import os
import threading

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database

load_dotenv()

_client: MongoClient | None = None
_client_lock = threading.Lock()


def get_db() -> Database:
    """Return the MongoDB database handle, creating the client on first use."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:  # re-check: another thread may have won the race
                uri = os.environ.get("MONGODB_URI")
                if not uri:
                    raise RuntimeError(
                        "MONGODB_URI is not set. Copy backend/.env.example to "
                        "backend/.env and fill in your Atlas connection string."
                    )
                _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    db_name = os.environ.get("DB_NAME", "business_search")
    return _client[db_name]
