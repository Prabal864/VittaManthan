"""
Transaction query endpoints
"""

import re
import logging
from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    RAGRequest,
    IngestRequest,
    IngestResponse,
    PromptRequest,
    RAGResponse
)
from app.services.rag_service import RAGService
from app.utils.data_store import get_ingested_data, set_ingested_data, has_ingested_data
from app.utils.formatters import format_transaction_for_api
from app.utils.filters import extract_filters_from_query, apply_filters
from app.utils.query_mode import detect_query_mode
from app.utils.cache import generate_query_id, get_cached_query, cache_query_results

logger = logging.getLogger(__name__)

router = APIRouter()

# Global references to models (will be set by main app)
embeddings_model = None
llm = None


def set_models(emb_model, llm_model):
    """Set global model references"""
    global embeddings_model, llm
    embeddings_model = emb_model
    llm = llm_model


@router.post("/query", response_model=RAGResponse)
async def query_transactions(request: RAGRequest):
    """
    Main endpoint: Accept context data and prompt, return LLM response

    This endpoint:
    1. Receives transaction data (context_data) and user question (prompt)
    2. Creates vector embeddings from the transaction data
    3. Applies filters based on the question
    4. Uses LLM to generate natural language response
    5. Returns paginated results with statistics
    """
    if not embeddings_model or not llm:
        raise HTTPException(status_code=503, detail="Models not initialized")

    try:
        logger.info(f"Processing query: {request.prompt}")
        logger.info(f"Context data: {len(request.context_data)} transactions")

        # Initialize RAG service
        rag_service = RAGService(embeddings_model, llm)

        # Prepare documents
        documents = request.context_data

        # Create vector store
        logger.info("Creating vector store...")
        vectorstore, langchain_docs = rag_service.create_vector_store(documents)

        # Extract filters
        filters = extract_filters_from_query(request.prompt)
        logger.info(f"Extracted filters: {filters}")

        # Detect query mode
        mode = detect_query_mode(request.prompt, documents)
        if request.use_full_data is not None:
            mode = "SMART_FULL" if request.use_full_data else "VECTOR_SEARCH"

        logger.info(f"Query mode: {mode}")

        # Generate unique query ID
        query_id = generate_query_id(request.prompt, filters)

        # Prepare response
        response_data = {
            "query_id": query_id,
            "mode": mode,
            "matching_transactions_count": 0,
            "filters_applied": None,
            "answer": "",
            "transactions": None,
            "pagination": None,
            "statistics": None
        }

        # Process based on mode
        if mode == "STATISTICAL":
            answer, stats, filter_desc, match_count = rag_service.process_statistical_query(
                documents, request.prompt
            )
            response_data["answer"] = answer
            response_data["statistics"] = stats
            response_data["filters_applied"] = filter_desc
            response_data["matching_transactions_count"] = match_count

        elif mode == "SMART_FULL" or request.use_full_data:
            answer, filtered_docs, filter_descriptions = rag_service.process_smart_full_query(
                documents, request.prompt, request.show_all
            )
            response_data["matching_transactions_count"] = len(filtered_docs)
            response_data["filters_applied"] = filter_descriptions
            response_data["answer"] = answer

            # Paginate results
            if request.show_all and filtered_docs:
                sorted_docs = sorted(filtered_docs, key=lambda x: float(x.get('amount', 0)), reverse=True)

                start_idx = (request.page - 1) * request.page_size
                end_idx = start_idx + request.page_size
                paginated_docs = sorted_docs[start_idx:end_idx]

                response_data["transactions"] = [
                    format_transaction_for_api(doc) for doc in paginated_docs
                ]
                response_data["pagination"] = {
                    "page": request.page,
                    "page_size": request.page_size,
                    "total_items": len(filtered_docs),
                    "total_pages": (len(filtered_docs) + request.page_size - 1) // request.page_size,
                    "has_next": end_idx < len(filtered_docs),
                    "has_prev": request.page > 1
                }

        else:
            # Vector search mode
            # Check if it's analytical or counting query
            is_analytical = any(kw in request.prompt.lower() for kw in [
                'summarize', 'summarise', 'summary', 'analyze', 'analyse',
                'overview', 'insights', 'patterns', 'trends'
            ])

            counting_patterns = [
                r'\b(how many|kitne|count|total)\s+.*?transaction',
                r'transaction.*?\b(how many|kitne|count|total)',
                r'\b(कितने|कितनी)\s+.*?(transaction|ट्रांज)',
                r'(transaction|ट्रांज).*?\b(कितने|कितनी)',
                r'\bnumber of\s+transaction',
            ]
            is_counting_query = any(re.search(pattern, request.prompt.lower()) for pattern in counting_patterns)
            is_analytical = is_analytical or is_counting_query

            if is_analytical:
                result = rag_service.process_analytical_query(documents, request.prompt)
                response_data["answer"] = result
                response_data["matching_transactions_count"] = len(documents)
            else:
                # Specific query - use vector search
                k_value = min(50, len(documents))
                result = rag_service.process_vector_search_query(vectorstore, request.prompt, k_value)
                response_data["answer"] = result
                response_data["matching_transactions_count"] = k_value

        return RAGResponse(**response_data)

    except Exception as e:
        logger.error(f"Error processing query: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ingest", response_model=IngestResponse)
