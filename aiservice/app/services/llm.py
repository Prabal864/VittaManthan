"""
LLM initialization and management
"""

import os
import logging
import typing

# Back-compat shim for pydantic v1 under Python 3.12 (ForwardRef._evaluate signature change)
try:
    _orig_fr_evaluate = typing.ForwardRef._evaluate

    def _fr_evaluate(self, globalns, localns, *args, **kwargs):
        if args and "recursive_guard" not in kwargs:
            kwargs["recursive_guard"] = args[0]
            args = ()
        return _orig_fr_evaluate(self, globalns, localns, *args, **kwargs)

    typing.ForwardRef._evaluate = _fr_evaluate
except Exception:
    # If patching fails, allow the import to raise the original error.
    pass

from langchain_openai import ChatOpenAI
from app.core.config import settings

logger = logging.getLogger(__name__)


def initialize_llm() -> ChatOpenAI:
    """Initialize and return LLM instance"""

    for model in settings.FREE_MODELS:
        try:
            logger.info(f"Attempting to initialize LLM with model: {model}")
            llm = ChatOpenAI(
                model=model,
                base_url=settings.OPENAI_BASE_URL,
                api_key=settings.OPENAI_API_KEY,
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
                model_kwargs={
                    "top_p": settings.LLM_TOP_P,
                    "frequency_penalty": settings.LLM_FREQUENCY_PENALTY,
                    "presence_penalty": settings.LLM_PRESENCE_PENALTY
                }
            )
            logger.info(f"✅ LLM initialized successfully with model: {model}")
            return llm
        except Exception as e:
            logger.warning(f"Failed to initialize with model {model}: {e}")
            continue

    raise Exception("Failed to initialize LLM with any available model")
