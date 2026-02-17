"""
Configuration settings for the application
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Settings:
    """Application settings"""

    # API Configuration
    APP_TITLE: str = "Transaction RAG Service"
    APP_DESCRIPTION: str = "LLM-powered transaction query service with multilingual support"
    APP_VERSION: str = "1.0.0"

    # Server Configuration
    HOST: str = "0.0.0.0"
    PORT: int = 9000
    RELOAD: bool = True

    # CORS Configuration
    ALLOW_ORIGINS: list = ["*"]
    ALLOW_CREDENTIALS: bool = True
    ALLOW_METHODS: list = ["*"]
    ALLOW_HEADERS: list = ["*"]

    # OpenAI/LLM Configuration
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL: str = "https://openrouter.ai/api/v1"

    # Free LLM models to try
    FREE_MODELS: list = [

        "openai/gpt-oss-120b",
        "meta-llama/llama-3.2-3b-instruct:free",
        "xiaomi/mimo-v2-flash:free",
        "microsoft/phi-3-mini-128k-instruct:free",
        "qwen/qwen-2-7b-instruct:free",
    ]

    # LLM Parameters
    LLM_TEMPERATURE: float = 0.8
    LLM_MAX_TOKENS: int = 3000
    LLM_TOP_P: float = 0.9
    LLM_FREQUENCY_PENALTY: float = 0.3
    LLM_PRESENCE_PENALTY: float = 0.3

    # Embedding Model
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Cache Configuration
    CACHE_TTL_MINUTES: int = 30


settings = Settings()
