"""
Pydantic models for request/response validation
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Any, Optional


class TransactionData(BaseModel):
    """Model for individual transaction"""
    model_config = ConfigDict(populate_by_name=True)

    txnId: Optional[str] = None
    accountId: Optional[str] = Field(None, alias="accountNumber")
    createdAt: Optional[str] = None
    amount: Optional[float] = 0.0
    currentBalance: Optional[float] = Field(None, alias="balance")
    mode: Optional[str] = Field(None, alias="txnMode")
    narration: Optional[str] = None
    reference: Optional[str] = Field(None, alias="txnRef")
    pk_GSI_1: Optional[str] = None


class RAGRequest(BaseModel):
    """Request model for RAG query"""
    context_data: List[Dict[str, Any]] = Field(..., description="List of transaction records")
    prompt: str = Field(..., description="User's question")
    page: int = Field(1, ge=1, description="Page number for pagination")
    page_size: int = Field(20, ge=1, le=100, description="Items per page")
    show_all: bool = Field(True, description="Show all matching transactions")
    use_full_data: Optional[bool] = Field(None, description="Force full scan mode")


class IngestRequest(BaseModel):
    """Request model for ingesting context data"""
    context_data: List[Dict[str, Any]] = Field(..., description="List of transaction records to ingest")


class IngestResponse(BaseModel):
    """Response model for ingestion"""
    status: str
    message: str
    transactions_ingested: int
    timestamp: str


class PromptRequest(BaseModel):
    """Request model for prompt-only queries (uses pre-ingested data)"""
    prompt: str = Field(..., description="User's question")
    page: int = Field(1, ge=1, description="Page number for pagination")
    page_size: int = Field(20, ge=1, le=100, description="Items per page")
    show_all: bool = Field(True, description="Show all matching transactions")
    use_full_data: Optional[bool] = Field(None, description="Force full scan mode")
    query_id: Optional[str] = Field(None, description="Query ID for pagination caching (auto-generated if not provided)")


class TransactionInfo(BaseModel):
    """Transaction info for response"""
    transaction_id: str
    account_number: str
    date: str
    amount: float
    type: str
    mode: str
    balance_after: float
    narration: str
    reference: str


class RAGResponse(BaseModel):
    """Response model for RAG query"""
    query_id: str
    answer: str
    mode: str
    matching_transactions_count: int
    filters_applied: Optional[List[str]] = None
    transactions: Optional[List[TransactionInfo]] = None
    pagination: Optional[Dict[str, Any]] = None
    statistics: Optional[Dict[str, Any]] = None
