"""
Data store for ingested transaction data
"""

from typing import Dict, List, Any, Optional
from datetime import datetime

# Storage for ingested context data
ingested_data_store: Dict[str, Any] = {
    "transactions": [],
    "vectorstore": None,
    "langchain_docs": [],
    "last_updated": None
}


def get_ingested_data() -> Dict[str, Any]:
    """Get the ingested data store"""
    return ingested_data_store


def set_ingested_data(transactions: List[Dict], vectorstore, langchain_docs: List):
    """Set the ingested data"""
    global ingested_data_store
    ingested_data_store["transactions"] = transactions
    ingested_data_store["vectorstore"] = vectorstore
    ingested_data_store["langchain_docs"] = langchain_docs
    ingested_data_store["last_updated"] = datetime.now().isoformat()


def clear_ingested_data():
    """Clear the ingested data"""
    global ingested_data_store
    ingested_data_store["transactions"] = []
    ingested_data_store["vectorstore"] = None
    ingested_data_store["langchain_docs"] = []
    ingested_data_store["last_updated"] = None


def has_ingested_data() -> bool:
    """Check if data has been ingested"""
    return len(ingested_data_store["transactions"]) > 0
