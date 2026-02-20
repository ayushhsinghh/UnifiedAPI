"""
MongoDB connection management.

Provides a singleton DatabaseManager and a convenience ``get_db()`` helper.
All collection indexes (including TTL) are configured on first connection.
"""

import logging
from typing import Optional

from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import ConnectionFailure

from configs.config import get_config

logger = logging.getLogger(__name__)

cfg = get_config()


class DatabaseManager:
    """Thread-safe singleton that owns the MongoClient."""

    _instance: Optional["DatabaseManager"] = None
    _client: Optional[MongoClient] = None
    _db: Optional[Database] = None

    def __new__(cls) -> "DatabaseManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if self._client is None:
            self.connect()

    # ── Connection ───────────────────────────────────────────────────────

    def connect(self) -> None:
        """Establish the MongoDB connection and create indexes."""
        try:
            self._client = MongoClient(
                cfg.MONGODB_URL, serverSelectionTimeoutMS=5000
            )
            self._client.admin.command("ping")
            self._db = self._client[cfg.DATABASE_NAME]
            logger.info("Connected to MongoDB at %s", cfg.MONGODB_URL)

            self._ensure_indexes()
            logger.info("Database indexes created / verified")
        except ConnectionFailure as exc:
            logger.error("Failed to connect to MongoDB: %s", exc)
            raise

    def get_db(self) -> Database:
        """Return the database handle, reconnecting if necessary."""
        if self._db is None:
            self.connect()
        return self._db

    def close(self) -> None:
        """Gracefully close the connection."""
        if self._client:
            self._client.close()
            logger.info("MongoDB connection closed")

    # ── Index helpers ────────────────────────────────────────────────────

    def _ensure_indexes(self) -> None:
        """Create all required indexes for the application."""
        db = self._db

        # Job indexes
        db[cfg.JOBS_COLLECTION].create_index("job_id", unique=True)
        db[cfg.JOBS_COLLECTION].create_index("created_at")

        # Game session indexes
        db[cfg.GAME_SESSIONS_COLLECTION].create_index(
            "session_id", unique=True
        )
        db[cfg.GAME_SESSIONS_COLLECTION].create_index("status")

        # Game player indexes
        db[cfg.GAME_PLAYERS_COLLECTION].create_index("session_id")
        db[cfg.GAME_PLAYERS_COLLECTION].create_index("player_id")
        db[cfg.GAME_PLAYERS_COLLECTION].create_index(
            [("session_id", 1), ("player_id", 1)], unique=True
        )

        # TTL indexes — auto-delete stale data
        self._setup_ttl_index(
            cfg.GAME_SESSIONS_COLLECTION,
            "created_at",
            expire_seconds=cfg.SESSION_TTL_SECONDS,
        )
        self._setup_ttl_index(
            cfg.GAME_PLAYERS_COLLECTION,
            "last_heartbeat",
            expire_seconds=cfg.PLAYER_TTL_SECONDS,
        )

    def _setup_ttl_index(
        self, collection_name: str, field: str, expire_seconds: int
    ) -> None:
        """Create a TTL index, dropping any conflicting index first."""
        coll = self._db[collection_name]
        try:
            for name, info in coll.index_information().items():
                keys = [k for k, _ in info["key"]]
                if keys == [field]:
                    if info.get("expireAfterSeconds") == expire_seconds:
                        return  # already correct
                    coll.drop_index(name)
                    logger.info(
                        "Dropped old index '%s' on %s.%s",
                        name, collection_name, field,
                    )
                    break
            coll.create_index(field, expireAfterSeconds=expire_seconds)
            logger.info(
                "TTL index on %s.%s (%ds) created",
                collection_name, field, expire_seconds,
            )
        except Exception as exc:
            logger.warning(
                "TTL index setup for %s.%s failed: %s",
                collection_name, field, exc,
            )


# ── Convenience function ─────────────────────────────────────────────────


def get_db() -> Database:
    """Shortcut to obtain the database handle."""
    return DatabaseManager().get_db()
