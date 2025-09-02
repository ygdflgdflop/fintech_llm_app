import streamlit as st
import os
import uuid

from tempfile import NamedTemporaryFile
from datetime import datetime

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.runnables import ConfigurableFieldSpec,RunnableLambda
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_tool_calling_agent
from utils import RAGManager
from utils import setup_tools
from dotenv import load_dotenv

load_dotenv()

os.makedirs("fintech_app/data", exist_ok=True)
st.set_page_config(page_title="Fintech Assistant", page_icon="💰", layout="wide")

llm = ChatOpenAI(model="gpt-4o-mini")
if "store" not in st.session_state:
    st.session_state.store = {}

if "user_id" not in st.session_state:
    st.session_state.user_id = ""  

if "conversations" not in st.session_state:
    st.session_state.conversations = {}

if "conversation_counter" not in st.session_state:
    st.session_state.conversation_counter = 1

if "current_conversation_id" not in st.session_state:
    new_conv_id = str(uuid.uuid4())
    st.session_state.conversations[new_conv_id] = {
        "number": st.session_state.conversation_counter,
        "messages": []
    }
    st.session_state.current_conversation_id = new_conv_id

if "role" not in st.session_state:
    st.session_state.role = "user"
    
if "user_email" not in st.session_state:
    st.session_state.user_email = ""
    
if "email_submitted" not in st.session_state:
    st.session_state.email_submitted = False
def get_session_history(user_id: str, conversation_id: str) -> ChatMessageHistory:
    if (user_id, conversation_id) not in st.session_state.store:
        st.session_state.store[(user_id, conversation_id)] = ChatMessageHistory()
    return st.session_state.store[(user_id, conversation_id)]

def create_new_conversation():
    st.session_state.conversation_counter += 1

    new_conv_id = str(uuid.uuid4())

    st.session_state.conversations[new_conv_id] = {
        "number": st.session_state.conversation_counter,
        "messages": []
    }
    st.session_state.current_conversation_id = new_conv_id

def switch_conversation(conv_id):
    st.session_state.current_conversation_id = conv_id

def handle_chat_input(prompt, agent_executor_with_history):
    current_conv = st.session_state.conversations[st.session_state.current_conversation_id]
    current_conv["messages"].append({"role": "user", "content": prompt})

    config = {
        "configurable": {
            "user_id": st.session_state.user_id,
            "conversation_id": st.session_state.current_conversation_id
        }
    }
    
    with st.chat_message("assistant", avatar="💰"):
        response_container = st.empty()
        response_container.markdown("Thinking...")
        
        try:
            result = agent_executor_with_history.invoke(
                {"input": prompt},
                config=config,
            )
            
            response_container.markdown(result["output"])
            current_conv["messages"].append({"role": "assistant", "content": result["output"]})
        except Exception as e:
            response_container.markdown(f"Error: {str(e)}")
            current_conv["messages"].append({"role": "assistant", "content": f"Error: {str(e)}"})

def setup_agent(tools):
    system_message = f"""You are a personal finance assistant for user with email {st.session_state.user_email}.
When querying the database for user data, always filter results using:
WHERE email_id = '{st.session_state.user_email}'

You have access to tools to help with financial queries. Use these tools to provide accurate and helpful responses.

For each request:
1. Analyze what the user is asking for
2. Choose the appropriate tool to use
3. Use the tool to get the information needed
4. Present the information in a clear, educational way

When users ask for financial advice, investment recommendations, or best practices, use the retrieve_financial_knowledge tool to get relevant information from our knowledge base.

Always be helpful, clear, and educational in your responses. Explain financial concepts simply.
When providing investment advice, always include disclaimers about risk.
Never make up information - if you don't know or need more data, say so.
"""
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_message),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad")
    ])
    
    agent = create_tool_calling_agent(llm, tools, prompt)
    agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
    
    agent_executor_with_history = RunnableWithMessageHistory(
        agent_executor,
        get_session_history,
        input_messages_key="input",
        history_messages_key="chat_history",
        history_factory_config=[
            ConfigurableFieldSpec(
                id="user_id",
                annotation=str,
                name="User ID",
            ),
            ConfigurableFieldSpec(
                id="conversation_id",
                annotation=str,
                name="Conversation ID",
            ),
        ],
    )
    
    return agent_executor_with_history

