"""
Custom embeddings wrapper using HuggingFace sentence-transformers
"""

import logging
from typing import List

# Back-compat shim for sentence-transformers expecting huggingface_hub.cached_download
try:
    import huggingface_hub
    from huggingface_hub import hf_hub_download

    if not hasattr(huggingface_hub, "cached_download"):
        huggingface_hub.cached_download = hf_hub_download
except Exception:
    # If huggingface_hub is unavailable, let the downstream import fail normally.
    pass

from sentence_transformers import SentenceTransformer
from langchain_core.embeddings import Embeddings

logger = logging.getLogger(__name__)


class HuggingFaceEmbeddings(Embeddings):
    """Custom wrapper for HuggingFace embeddings"""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        logger.info(f"Loading embedding model: {model_name}")
        self.model = SentenceTransformer(model_name)
        logger.info("Embedding model loaded successfully")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self.model.encode(texts).tolist()

    def embed_query(self, text: str) -> List[float]:
        return self.model.encode([text])[0].tolist()
