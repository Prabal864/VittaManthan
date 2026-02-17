"""
RAG (Retrieval-Augmented Generation) Service
Core business logic for transaction querying with LLM
"""

import logging
from typing import List, Dict, Tuple
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

from app.utils.formatters import format_transaction_for_vector
from app.utils.filters import extract_filters_from_query, apply_filters
from app.utils.query_mode import calculate_statistics
from app.utils.answer_generator import generate_conversational_answer

logger = logging.getLogger(__name__)


class RAGService:
    """Service for handling RAG-based transaction queries"""

    def __init__(self, embeddings_model, llm):
        self.embeddings_model = embeddings_model
        self.llm = llm

    def create_vector_store(self, documents: List[Dict]) -> Tuple[FAISS, List[Document]]:
        """Create vector store from transaction documents"""
        langchain_docs = []
        for txn in documents:
            formatted_content = format_transaction_for_vector(txn)
            doc = Document(
                page_content=formatted_content,
                metadata={
                    "txnId": txn.get("txnId", ""),
                    "date": txn.get("createdAt", ""),
                    "amount": float(txn.get("amount", 0)),
                    "mode": txn.get("mode", txn.get("txnMode", "")),
                    "type": txn.get("pk_GSI_1", "").replace("TYPE#", ""),
                    "accountNumber": txn.get("accountId", txn.get("accountNumber", "N/A")),
                    "narration": txn.get("narration", "N/A")
                }
            )
            langchain_docs.append(doc)

        logger.info(f"Created {len(langchain_docs)} document objects")

        vectorstore = FAISS.from_documents(langchain_docs, self.embeddings_model)
        logger.info("✅ Vector store created")

        return vectorstore, langchain_docs

    def process_statistical_query(
        self,
        documents: List[Dict],
        prompt: str
    ) -> Tuple[str, Dict[str, float], List[str], int]:
        """Process statistical analysis queries"""
        filters = extract_filters_from_query(prompt)
        stats = calculate_statistics(documents, filters)
        filtered_docs, filter_desc = apply_filters(documents, filters, prompt)

        is_hindi = any(ord(c) >= 0x0900 and ord(c) <= 0x097F for c in prompt)
        is_hinglish = any(word in prompt.lower() for word in ['mujhe', 'saari', 'dikhao'])

        filter_text = " (" + ", ".join(filter_desc) + ")" if filter_desc else ""

        if is_hindi:
            answer = f"📊 सांख्यिकी{filter_text}:\n"
            answer += f"• कुल: {stats['count']}\n"
            answer += f"• राशि: ₹{stats['total']:,.2f}\n"
            answer += f"• औसत: ₹{stats['average']:,.2f}\n"
        elif is_hinglish:
            answer = f"📊 Statistics{filter_text}:\n"
            answer += f"• Total: {stats['count']}\n"
            answer += f"• Amount: ₹{stats['total']:,.2f}\n"
            answer += f"• Average: ₹{stats['average']:,.2f}\n"
        else:
            answer = f"📊 Statistics{filter_text}:\n"
            answer += f"• Total: {stats['count']}\n"
            answer += f"• Amount: ₹{stats['total']:,.2f}\n"
            answer += f"• Average: ₹{stats['average']:,.2f}\n"

        return answer, stats, filter_desc, len(filtered_docs)

    def process_smart_full_query(
        self,
        documents: List[Dict],
        prompt: str,
        show_all: bool
    ) -> Tuple[str, List[Dict], List[str]]:
        """Process full scan queries with filters"""
        filters = extract_filters_from_query(prompt)
        filtered_docs, filter_descriptions = apply_filters(documents, filters, prompt)

        # Generate answer using LLM
        answer = generate_conversational_answer(
            prompt,
            filtered_docs,
            filters,
            filter_descriptions,
            show_all,
            self.llm
        )

        return answer, filtered_docs, filter_descriptions

    def process_analytical_query(
        self,
        documents: List[Dict],
        prompt: str
    ) -> str:
        """Process analytical queries that need comprehensive context"""
        logger.info(f"Analytical query detected - analyzing ALL {len(documents)} transactions")

        # Calculate comprehensive statistics from ALL transactions
        amounts = [float(d.get('amount', 0)) for d in documents]
        total_amount = sum(amounts)
        avg_amount = total_amount / len(amounts) if amounts else 0

        # Analyze by transaction type and mode
        type_breakdown = {}
        mode_breakdown = {}
        date_breakdown = {}

        for doc in documents:
            # Type breakdown
            txn_type = doc.get('pk_GSI_1', '').replace('TYPE#', '')
            if txn_type not in type_breakdown:
                type_breakdown[txn_type] = {'count': 0, 'amount': 0.0}
            type_breakdown[txn_type]['count'] += 1
            type_breakdown[txn_type]['amount'] += float(doc.get('amount', 0))

            # Mode breakdown
            txn_mode = doc.get('mode', doc.get('txnMode', 'UNKNOWN'))
            if txn_mode not in mode_breakdown:
                mode_breakdown[txn_mode] = {'count': 0, 'amount': 0.0}
            mode_breakdown[txn_mode]['count'] += 1
            mode_breakdown[txn_mode]['amount'] += float(doc.get('amount', 0))

            # Month breakdown
            created_at = doc.get('createdAt', '')
            if created_at:
                month_key = created_at[:7]
                if month_key not in date_breakdown:
                    date_breakdown[month_key] = {'count': 0, 'amount': 0.0}
                date_breakdown[month_key]['count'] += 1
                date_breakdown[month_key]['amount'] += float(doc.get('amount', 0))

        # Get diverse sample of transactions
        sorted_by_amount = sorted(documents, key=lambda x: float(x.get('amount', 0)), reverse=True)
        sorted_by_date = sorted(documents, key=lambda x: x.get('createdAt', ''), reverse=True)

        sample_transactions = []
        seen_ids = set()

        # Top 10 highest amounts
        for txn in sorted_by_amount[:10]:
            txn_id = txn.get('txnId', '')
            if txn_id not in seen_ids:
                seen_ids.add(txn_id)
                sample_transactions.append(txn)

        # Bottom 5 lowest amounts
        for txn in sorted_by_amount[-5:]:
            txn_id = txn.get('txnId', '')
            if txn_id not in seen_ids and len(sample_transactions) < 15:
                seen_ids.add(txn_id)
                sample_transactions.append(txn)

        # Recent 15 transactions
        for txn in sorted_by_date[:15]:
            txn_id = txn.get('txnId', '')
            if txn_id not in seen_ids and len(sample_transactions) < 30:
                seen_ids.add(txn_id)
                sample_transactions.append(txn)

        # Format comprehensive context
        context_parts = [
            f"📊 COMPLETE DATASET ANALYSIS (ALL {len(documents)} TRANSACTIONS):",
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"Total Transactions: {len(documents)}",
            f"Total Amount: ₹{total_amount:,.2f}",
            f"Average Amount: ₹{avg_amount:,.2f}",
            f"Highest Transaction: ₹{max(amounts):,.2f}" if amounts else "N/A",
            f"Lowest Transaction: ₹{min(amounts):,.2f}" if amounts else "N/A",
            "",
            f"📈 BREAKDOWN BY TRANSACTION TYPE (ALL {len(documents)} transactions):",
        ]

        for txn_type, data in sorted(type_breakdown.items(), key=lambda x: x[1]['amount'], reverse=True):
            context_parts.append(f"  • {txn_type}: {data['count']} transactions, Total: ₹{data['amount']:,.2f}")

        context_parts.append("")
        context_parts.append(f"💳 BREAKDOWN BY MODE (ALL {len(documents)} transactions):")
        for mode, data in sorted(mode_breakdown.items(), key=lambda x: x[1]['amount'], reverse=True):
            context_parts.append(f"  • {mode}: {data['count']} transactions, Total: ₹{data['amount']:,.2f}")

        if date_breakdown:
            context_parts.append("")
            context_parts.append(f"📅 MONTHLY BREAKDOWN (ALL {len(documents)} transactions):")
            for month, data in sorted(date_breakdown.items(), reverse=True)[:6]:
                context_parts.append(f"  • {month}: {data['count']} transactions, Total: ₹{data['amount']:,.2f}")

        context_parts.extend([
            "",
            f"📋 REPRESENTATIVE SAMPLE TRANSACTIONS ({len(sample_transactions)} shown from {len(documents)} total):",
            ""
        ])

        for i, txn in enumerate(sample_transactions, 1):
            context_parts.append(f"Sample Transaction {i}:")
            context_parts.append(format_transaction_for_vector(txn))
            context_parts.append("")

        comprehensive_context = "\n".join(context_parts)

        # Enhanced prompt for analytical queries
        prompt_template = ChatPromptTemplate.from_template("""You are an intelligent financial analyst with access to COMPLETE transaction data.

🎯 CRITICAL: You have COMPREHENSIVE statistics and breakdowns from EXACTLY {total_transactions} transactions.
The statistics (totals, averages, breakdowns by type/mode/month) represent the ENTIRE dataset of {total_transactions} transactions, not just samples.

🧠 UNDERSTAND THE USER'S INTENT:
First, read the user's question carefully and understand:
- What are they asking for? (summary, analysis, insights, trends, count, specific transactions, comparisons, etc.)
- What's the context? (time period, amount range, person, mode, etc.)
- What level of detail do they want?

🌐 LANGUAGE INTELLIGENCE:
- Hindi (Devanagari script) → Respond in pure Hindi (Devanagari)
- Hinglish (Roman script with Hindi words like 'mujhe', 'dikhao', 'saari', 'batao', 'kitne') → Respond in Hinglish (Roman script)
- English → Respond in English
- Match the user's tone and formality level

📊 COMPLETE TRANSACTION DATA (ALL {total_transactions} transactions analyzed):
{context}

❓ USER'S QUESTION: {question}

💡 YOUR APPROACH:
1. **EXACT COUNT**: If asked "how many" or "kitne" transactions, the answer is EXACTLY {total_transactions}
2. **Acknowledge scope**: You're analyzing ALL {total_transactions} transactions (not just samples)
3. **Use comprehensive stats**: All breakdowns and totals represent the complete dataset of {total_transactions} transactions
4. **Be specific**: Use exact numbers from the statistics
5. **Provide insights**: Identify patterns, trends, anomalies across the full dataset
6. **Natural response**: Be conversational and match user's language style
7. **Accurate**: All numbers are from the complete dataset of {total_transactions} transactions
8. **Sample awareness**: The detailed transactions shown are examples; your stats cover all {total_transactions}

🚀 YOUR INTELLIGENT RESPONSE (analyzing ALL {total_transactions} transactions):""")

        prompt_input = {
            "context": comprehensive_context,
            "question": prompt,
            "total_transactions": len(documents)
        }

        chain = prompt_template | self.llm | StrOutputParser()
        result = chain.invoke(prompt_input)

        return result

    def process_vector_search_query(
        self,
        vectorstore: FAISS,
        prompt: str,
        k_value: int = 50
    ) -> str:
        """Process specific queries using vector similarity search"""
        logger.info(f"Using vector similarity search with k={k_value}")

        prompt_template = ChatPromptTemplate.from_template("""You are an intelligent financial assistant with expertise in analyzing transaction data.

🧠 UNDERSTAND FIRST, THEN RESPOND:
1. Read the user's question and understand their true intent
2. Analyze the transaction data provided in the context
3. Think about what information would be most helpful
4. Respond naturally in the user's language

🌐 LANGUAGE INTELLIGENCE:
- Hindi (Devanagari) → Respond in Hindi (Devanagari)
- Hinglish (Roman with Hindi words: mujhe, dikhao, saari, batao, kya) → Respond in Hinglish (Roman)
- English → Respond in English

📋 TRANSACTION CONTEXT (Most relevant transactions):
{context}

❓ USER'S QUESTION: {question}

💡 GUIDELINES FOR YOUR RESPONSE:
- Be conversational and natural - avoid robotic templates
- Directly answer what they're asking
- Provide specific details (amounts, dates, names, transaction IDs when relevant)
- If they want a list, mention the transactions you found
- If they want analysis, provide insights and patterns
- If they want summary, give overview with key statistics
- Use emojis moderately for friendliness
- Be accurate with numbers and facts
- Match the user's language style and tone

🎯 YOUR NATURAL, HELPFUL RESPONSE:""")

        def format_docs(docs):
            return "\n\n=== TRANSACTION ===\n\n".join(doc.page_content for doc in docs)

        rag_chain = (
            {
                "context": vectorstore.as_retriever(search_kwargs={"k": k_value}) | format_docs,
                "question": RunnablePassthrough()
            }
            | prompt_template
            | self.llm
            | StrOutputParser()
        )

        result = rag_chain.invoke(prompt)
        return result
