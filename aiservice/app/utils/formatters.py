"""
Transaction formatting utilities
"""

from typing import Dict
from app.models.schemas import TransactionInfo


def format_transaction_for_vector(record: Dict) -> str:
    """Format transaction for vector storage"""
    return (
        f"Account Number: {record.get('accountId', record.get('accountNumber', 'N/A'))}\n"
        f"Transaction ID: {record.get('txnId', 'N/A')}\n"
        f"Date: {record.get('createdAt', 'N/A')}\n"
        f"Amount: ₹{float(record.get('amount', 0)):,.2f}\n"
        f"Current Balance: ₹{float(record.get('currentBalance', record.get('balance', 0))):,.2f}\n"
        f"Mode: {record.get('mode', record.get('txnMode', 'N/A'))}\n"
        f"Narration: {record.get('narration', 'N/A')}\n"
        f"Reference: {record.get('reference', record.get('txnRef', 'N/A'))}\n"
        f"Transaction Type: {record.get('pk_GSI_1', 'N/A').replace('TYPE#', '')}\n"
    )


def format_transaction_for_api(doc: Dict) -> TransactionInfo:
    """Format transaction for API response"""
    return TransactionInfo(
        transaction_id=doc.get("txnId", "N/A"),
        account_number=doc.get("accountId", doc.get("accountNumber", "N/A")),
        date=doc.get("createdAt", "N/A"),
        amount=float(doc.get("amount", 0)),
        type=doc.get("pk_GSI_1", "N/A").replace("TYPE#", ""),
        mode=doc.get("mode", doc.get("txnMode", "N/A")),
        balance_after=float(doc.get("currentBalance", doc.get("balance", 0))),
        narration=doc.get("narration", "N/A"),
        reference=doc.get("reference", doc.get("txnRef", "N/A"))
    )