def set_role(role):
    st.session_state.role = role
    if role == "user":
        st.session_state.email_submitted = False
        st.session_state.user_email = ""
        st.session_state.user_id = ""

def show_admin_interface(rag_manager):
    st.title("💰 Fintech Knowledge Administration")
    
    st.info("As an admin, you can upload financial knowledge that will be used to power the chatbot's responses.")
    
    st.subheader("Upload Knowledge File")
    uploaded_file = st.file_uploader("Choose a text file", type=["txt"], key="file_uploader")
    
    if uploaded_file:

        with NamedTemporaryFile(delete=False, suffix=".txt") as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            temp_path = tmp_file.name
        

        if st.button("Process File"):
            with st.spinner("Processing file..."):
                result = rag_manager.add_document_from_file(temp_path)
                st.success(result)
            

            os.unlink(temp_path)
    

def show_user_interface(agent_executor_with_history):
    st.title("💰 Personal Finance Assistant")
    
    if not st.session_state.email_submitted or not st.session_state.user_id:
        st.info("Please enter your email address to start chatting. This will be used to maintain your conversation history.")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            email = st.text_input("Email Address:", key="email_input", placeholder="you@example.com")
        with col2:
            submit_button = st.button("Submit", type="primary")
            
        if submit_button:
            if submit_email(email):
                st.success("Email submitted successfully! You can now start chatting.")
                st.rerun()
            else:
                st.error("Please enter a valid email address.")
        

        st.sidebar.subheader("Sample Questions")
        st.sidebar.markdown("""
        - What's my current spending by category?
        - What's the price of AAPL stock?
        - How should I start investing with $1000?
        - Calculate a monthly mortgage payment for $300,000
        - What are the latest news about interest rates?
        - Show me my investment portfolio performance
        """)
        return
    
    with st.sidebar:
        st.subheader("Conversations")


        if st.button("New Conversation", key="new_conv"):
            create_new_conversation()


        conversations_list = [(conv_id, f"Conversation {conv_data['number']}")
                             for conv_id, conv_data in st.session_state.conversations.items()]

        if conversations_list:
            selected_conv = st.selectbox(
                "Select Conversation:",
                options=[conv[0] for conv in conversations_list],
                format_func=lambda x: [conv[1] for conv in conversations_list if conv[0] == x][0],
                index=list(st.session_state.conversations.keys()).index(st.session_state.current_conversation_id)
            )

            if selected_conv != st.session_state.current_conversation_id:
                switch_conversation(selected_conv)
        
        st.divider()
        st.subheader("Sample Questions")
        st.markdown("""
        - What's my current spending by category?
        - What's the price of AAPL stock?
        - How should I start investing with $1000?
        - Calculate a monthly mortgage payment for $300,000
        - What are the latest news about interest rates?
        - Show me my investment portfolio performance
        """)
    
    current_conv = st.session_state.conversations[st.session_state.current_conversation_id]

    with st.sidebar:
        st.caption(f"Logged in as: {st.session_state.user_id}")
        if st.button("Change Email"):
            st.session_state.email_submitted = False
            st.session_state.user_email = ""
            st.session_state.user_id = ""
            st.rerun()
    
    for message in current_conv["messages"]:
        with st.chat_message(message["role"], avatar="👤" if message["role"] == "user" else "💰"):
            st.write(message["content"])

    if prompt := st.chat_input("Ask about your finances..."):
        handle_chat_input(prompt, agent_executor_with_history)

def submit_email(email):
    """Handle email submission and validate it"""
    if "@" in email and "." in email:
        st.session_state.user_email = email

        st.session_state.email_submitted = True
        return True
    else:
        return False
def main():
    rag_manager = RAGManager("fintech_app/data/chroma_db")
    
    tools = setup_tools(rag_manager, llm=llm, user_email=st.session_state.user_email)
    agent_executor_with_history = setup_agent(tools)
    
    with st.sidebar:
        st.divider()
        st.subheader("Role Selection")
        selected_role = st.radio("Select Role:", ["user", "admin"], index=0 if st.session_state.role == "user" else 1)
        if selected_role != st.session_state.role:
            set_role(selected_role)
            st.rerun()
    if st.session_state.role == "admin":
        show_admin_interface(rag_manager)
    else:
        show_user_interface(agent_executor_with_history)

if __name__ == "__main__":
    main() 