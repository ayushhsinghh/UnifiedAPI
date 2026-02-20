"""
Repository functions for the Guess-the-Imposter game.

Covers both *game_sessions* and *game_players* collections.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from configs.config import get_config
from src.database.connection import get_db

logger = logging.getLogger(__name__)

cfg = get_config()


# ═══════════════════════════════════════════════════════════════════════════
#  GAME SESSION OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════


def create_game_session(
    session_id: str,
    creator_id: str,
    game_category: str,
    player_topic: str,
    imposter_topic: str,
    max_players: int = 8,
) -> Dict:
    """Insert a new game session document."""
    db = get_db()
    session_document = {
        "session_id": session_id,
        "creator_id": creator_id,
        "game_category": game_category,
        "player_topic": player_topic,
        "imposter_topic": imposter_topic,
        "max_players": max_players,
        "status": "waiting",
        "players_list": [creator_id],
        "imposter_id": None,
        "discussion_time": cfg.GAME_DISCUSSION_TIME_SECONDS,
        "voting_time": cfg.GAME_VOTING_TIME_SECONDS,
        "current_phase": "waiting",
        "votes": {},
        "voters": [],
        "game_result": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "started_at": None,
        "ended_at": None,
    }
    db[cfg.GAME_SESSIONS_COLLECTION].insert_one(session_document)
    logger.info("Game session %s created by %s", session_id, creator_id)
    return session_document


def get_game_session(session_id: str) -> Optional[Dict]:
    """Retrieve a game session by its ID."""
    try:
        db = get_db()
        session = db[cfg.GAME_SESSIONS_COLLECTION].find_one(
            {"session_id": session_id}
        )
        if session:
            session.pop("_id", None)
            return session
        logger.warning("Game session %s not found", session_id)
        return None
    except Exception as exc:
        logger.error(
            "Error getting game session %s: %s", session_id, exc, exc_info=True
        )
        return None


def update_game_session(session_id: str, update_data: Dict) -> bool:
    """Apply a partial update to a game session."""
    try:
        db = get_db()
        update_data["updated_at"] = datetime.utcnow()
        result = db[cfg.GAME_SESSIONS_COLLECTION].update_one(
            {"session_id": session_id}, {"$set": update_data}
        )
        if result.modified_count > 0:
            logger.debug(
                "Game session %s updated with: %s", session_id, update_data
            )
            return True
        logger.warning("Game session %s update failed — no match", session_id)
        return False
    except Exception as exc:
        logger.error(
            "Error updating game session %s: %s",
            session_id, exc, exc_info=True,
        )
        return False


def add_player_to_session(session_id: str, player_id: str) -> bool:
    """Atomically add a player_id to the session's players_list."""
    try:
        db = get_db()
        result = db[cfg.GAME_SESSIONS_COLLECTION].update_one(
            {"session_id": session_id},
            {
                "$addToSet": {"players_list": player_id},
                "$set": {"updated_at": datetime.utcnow()},
            },
        )
        if result.modified_count > 0:
            logger.info(
                "Player %s added to session %s players_list",
                player_id, session_id,
            )
        else:
            logger.debug(
                "Player %s already in session %s players_list",
                player_id, session_id,
            )
        return True
    except Exception as exc:
        logger.error(
            "Error adding player %s to session %s: %s",
            player_id, session_id, exc, exc_info=True,
        )
        return False


def get_all_game_sessions(status: Optional[str] = None) -> List[Dict]:
    """Return all game sessions, optionally filtered by status."""
    db = get_db()
    query = {} if status is None else {"status": status}
    sessions = list(
        db[cfg.GAME_SESSIONS_COLLECTION].find(query).sort("created_at", -1)
    )
    for session in sessions:
        session.pop("_id", None)
    return sessions


def remove_game_session(session_id: str) -> bool:
    """Delete a game session and its associated players."""
    db = get_db()
    db[cfg.GAME_PLAYERS_COLLECTION].delete_many({"session_id": session_id})
    result = db[cfg.GAME_SESSIONS_COLLECTION].delete_one(
        {"session_id": session_id}
    )
    logger.info("Game session %s deleted", session_id)
    return result.deleted_count > 0


# ═══════════════════════════════════════════════════════════════════════════
#  GAME PLAYER OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════


