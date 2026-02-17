"""
Database models and session management for PostgreSQL persistence
"""
from sqlalchemy import create_engine, Column, String, JSON, DateTime, Integer, Text, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
import logging

logger = logging.getLogger(__name__)

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/rag_db")

# Add SSL mode for cloud databases (DigitalOcean, AWS RDS, etc.)
# If URL doesn't have sslmode, add it
if "sslmode" not in DATABASE_URL and ("digitalocean.com" in DATABASE_URL or "rds.amazonaws" in DATABASE_URL):
    separator = "&" if "?" in DATABASE_URL else "?"
    DATABASE_URL = f"{DATABASE_URL}{separator}sslmode=require"

# Create engine
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Verify connections before using
    pool_size=10,         # Connection pool size
    max_overflow=20,      # Max overflow connections
    echo=False,           # Set to True for SQL debugging
    connect_args={"sslmode": "require"} if "digitalocean.com" in DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class UserData(Base):
    """
    Store user ingested data (transactions only - vectorstore rebuilt on load)
    Vectorstore is NOT stored due to size limitations (can be 100MB+)
    """
    __tablename__ = "user_data"

    user_id = Column(String, primary_key=True, index=True)
    transactions = Column(JSON, nullable=False)  # List of transaction dictionaries
    vectorstore_data = Column(Text, nullable=True, default="")  # Empty - vectorstore rebuilt from transactions
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)


class ChatHistory(Base):
    """
    Store chat history for each user
    Records all queries and responses for auditing and analytics
    """
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String, index=True, nullable=False)
    query_id = Column(String, index=True)  # Links to cached query
    query = Column(Text, nullable=False)  # User's question
    response = Column(Text, nullable=False)  # LLM's answer
    mode = Column(String)  # Query mode (ANALYTICAL, STATISTICAL, etc.)
    matching_transactions_count = Column(Integer)
    filters_applied = Column(JSON)  # List of filters
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)


def init_db():
    """
    Initialize database tables
    Creates tables if they don't exist
    """
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Database tables created successfully")

        # Log table info
        tables = Base.metadata.tables.keys()
        logger.info(f"📋 Available tables: {list(tables)}")

    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise


def get_db():
    """
    Dependency for getting database session
    Use this in FastAPI endpoints with Depends()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_connection():
    """
    Test database connection
    Returns True if connection successful
    """
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        logger.info("✅ Database connection successful")
        return True
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return False
