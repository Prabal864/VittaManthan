"""
Health check and status endpoints
"""

from fastapi import APIRouter
from app.utils.data_store import get_ingested_data

router = APIRouter()

# Global references to models (will be set by main app)
embeddings_model = None
llm = None


def set_models(emb_model, llm_model):
    """Set global model references"""
    global embeddings_model, llm
    embeddings_model = emb_model
    llm = llm_model


@router.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "online",
        "service": "Transaction RAG Service",
        "version": "1.0.0",
        "models_loaded": embeddings_model is not None and llm is not None
    }


@router.get("/status")
async def get_ingestion_status():
    """Check the status of ingested context data"""
    ingested_data = get_ingested_data()

    return {
        "data_ingested": len(ingested_data["transactions"]) > 0,
        "transactions_count": len(ingested_data["transactions"]),
        "last_updated": ingested_data["last_updated"],
        "vectorstore_ready": ingested_data["vectorstore"] is not None
    }


@router.post("/test-connection")
async def test_connection():
    """Test LLM connection"""
    if not llm:
        return {"status": "error", "error": "LLM not initialized"}

    try:
        response = llm.invoke("Say 'OK' if you're working")
        return {"status": "success", "response": response.content}
    except Exception as e:
        return {"status": "error", "error": str(e)}
