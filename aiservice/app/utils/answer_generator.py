"""
Answer generation utilities using LLM
"""

import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


def generate_conversational_answer(
    question: str,
    filtered_docs: List[Dict],
    filters: Dict,
    filter_descriptions: List[str] = None,
    show_all: bool = False,
    llm_instance = None
) -> str:
    """Generate conversational answer using LLM for natural responses"""

    if not filtered_docs:
        is_hindi = any(ord(c) >= 0x0900 and ord(c) <= 0x097F for c in question)
        is_hinglish = any(word in question.lower() for word in ['mujhe', 'saari', 'dikhao', 'batao', 'kya'])

        if is_hindi:
            return "मुझे आपके सवाल से मेल खाने वाली कोई ट्रांज़ैक्शन नहीं मिली। 😊"
        elif is_hinglish:
            return "Sorry! 😊 Aapke filters ke hisaab se koi transaction nahi mili."
        return "No transactions found matching your query."

    # Calculate statistics
    amounts = [float(d.get("amount", 0)) for d in filtered_docs]
    total_amount = sum(amounts)
    avg_amount = total_amount / len(amounts) if amounts else 0
    max_amount = max(amounts) if amounts else 0
    min_amount = min(amounts) if amounts else 0

    # Prepare transaction summary for LLM
    filter_context = ", ".join(filter_descriptions) if filter_descriptions else "No filters"

    # If LLM is available, use it for natural response
    if llm_instance:
        # Sample transactions for context (max 10 for preview)
        sample_txns = filtered_docs[:10]
        txn_details = []
        for i, txn in enumerate(sample_txns, 1):
            txn_details.append(
                f"Transaction {i}: "
                f"₹{float(txn.get('amount', 0)):,.2f} ({txn.get('pk_GSI_1', 'N/A').replace('TYPE#', '')}), "
                f"{txn.get('mode', txn.get('txnMode', 'N/A'))}, "
                f"{txn.get('createdAt', 'N/A')[:10]}, "
                f"Narration: {txn.get('narration', 'N/A')[:50]}"
            )

        context_info = f"""
TRANSACTION QUERY RESULTS:
Total Matching Transactions: {len(filtered_docs)}
Filters Applied: {filter_context}

STATISTICS:
- Total Amount: ₹{total_amount:,.2f}
- Average Amount: ₹{avg_amount:,.2f}
- Highest: ₹{max_amount:,.2f}
- Lowest: ₹{min_amount:,.2f}

SAMPLE TRANSACTIONS (showing {len(sample_txns)} of {len(filtered_docs)}):
{chr(10).join(txn_details)}
"""

        prompt = f"""You are an intelligent financial assistant. Understand the user's question deeply, then provide a natural, helpful response.

USER QUESTION: {question}

{context_info}

INSTRUCTIONS:
1. First, understand what the user is asking (list, summary, analysis, specific details, etc.)
2. Detect the language: Hindi (Devanagari), Hinglish (Roman script with Hindi words), or English
3. Respond in the SAME language style as the question
4. Be conversational, warm, and helpful - don't use robotic templates
5. Provide the information they need naturally
6. If they ask for "all" transactions, mention that detailed list is provided separately
7. Give insights, patterns, or helpful observations when relevant
8. Use emojis moderately for friendliness

YOUR NATURAL RESPONSE:"""

        try:
            response = llm_instance.invoke(prompt)
            return response.content
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            # Fallback to template

    # Fallback: Template-based response (if LLM unavailable)
    is_hindi = any(ord(c) >= 0x0900 and ord(c) <= 0x097F for c in question)
    is_hinglish = any(word in question.lower() for word in ['mujhe', 'saari', 'dikhao', 'batao', 'kya', 'ki', 'se', 'ko'])

    if is_hindi:
        return f"नमस्ते! 😊 {len(filtered_docs)} ट्रांज़ैक्शन मिली हैं।\n\n📊 सारांश:\n   • कुल राशि: ₹{total_amount:,.2f}\n   • औसत: ₹{avg_amount:,.2f}"
    elif is_hinglish:
        return f"Namaste! 😊 Maine {len(filtered_docs)} transactions nikali hain.\n\n📊 Summary:\n   • Total: ₹{total_amount:,.2f}\n   • Average: ₹{avg_amount:,.2f}"
    else:
        return f"Hello! 😊 I found {len(filtered_docs)} transaction(s).\n\n📊 Summary:\n   • Total: ₹{total_amount:,.2f}\n   • Average: ₹{avg_amount:,.2f}"
