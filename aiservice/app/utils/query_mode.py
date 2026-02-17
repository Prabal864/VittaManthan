"""
Query mode detection utilities
"""

import re
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


def detect_query_mode(question: str, documents: List[Dict]) -> str:
    """
    Detect the best mode for answering the query
    Returns: VECTOR_SEARCH, SMART_FULL, or STATISTICAL
    """
    question_lower = question.lower()

    # PRIORITY 1: Counting queries - needs ALL transactions
    # Check for "how many", "kitne", "count", "total transactions" type queries
    counting_patterns = [
        r'\b(how many|kitne|count|total)\s+.*?transaction',  # how many transactions
        r'transaction.*?\b(how many|kitne|count|total)',      # transactions how many
        r'\b(कितने|कितनी)\s+.*?(transaction|ट्रांज)',        # Hindi: kitne transactions
        r'(transaction|ट्रांज).*?\b(कितने|कितनी)',            # transactions kitne
        r'\b(how|kitne)\s+many\b',                             # how many
        r'\bnumber of\s+transaction',                          # number of transactions
    ]

    for pattern in counting_patterns:
        if re.search(pattern, question_lower):
            logger.info("Detected counting query - using VECTOR_SEARCH with ALL data awareness")
            return "VECTOR_SEARCH"  # Will be handled with comprehensive context

    # PRIORITY 2: Check for account number queries
    account_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
    has_account = bool(re.search(account_pattern, question_lower))
    has_account_keyword = bool(re.search(r'\b(account|acc|खाता)\s*(?:number|no|#)?\b', question_lower))

    if (has_account or has_account_keyword) and any(word in question_lower for word in ['transaction', 'saari', 'all', 'list', 'dikhao']):
        return "SMART_FULL"

    # PRIORITY 3: Statistical keywords (ONLY for pure stats, not analysis)
    exclude_patterns = [
        r'account\s*number',
        r'transaction\s*number',
        r'reference\s*number',
    ]
    is_excluded = any(re.search(pattern, question_lower) for pattern in exclude_patterns)

    if not is_excluded:
        # Only trigger stats mode for pure calculation queries
        stats_keywords = [
            'total amount', 'sum of', 'average amount', 'count of',
            'how many transactions', 'kitne transactions'
        ]
        if any(kw in question_lower for kw in stats_keywords):
            return "STATISTICAL"

    # PRIORITY 4: Full scan keywords (for filtered lists)
    full_scan_keywords = [
        'all', 'saari', 'sabhi', 'sab', 'every', 'show me', 'dikhao',
        'list', 'display', 'between', 'above', 'below', 'largest', 'smallest'
    ]
    if any(kw in question_lower for kw in full_scan_keywords):
        return "SMART_FULL"

    # PRIORITY 5: Date/time period queries
    has_year = bool(re.search(r'\b(20\d{2})\b', question_lower))
    has_month = bool(re.search(r'\b(january|february|march|april|may|june|july|august|september|october|november|december)\b', question_lower))

    if (has_year or has_month) and 'transaction' in question_lower:
        return "SMART_FULL"

    # PRIORITY 6: General analytical/summarization queries
    analytical_keywords = [
        'summarize', 'summarise', 'summary', 'analyze', 'analyse', 'analysis',
        'insights', 'patterns', 'trends', 'overview', 'explain', 'tell me about',
        'what happened', 'describe', 'understand', 'help me', 'guide', 'advice',
        'recommend', 'suggest', 'why', 'how', 'when', 'where', 'what',
        'batao', 'samjhao', 'bataiye', 'explain karo', 'kya hua'
    ]
    if any(kw in question_lower for kw in analytical_keywords):
        logger.info("Detected analytical query - using VECTOR_SEARCH with LLM")
        return "VECTOR_SEARCH"

    # Default to VECTOR_SEARCH for open-ended questions
    return "VECTOR_SEARCH"


def calculate_statistics(documents: List[Dict], filters: Dict) -> Dict[str, float]:
    """Calculate statistics on filtered documents"""
    from app.utils.filters import apply_filters

    filtered_docs, _ = apply_filters(documents, filters, "")

    if not filtered_docs:
        return {
            "count": 0,
            "total": 0.0,
            "average": 0.0,
            "max": 0.0,
            "min": 0.0
        }

    amounts = [float(d.get("amount", 0)) for d in filtered_docs]

    return {
        "count": len(filtered_docs),
        "total": sum(amounts),
        "average": sum(amounts) / len(amounts) if amounts else 0,
        "max": max(amounts) if amounts else 0,
        "min": min(amounts) if amounts else 0
    }