async def ingest_context_data(request: IngestRequest):
    """
    Ingest endpoint: Accept and store context data for later querying

    This endpoint:
    1. Receives transaction data (context_data)
    2. Creates vector embeddings from the transaction data
    3. Stores the vectorstore and documents in memory for later use
    4. Returns confirmation with timestamp
    """
    if not embeddings_model or not llm:
        raise HTTPException(status_code=503, detail="Models not initialized")

    try:
        logger.info(f"Ingesting context data: {len(request.context_data)} transactions")

        # Initialize RAG service
        rag_service = RAGService(embeddings_model, llm)

        # Create vector store
        vectorstore, langchain_docs = rag_service.create_vector_store(request.context_data)

        # Store in global state
        set_ingested_data(request.context_data, vectorstore, langchain_docs)

        ingested_data = get_ingested_data()

        return IngestResponse(
            status="success",
            message="Context data ingested successfully",
            transactions_ingested=len(request.context_data),
            timestamp=ingested_data["last_updated"]
        )

    except Exception as e:
        logger.error(f"Error ingesting context data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/prompt", response_model=RAGResponse)
async def query_with_prompt(request: PromptRequest):
    """
    Prompt endpoint: Accept only prompt and query against pre-ingested data

    This endpoint:
    1. Receives user question (prompt) only
    2. Uses previously ingested context data and vectorstore
    3. Applies filters based on the question
    4. Uses LLM to generate natural language response (ONLY ONCE per query)
    5. Caches results for pagination
    6. Returns paginated results with statistics

    For pagination:
    - First request (page=1): Generates answer with LLM and caches results
    - Subsequent requests (page>1 with same query_id): Returns cached answer with next page of transactions
    """
    if not embeddings_model or not llm:
        raise HTTPException(status_code=503, detail="Models not initialized")

    # Check if data has been ingested
    if not has_ingested_data():
        raise HTTPException(
            status_code=400,
            detail="No context data ingested. Please call /ingest endpoint first."
        )

    try:
        logger.info(f"Processing prompt query: {request.prompt}, page: {request.page}")

        # Get ingested data
        ingested_data = get_ingested_data()
        documents = ingested_data["transactions"]
        vectorstore = ingested_data["vectorstore"]

        logger.info(f"Using ingested data: {len(documents)} transactions")

        # Extract filters to generate/validate query_id
        filters = extract_filters_from_query(request.prompt)
        logger.info(f"Extracted filters: {filters}")

        # Generate or use provided query_id
        if request.query_id:
            query_id = request.query_id
            logger.info(f"Using provided query_id: {query_id}")
        else:
            query_id = generate_query_id(request.prompt, filters)
            logger.info(f"Generated new query_id: {query_id}")

        # Check cache for this query
        cached_data = get_cached_query(query_id)

        if cached_data and request.page > 1:
            # Use cached data for pagination
            logger.info(f"Using cached results for pagination (page {request.page})")

            mode = cached_data["mode"]
            answer = cached_data["answer"]
            filtered_docs = cached_data["filtered_docs"]
            filters_applied = cached_data["filters_applied"]
            statistics = cached_data.get("statistics")

            # Prepare response with cached data
            response_data = {
                "query_id": query_id,
                "mode": mode,
                "matching_transactions_count": len(filtered_docs),
                "filters_applied": filters_applied,
                "answer": answer,
                "transactions": None,
                "pagination": None,
                "statistics": statistics
            }

            # Paginate the cached filtered_docs
            if request.show_all and filtered_docs:
                sorted_docs = sorted(filtered_docs, key=lambda x: float(x.get('amount', 0)), reverse=True)

                start_idx = (request.page - 1) * request.page_size
                end_idx = start_idx + request.page_size
                paginated_docs = sorted_docs[start_idx:end_idx]

                response_data["transactions"] = [
                    format_transaction_for_api(doc) for doc in paginated_docs
                ]
                response_data["pagination"] = {
                    "page": request.page,
                    "page_size": request.page_size,
                    "total_items": len(filtered_docs),
                    "total_pages": (len(filtered_docs) + request.page_size - 1) // request.page_size,
                    "has_next": end_idx < len(filtered_docs),
                    "has_prev": request.page > 1
                }

            return RAGResponse(**response_data)

        # No cache or page 1 - process normally and cache results
        logger.info("Processing new query or page 1 - will generate LLM response and cache")

        # Initialize RAG service
        rag_service = RAGService(embeddings_model, llm)

        # Detect query mode
        mode = detect_query_mode(request.prompt, documents)
        if request.use_full_data is not None:
            mode = "SMART_FULL" if request.use_full_data else "VECTOR_SEARCH"

        logger.info(f"Query mode: {mode}")

        # Prepare response
        response_data = {
            "query_id": query_id,
            "mode": mode,
            "matching_transactions_count": 0,
            "filters_applied": None,
            "answer": "",
            "transactions": None,
            "pagination": None,
            "statistics": None
        }

        # Process based on mode
        if mode == "STATISTICAL":
            answer, stats, filter_desc, match_count = rag_service.process_statistical_query(
                documents, request.prompt
            )

            response_data["answer"] = answer
            response_data["statistics"] = stats
            response_data["filters_applied"] = filter_desc
            response_data["matching_transactions_count"] = match_count

            # Cache results
            filtered_docs, _ = apply_filters(documents, filters, request.prompt)
            cache_query_results(query_id, answer, mode, filtered_docs, filter_desc, stats)

        elif mode == "SMART_FULL" or request.use_full_data:
            answer, filtered_docs, filter_descriptions = rag_service.process_smart_full_query(
                documents, request.prompt, request.show_all
            )

            response_data["answer"] = answer
            response_data["matching_transactions_count"] = len(filtered_docs)
            response_data["filters_applied"] = filter_descriptions

            # Cache results
            cache_query_results(query_id, answer, mode, filtered_docs, filter_descriptions, None)

            # Paginate results
            if request.show_all and filtered_docs:
                sorted_docs = sorted(filtered_docs, key=lambda x: float(x.get('amount', 0)), reverse=True)

                start_idx = (request.page - 1) * request.page_size
                end_idx = start_idx + request.page_size
                paginated_docs = sorted_docs[start_idx:end_idx]

                response_data["transactions"] = [
                    format_transaction_for_api(doc) for doc in paginated_docs
                ]
                response_data["pagination"] = {
                    "page": request.page,
                    "page_size": request.page_size,
                    "total_items": len(filtered_docs),
                    "total_pages": (len(filtered_docs) + request.page_size - 1) // request.page_size,
                    "has_next": end_idx < len(filtered_docs),
                    "has_prev": request.page > 1
                }

        else:
            # Vector search mode
            is_analytical = any(kw in request.prompt.lower() for kw in [
                'summarize', 'summarise', 'summary', 'analyze', 'analyse',
                'overview', 'insights', 'patterns', 'trends'
            ])

            counting_patterns = [
                r'\b(how many|kitne|count|total)\s+.*?transaction',
                r'transaction.*?\b(how many|kitne|count|total)',
                r'\b(कितने|कितनी)\s+.*?(transaction|ट्रांज)',
                r'(transaction|ट्रांज).*?\b(कितने|कितनी)',
                r'\bnumber of\s+transaction',
            ]
            is_counting_query = any(re.search(pattern, request.prompt.lower()) for pattern in counting_patterns)
            is_analytical = is_analytical or is_counting_query

            if is_analytical:
                result = rag_service.process_analytical_query(documents, request.prompt)
                response_data["answer"] = result
                response_data["matching_transactions_count"] = len(documents)

                # Cache analytical result
                cache_query_results(query_id, result, mode, [], None, None)
            else:
                # Regular vector search
                k_value = min(50, len(documents))
                result = rag_service.process_vector_search_query(vectorstore, request.prompt, k_value)
                response_data["answer"] = result
                response_data["matching_transactions_count"] = k_value

        return RAGResponse(**response_data)

    except Exception as e:
        logger.error(f"Error processing prompt query: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
