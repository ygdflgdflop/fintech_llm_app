import yfinance as yf
from langchain_core.tools import Tool
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_experimental.tools import PythonREPLTool
from .database import get_db_toolkit
from .rag import RAGManager
from typing import List, cast, Optional

def setup_tools(rag_manager: RAGManager, llm, user_email: Optional[str] = None):
    """Set up the tools for the finance agent.
    
    Args:
        rag_manager: The RAG manager for financial knowledge retrieval
        llm: The language model to use for SQL toolkit
        user_email: The email of the currently logged in user
    """
    def get_stock_price(ticker):
        """Get the latest price for a stock ticker."""
        try:
            stock = yf.Ticker(ticker)
            price = stock.history(period="1d")['Close'].iloc[-1]
            return f"The current price of {ticker} is ${price:.2f}"
        except Exception as e:
            return f"Error fetching stock price: {str(e)}"
        
    def retrieve_financial_knowledge(query):
        """Retrieve financial knowledge from the vector store."""
        try:
            print(f"Retrieving financial knowledge for user: {user_email}")
            print(f"Query: {query}")
            print("="*100)
            rag_chain = rag_manager.get_conversational_rag_chain()
        
            response = rag_chain.invoke(
                {"input": query},
                config={"configurable": {"session_id": user_email if user_email else "anonymous"}}
            )
            
            return response["answer"]
        
        except Exception as e:
            return f"Error retrieving financial knowledge: {str(e)}"
        
    python_repl = PythonREPLTool()

    tavily_search = TavilySearchResults(max_results=3)

    tools = [
        Tool(
            name="get_stock_price",
            func=get_stock_price,
            description="Get the current price of a stock. Input should be a valid stock ticker symbol (e.g., AAPL, MSFT)."
        ),
        Tool(
            name="python_calculator",
            func=python_repl.run,
            description="Useful for performing calculations, data analysis, or generating visualizations. Input should be Python code."
        ),
        Tool(
            name="market_research",
            func=tavily_search.invoke,
            description="Search the web for financial news, market analysis, or investment advice. Input should be a search query."
        ),
        Tool.from_function(
            func=retrieve_financial_knowledge,
            name="retrieve_financial_knowledge",
            description="""Retrieve financial knowledge, investment fundamentals 
            and advice from our knowledge base with conversation memory. 
            This tool maintains conversation history for contextual follow-up questions. 
            Use this for questions about financial advice, investment strategies, best practices, 
            recommendations, or when you need expert financial guidance.""",
            return_direct=True
        )
    ]
    
    sql_toolkit = get_db_toolkit(llm)
    sql_tools = sql_toolkit.get_tools()
    
    for tool in sql_tools:
        if tool.name == "sql_db_query":
            tool.description = """
Execute SQL queries on the finance database to retrieve information about:
1. User details (from the 'users' table) - Access user profile information
2. Transaction history (from the 'transactions' table) - Get spending history, income, expenses by category
3. Investment portfolio (from the 'portfolio' table) - Access stock holdings, purchase history, and portfolio composition

When querying for personal data, always filter using the email_id column to ensure data privacy.
Example: SELECT * FROM transactions WHERE email_id = '<user_email>'

Use this for direct SQL database queries to analyze financial data or retrieve specific information.
"""
        elif tool.name == "sql_db_schema":
            tool.description = """
Get schema information about the finance database tables:
- users: User account information (email_id, name, join_date)
- transactions: Financial transaction records (id, email_id, date, amount, category, description)
- portfolio: Investment holdings (id, email_id, symbol, shares, purchase_price, purchase_date)

Use this to understand database structure before querying.
"""
        elif tool.name == "sql_db_list_tables":
            tool.description = """
List all tables in the finance database 
Use this when you need to check what tables are available for querying.
"""
    
    tools.extend(cast(List[Tool], sql_tools))
    
    return tools 