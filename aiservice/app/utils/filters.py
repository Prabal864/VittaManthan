"""
Filter extraction and application utilities
"""

import re
import logging
from typing import List, Dict, Any, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


def extract_filters_from_query(question: str) -> Dict[str, Any]:
    """
    Extract filters from natural language query
    Supports: amount, date, mode, type, account, person name
    """
    filters = {
        "amount_above": None,
        "amount_below": None,
        "amount_range": None,
        "date_filter": None,
        "mode": None,
        "type": None,
        "account_id": None,
        "person_name": None,
        "strict_name_match": False
    }

    question_lower = question.lower()

    # Date filters (month/year)
    months_hindi = {
        'january': 1, 'jan': 1, 'जनवरी': 1,
        'february': 2, 'feb': 2, 'फरवरी': 2,
        'march': 3, 'mar': 3, 'मार्च': 3,
        'april': 4, 'apr': 4, 'अप्रैल': 4,
        'may': 5, 'मई': 5,
        'june': 6, 'jun': 6, 'जून': 6,
        'july': 7, 'jul': 7, 'जुलाई': 7,
        'august': 8, 'aug': 8, 'अगस्त': 8,
        'september': 9, 'sep': 9, 'सितंबर': 9,
        'october': 10, 'oct': 10, 'अक्टूबर': 10,
        'november': 11, 'nov': 11, 'नवंबर': 11,
        'december': 12, 'dec': 12, 'दिसंबर': 12
    }

    # Extract month and year
    for month_name, month_num in months_hindi.items():
        if month_name in question_lower:
            filters['date_filter'] = {'month': month_num}
            year_match = re.search(rf'{month_name}\s*(\d{{4}})', question_lower)
            if year_match:
                filters['date_filter']['year'] = int(year_match.group(1))
            break

    # Year only
    if not filters['date_filter']:
        year_match = re.search(r'\b(20\d{2})\b', question_lower)
        if year_match:
            filters['date_filter'] = {'year': int(year_match.group(1))}

    # Amount filters - Avoid year confusion
    all_numbers_raw = re.findall(r'\d+(?:,\d+)*(?:\.\d+)?[kKlL]?', question_lower)

    amounts_processed = []
    for num_str in all_numbers_raw:
        num_clean = num_str.replace(',', '').lower()

        # Skip if it's a year
        if re.match(r'^202[0-9]$', num_clean):
            logger.debug(f"Skipping year: {num_str}")
            continue

        # Convert K/L notation
        try:
            if 'k' in num_clean:
                value = float(num_clean.replace('k', '')) * 1000
            elif 'l' in num_clean:
                value = float(num_clean.replace('l', '')) * 100000
            else:
                value = float(num_clean)
            amounts_processed.append(value)
        except ValueError:
            continue

    logger.debug(f"Processed amounts: {amounts_processed}")

    # Range: "between ₹10,000 and ₹30,000"
    if "between" in question_lower and len(amounts_processed) >= 2:
        min_amt = amounts_processed[0]
        max_amt = amounts_processed[1]
        if min_amt > max_amt:
            min_amt, max_amt = max_amt, min_amt
        filters['amount_range'] = (min_amt, max_amt)
        logger.info(f"Amount range: ₹{min_amt:,.2f} to ₹{max_amt:,.2f}")

    # Above/Greater than
    elif any(word in question_lower for word in ["above", "greater than", "more than", "over", "zyada", "se zyada"]):
        if amounts_processed:
            filters['amount_above'] = amounts_processed[0]
            logger.info(f"Amount above: ₹{filters['amount_above']:,.2f}")

    # Below/Less than
    elif any(word in question_lower for word in ["below", "less than", "under", "kam", "se kam"]):
        if amounts_processed:
            filters['amount_below'] = amounts_processed[0]
            logger.info(f"Amount below: ₹{filters['amount_below']:,.2f}")

    # Transaction mode
    modes = ['UPI', 'CASH', 'NEFT', 'IMPS', 'RTGS', 'DEBIT CARD', 'CREDIT CARD']
    for mode in modes:
        if mode.lower() in question_lower:
            filters['mode'] = mode
            break

    # Transaction type
    if any(word in question_lower for word in ['credit', 'credited', 'क्रेडिट']):
        filters['type'] = 'CREDIT'
    elif any(word in question_lower for word in ['debit', 'debited', 'डेबिट']):
        filters['type'] = 'DEBIT'

    # Account ID (UUID pattern)
    account_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
    account_match = re.search(account_pattern, question_lower)
    if account_match:
        filters['account_id'] = account_match.group(0)
    else:
        account_keyword_match = re.search(r'(?:account|acc|खाता)\s*(?:number|no|#)?\s*[:=]?\s*([a-zA-Z0-9\-]+)', question_lower)
        if account_keyword_match:
            filters['account_id'] = account_keyword_match.group(1)

    # Person name - STRICT MATCHING for full names
    name_patterns = re.findall(r'(?:by|from|to|with|se|ko|द्वारा)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', question)
    if name_patterns:
        filters['person_name'] = name_patterns[0].strip()
        filters['strict_name_match'] = True
        logger.info(f"STRICT name filter: '{filters['person_name']}'")
    else:
        single_name = re.findall(r'(?:by|from|to|with|se|ko|द्वारा)\s+([A-Z][a-z]+)', question)
        if single_name:
            filters['person_name'] = single_name[0].strip()
            filters['strict_name_match'] = False
            logger.info(f"Loose name filter: '{filters['person_name']}'")

    return filters


