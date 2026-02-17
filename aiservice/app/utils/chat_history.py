
from typing import List, Dict, Optional
import logging

try:
    from app.db.database import SessionLocal, ChatHistory
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

logger = logging.getLogger(__name__)


def save_chat_interaction(
    user_id: str,
    query: str,
    response: str,
    query_id: Optional[str] = None,
    mode: Optional[str] = None,
    matching_transactions_count: Optional[int] = None,
    filters_applied: Optional[List[str]] = None
):

    if not DB_AVAILABLE:
        logger.warning("⚠️ Database not available - chat history not saved")
        return

    db = SessionLocal()
    try:
        chat_entry = ChatHistory(
            user_id=user_id,
            query_id=query_id,
            query=query,
            response=response,
            mode=mode,
            matching_transactions_count=matching_transactions_count,
            filters_applied=filters_applied
        )
        db.add(chat_entry)
        db.commit()
        logger.info(f"💬 CHAT: Saved interaction for user '{user_id}' (query_id: {query_id})")

    except Exception as e:
        db.rollback()
        logger.error(f"❌ Failed to save chat history: {e}")
    finally:
        db.close()


def get_chat_history(
    user_id: str,
    limit: int = 50,
    offset: int = 0
) -> List[Dict]:

    if not DB_AVAILABLE:
        logger.warning("⚠️ Database not available - returning empty history")
        return []

    db = SessionLocal()
    try:
        chats = db.query(ChatHistory)\
            .filter_by(user_id=user_id)\
            .order_by(ChatHistory.timestamp.desc())\
            .limit(limit)\
            .offset(offset)\
            .all()

        history = [
            {
                "id": chat.id,
                "query_id": chat.query_id,
                "query": chat.query,
                "response": chat.response,
                "mode": chat.mode,
                "matching_transactions_count": chat.matching_transactions_count,
                "filters_applied": chat.filters_applied,
                "timestamp": chat.timestamp.isoformat()
            }
            for chat in chats
        ]

        logger.info(f"📖 Retrieved {len(history)} chat entries for user '{user_id}'")
        return history

    except Exception as e:
        logger.error(f"❌ Failed to retrieve chat history: {e}")
        return []
    finally:
        db.close()


def get_recent_queries(user_id: str, limit: int = 10) -> List[str]:

    if not DB_AVAILABLE:
        return []

    db = SessionLocal()
    try:
        queries = db.query(ChatHistory.query)\
            .filter_by(user_id=user_id)\
            .order_by(ChatHistory.timestamp.desc())\
            .limit(limit)\
            .all()

        return [q[0] for q in queries]

    except Exception as e:
        logger.error(f"❌ Failed to retrieve recent queries: {e}")
        return []
    finally:
        db.close()


def delete_chat_history(user_id: str):

    if not DB_AVAILABLE:
        logger.warning("⚠️ Database not available - cannot delete history")
        return

    db = SessionLocal()
    try:
        deleted_count = db.query(ChatHistory).filter_by(user_id=user_id).delete()
        db.commit()
        logger.info(f"🗑️ Deleted {deleted_count} chat entries for user '{user_id}'")

    except Exception as e:
        db.rollback()
        logger.error(f"❌ Failed to delete chat history: {e}")
    finally:
        db.close()


def get_chat_statistics(user_id: str) -> Dict:
    """
    Get statistics about user's chat history

    Args:
        user_id: User identifier

    Returns:
        Dictionary with statistics
    """
    if not DB_AVAILABLE:
        return {}

    db = SessionLocal()
    try:
        total_chats = db.query(ChatHistory).filter_by(user_id=user_id).count()

        # Get mode distribution
        mode_stats = {}
        modes = db.query(ChatHistory.mode)\
            .filter_by(user_id=user_id)\
            .filter(ChatHistory.mode.isnot(None))\
            .all()

        for mode in modes:
            mode_name = mode[0]
            mode_stats[mode_name] = mode_stats.get(mode_name, 0) + 1

        stats = {
            "total_interactions": total_chats,
            "mode_distribution": mode_stats,
            "user_id": user_id
        }

        logger.info(f"📊 Retrieved chat statistics for user '{user_id}': {total_chats} interactions")
        return stats

    except Exception as e:
        logger.error(f"❌ Failed to get chat statistics: {e}")
        return {}
    finally:
        db.close()
