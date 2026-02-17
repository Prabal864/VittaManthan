# Multi-stage Dockerfile for FastAPI RAG Service

# ============================================================================
# Stage 1: Builder - Install dependencies and create wheels
# ============================================================================
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements_api.txt .

# Create virtual environment and install dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip and install dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements_api.txt

# ============================================================================
# Stage 2: Runtime - Create minimal production image
# ============================================================================
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    # Hugging Face cache directory
    TRANSFORMERS_CACHE=/app/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/app/.cache/sentence_transformers

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/.cache/huggingface /app/.cache/sentence_transformers && \
    chown -R appuser:appuser /app

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY --chown=appuser:appuser app/ /app/app/
COPY --chown=appuser:appuser run.py /app/
COPY --chown=appuser:appuser .env /app/.env

# Switch to non-root user
USER appuser

# Pre-download the embedding model (optional but recommended for faster startup)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')" || true

# Expose port
EXPOSE 9000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:9000/ || exit 1

# Run the application
CMD ["python", "run.py"]
