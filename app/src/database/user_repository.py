import logging
from typing import Optional, Dict, Any
from datetime import datetime

from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError
from fastapi import HTTPException
from src.database.connection import get_db
from configs.config import get_config

logger = logging.getLogger(__name__)
cfg = get_config()


class UserRepository:
    """Repository for managing user documents in MongoDB."""

    def __init__(self):
        self._db = get_db()
        self._collection: Collection = self._db[cfg.USERS_COLLECTION]

    def create_user(
        self, 
        email: str, 
        hashed_password: Optional[str] = None, 
        google_id: Optional[str] = None,
        name: Optional[str] = None,
        picture: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new user. 
        Supports both traditional password registration and Google OAuth.
        """
        now = datetime.utcnow().isoformat()
        
        user_doc = {
            "email": email.lower(),
            "hashed_password": hashed_password,
            "google_id": google_id,
            "name": name,
            "picture": picture,
            "created_at": now,
            "updated_at": now
        }

        try:
            result = self._collection.insert_one(user_doc)
            user_doc["_id"] = str(result.inserted_id)
            return user_doc
        except DuplicateKeyError:
            logger.warning(f"Registration failed: User with email {email} already exists.")
            raise HTTPException(status_code=400, detail="Email already registered")

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Fetch a user by their email address."""
        user = self._collection.find_one({"email": email.lower()})
        if user:
            user["_id"] = str(user["_id"])
        return user

    def update_user_google_id(self, email: str, google_id: str, name: Optional[str] = None, picture: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Update an existing user (e.g., when they link a Google account)."""
        now = datetime.utcnow().isoformat()
        
        update_fields = {"google_id": google_id, "updated_at": now}
        if name:
            update_fields["name"] = name
        if picture:
            update_fields["picture"] = picture

        updated_user = self._collection.find_one_and_update(
            {"email": email.lower()},
            {"$set": update_fields},
            return_document=True
        )
        if updated_user:
            updated_user["_id"] = str(updated_user["_id"])
        return updated_user
