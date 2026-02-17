"""
Main FastAPI Application
Transaction RAG Service with LLM-powered querying
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.services.embeddings import HuggingFaceEmbeddings
from app.services.llm import initialize_llm
from app.api import health, transactions

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global model instances
embeddings_model = None
llm = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan event handler for startup and shutdown
    """
    global embeddings_model, llm

    # Startup
    try:
        logger.info("Initializing embedding model...")
        embeddings_model = HuggingFaceEmbeddings(settings.EMBEDDING_MODEL)
        logger.info("✅ Embedding model initialized")

        logger.info("Initializing LLM...")
        llm = initialize_llm()
        logger.info("✅ LLM initialized")

        # Set models in routers
        health.set_models(embeddings_model, llm)
        transactions.set_models(embeddings_model, llm)

    except Exception as e:
        logger.error(f"Failed to initialize models: {e}")

    yield

    # Shutdown (cleanup if needed)
    logger.info("Shutting down...")


# Create FastAPI app
app = FastAPI(
    title=settings.APP_TITLE,
    description=settings.APP_DESCRIPTION,
    version=settings.APP_VERSION,
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOW_ORIGINS,
    allow_credentials=settings.ALLOW_CREDENTIALS,
    allow_methods=settings.ALLOW_METHODS,
    allow_headers=settings.ALLOW_HEADERS,
)

# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(transactions.router, tags=["Transactions"])