def apply_filters(documents: List[Dict], filters: Dict, question: str) -> Tuple[List[Dict], List[str]]:
    """
    Apply extracted filters to documents
    Returns: (filtered_docs, filter_descriptions)
    """
    filtered = documents.copy()
    descriptions = []

    logger.info(f"Applying filters to {len(documents)} transactions...")

    # Date filter
    if filters.get('date_filter'):
        date_f = filters['date_filter']
        new_filtered = []
        for d in filtered:
            date_str = d.get('createdAt', '')
            if date_str:
                try:
                    date_obj = datetime.strptime(date_str[:10], '%Y-%m-%d')
                    match = True
                    if 'year' in date_f and date_obj.year != date_f['year']:
                        match = False
                    if 'month' in date_f and date_obj.month != date_f['month']:
                        match = False
                    if match:
                        new_filtered.append(d)
                except:
                    pass
        filtered = new_filtered
        if 'month' in date_f and 'year' in date_f:
            month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
            descriptions.append(f"Date: {month_names[date_f['month']-1]} {date_f['year']}")
        elif 'year' in date_f:
            descriptions.append(f"Year: {date_f['year']}")
        logger.info(f"Date filter: {len(filtered)} transactions")

    # Mode filter
    if filters.get('mode'):
        mode = filters['mode']
        filtered = [d for d in filtered if d.get('mode', d.get('txnMode', '')).upper() == mode.upper()]
        descriptions.append(f"Mode: {mode}")
        logger.info(f"Mode filter: {len(filtered)} {mode} transactions")

    # Type filter
    if filters.get('type'):
        txn_type = filters['type']
        filtered = [d for d in filtered if txn_type in d.get('pk_GSI_1', '')]
        descriptions.append(f"Type: {txn_type}")
        logger.info(f"Type filter: {len(filtered)} {txn_type} transactions")

    # Amount filters
    if filters.get('amount_range'):
        min_amt, max_amt = filters['amount_range']
        filtered = [d for d in filtered if min_amt <= float(d.get('amount', 0)) <= max_amt]
        descriptions.append(f"Amount: ₹{min_amt:,.2f} - ₹{max_amt:,.2f}")
        logger.info(f"Amount range: {len(filtered)} transactions")

    elif filters.get('amount_above'):
        threshold = filters['amount_above']
        amount_filtered = [d for d in filtered if float(d.get('amount', 0)) > threshold]
        filtered = amount_filtered

        # Validation
        if filtered:
            min_amount = min([float(d.get('amount', 0)) for d in filtered])
            logger.info(f"Min amount: ₹{min_amount:,.2f} (should be > ₹{threshold:,.2f})")

        descriptions.append(f"Amount above: ₹{threshold:,.2f}")
        logger.info(f"Amount filter: {len(filtered)} transactions above ₹{threshold:,.2f}")

    elif filters.get('amount_below'):
        threshold = filters['amount_below']
        filtered = [d for d in filtered if float(d.get('amount', 0)) < threshold]
        descriptions.append(f"Amount below: ₹{threshold:,.2f}")
        logger.info(f"Amount filter: {len(filtered)} transactions below ₹{threshold:,.2f}")

    # Account filter
    if filters.get('account_id'):
        acc_id = filters['account_id']
        account_filtered = [d for d in filtered
                           if d.get('accountId', d.get('accountNumber', '')).lower() == acc_id.lower()]
        filtered = account_filtered
        descriptions.append(f"Account: {acc_id}")
        logger.info(f"Account filter: {len(filtered)} transactions")

    # Person name filter - STRICT MATCHING
    if filters.get('person_name'):
        name = filters['person_name']
        strict_match = filters.get('strict_name_match', False)

        if strict_match:
            person_filtered = []
            for d in filtered:
                narration = d.get('narration', '')
                name_words = name.split()
                if len(name_words) >= 2:
                    pattern = r'\b' + r'\s+'.join(re.escape(word) for word in name_words) + r'\b'
                    if re.search(pattern, narration, re.IGNORECASE):
                        person_filtered.append(d)
                else:
                    if name.lower() in narration.lower():
                        person_filtered.append(d)

            filtered = person_filtered
            descriptions.append(f"EXACT name: '{name}'")
            logger.info(f"STRICT name filter: {len(filtered)} transactions")
        else:
            person_filtered = [d for d in filtered if name.lower() in d.get('narration', '').lower()]
            filtered = person_filtered
            descriptions.append(f"Person: '{name}'")
            logger.info(f"Loose name filter: {len(filtered)} transactions")

    return filtered, descriptions
