import os

from pymongo import MongoClient
from pymongo.database import Database

_client: MongoClient | None = None


def get_db() -> Database:
    """Return the MongoDB database handle, creating the client on first use."""
    global _client
    if _client is None:
        uri = os.environ["MONGODB_URI"]
        _client = MongoClient(uri)
    db_name = os.environ.get("DB_NAME", "business_search")
    return _client[db_name]
