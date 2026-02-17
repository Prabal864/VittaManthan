# FastAPI Transaction RAG Service

A FastAPI-based RAG (Retrieval-Augmented Generation) service for querying transaction data using LLM.

## Project Structure

```
FastAPIProject1/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application entry point
│   ├── api/                    # API route handlers
│   │   ├── __init__.py
│   │   ├── health.py          # Health check endpoints
│   │   └── transactions.py    # Transaction query endpoints
│   ├── core/                  # Core configuration
│   │   ├── __init__.py
│   │   └── config.py          # Application settings
│   ├── models/                # Data models
│   │   ├── __init__.py
│   │   └── schemas.py         # Pydantic models
│   ├── services/              # Business logic services
│   │   ├── __init__.py
│   │   ├── embeddings.py      # Embedding model service
│   │   ├── llm.py             # LLM initialization
│   │   └── rag_service.py     # RAG processing service
│   └── utils/                 # Utility functions
│       ├── __init__.py
│       ├── answer_generator.py # Answer generation utilities
│       ├── cache.py           # Cache management
│       ├── data_store.py      # Data storage
│       ├── filters.py         # Filter extraction and application
│       ├── formatters.py      # Transaction formatting
│       └── query_mode.py      # Query mode detection
├── run.py                     # Application entry point
├── requirements_api.txt       # Python dependencies
└── README.md                  # This file
```

## Installation

1. Install dependencies:
```bash
pip install -r requirements_api.txt
```

2. Create a `.env` file with your OpenAI API key:
```
OPENAI_API_KEY=your_api_key_here
```

## Running the Application

Start the server:
```bash
python run.py
```

Or with uvicorn directly:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 9000 --reload
```

The API will be available at `http://localhost:9000`

## API Endpoints

- `GET /` - Health check
- `GET /status` - Check ingestion status
- `POST /test-connection` - Test LLM connection
- `POST /ingest` - Ingest transaction data
- `POST /query` - Query with context data
- `POST /prompt` - Query using pre-ingested data

## API Documentation

Interactive API documentation is available at:
- Swagger UI: `http://localhost:9000/docs`
- ReDoc: `http://localhost:9000/redoc`