def add_game_player(
    session_id: str,
    player_id: str,
    player_name: str,
    is_imposter: bool = False,
) -> Dict:
    """Insert a player document into the game_players collection."""
    db = get_db()
    player_document = {
        "session_id": session_id,
        "player_id": player_id,
        "player_name": player_name,
        "is_imposter": is_imposter,
        "is_alive": True,
        "votes_received": 0,
        "joined_at": datetime.utcnow(),
        "last_heartbeat": datetime.utcnow(),
    }
    db[cfg.GAME_PLAYERS_COLLECTION].insert_one(player_document)
    logger.info(
        "Player %s (%s) added to session %s",
        player_name, player_id, session_id,
    )
    return player_document


def update_player_heartbeat(session_id: str, player_id: str) -> bool:
    """Touch a player's heartbeat timestamp."""
    db = get_db()
    result = db[cfg.GAME_PLAYERS_COLLECTION].update_one(
        {"session_id": session_id, "player_id": player_id},
        {"$set": {"last_heartbeat": datetime.utcnow()}},
    )
    return result.modified_count > 0


def remove_inactive_players(
    session_id: str,
    timeout_seconds: Optional[int] = None,
) -> int:
    """
    Mark players inactive if their heartbeat is older than *timeout_seconds*,
    clean their votes, and remove them from the session players_list.

    Returns the number of players removed.
    """
    if timeout_seconds is None:
        timeout_seconds = cfg.HEARTBEAT_TIMEOUT_SECONDS

    db = get_db()
    cutoff = datetime.utcnow() - timedelta(seconds=timeout_seconds)

    inactive_cursor = db[cfg.GAME_PLAYERS_COLLECTION].find(
        {
            "session_id": session_id,
            "last_heartbeat": {"$lt": cutoff},
            "is_alive": True,
        }
    )
    inactive_ids = [p["player_id"] for p in inactive_cursor]

    if not inactive_ids:
        return 0

    # Mark as not alive
    db[cfg.GAME_PLAYERS_COLLECTION].update_many(
        {"session_id": session_id, "player_id": {"$in": inactive_ids}},
        {"$set": {"is_alive": False}},
    )

    # Clean up votes and players_list in the session document
    session = db[cfg.GAME_SESSIONS_COLLECTION].find_one(
        {"session_id": session_id}
    )
    if session:
        votes = session.get("votes", {})
        voters = session.get("voters", [])
        players_list = session.get("players_list", [])

        cleaned_votes = {
            k: v for k, v in votes.items() if k not in inactive_ids
        }
        cleaned_voters = [v for v in voters if v not in inactive_ids]
        cleaned_players_list = [
            p for p in players_list if p not in inactive_ids
        ]

        db[cfg.GAME_SESSIONS_COLLECTION].update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "votes": cleaned_votes,
                    "voters": cleaned_voters,
                    "players_list": cleaned_players_list,
                    "updated_at": datetime.utcnow(),
                }
            },
        )

    logger.info(
        "Marked %d inactive players in session %s: %s",
        len(inactive_ids), session_id, inactive_ids,
    )
    return len(inactive_ids)


def get_game_player(session_id: str, player_id: str) -> Optional[Dict]:
    """Retrieve a single player document."""
    db = get_db()
    player = db[cfg.GAME_PLAYERS_COLLECTION].find_one(
        {"session_id": session_id, "player_id": player_id}
    )
    if player:
        player.pop("_id", None)
    return player


def get_session_players(
    session_id: str, only_alive: bool = False
) -> List[Dict]:
    """Return all players in a session, optionally filtered to alive only."""
    db = get_db()
    query: Dict = {"session_id": session_id}
    if only_alive:
        query["is_alive"] = True
    players = list(db[cfg.GAME_PLAYERS_COLLECTION].find(query))
    for player in players:
        player.pop("_id", None)
    return players


def update_player_votes(
    session_id: str, player_id: str, votes_count: int
) -> bool:
    """Set the total votes received by a player."""
    db = get_db()
    result = db[cfg.GAME_PLAYERS_COLLECTION].update_one(
        {"session_id": session_id, "player_id": player_id},
        {"$set": {"votes_received": votes_count}},
    )
    return result.modified_count > 0


def mark_player_voted_out(session_id: str, player_id: str) -> bool:
    """Mark a player as voted out (is_alive = False)."""
    db = get_db()
    result = db[cfg.GAME_PLAYERS_COLLECTION].update_one(
        {"session_id": session_id, "player_id": player_id},
        {"$set": {"is_alive": False}},
    )
    return result.modified_count > 0


def remove_game_players(session_id: str) -> bool:
    """Delete all player documents for a session."""
    db = get_db()
    result = db[cfg.GAME_PLAYERS_COLLECTION].delete_many(
        {"session_id": session_id}
    )
    logger.info("All players removed from session %s", session_id)
    return result.deleted_count > 0
