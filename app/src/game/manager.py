"""
Game manager for the Guess-the-Imposter game.

Orchestrates game lifecycle: creation, joining, starting, voting,
round management, and cleanup.
"""

import logging
import random
import string
import threading
import uuid
from collections import Counter
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from configs.config import get_config
from src.database.connection import get_db
from src.database.game_repository import (
    add_game_player,
    add_player_to_session,
    create_game_session,
    get_all_game_sessions,
    get_game_player,
    get_game_session,
    get_session_players,
    mark_player_voted_out,
    remove_game_players,
    remove_game_session,
    remove_inactive_players,
    update_game_session,
    update_player_heartbeat,
    update_player_votes,
)
from src.game.constants import (
    GAME_PHASE_DISCUSSION,
    GAME_PHASE_RESULT,
    GAME_PHASE_REVEAL,
    GAME_PHASE_VOTING,
    GAME_STATUS_ENDED,
    GAME_STATUS_PLAYING,
    GAME_STATUS_WAITING,
    PLACEHOLDER_IMPOSTER_TOPIC,
    PLACEHOLDER_PLAYER_TOPIC,
)
from src.game.topic_generator import generate_game_topics

logger = logging.getLogger(__name__)

cfg = get_config()


class GameManager:
    """Static-method-based manager for game sessions."""

    # ── ID generators ────────────────────────────────────────────────────

    @staticmethod
    def generate_session_id() -> str:
        """Return a unique 5-character alphanumeric session ID."""
        return "".join(
            random.choices(string.ascii_uppercase + string.digits, k=5)
        )

    @staticmethod
    def generate_player_id() -> str:
        """Return a UUID-based player ID."""
        return str(uuid.uuid4())

    # ── Background topic generation ──────────────────────────────────────

    @staticmethod
    def _generate_topics_background(
        session_id: str,
        game_category: str,
        previous_player_topic: Optional[str] = None,
        previous_imposter_topic: Optional[str] = None,
    ) -> None:
        """Background thread: call Gemini and write topics back to DB."""
        try:
            topics = generate_game_topics(
                game_category,
                previous_player_topic=previous_player_topic,
                previous_imposter_topic=previous_imposter_topic,
            )
            player_topic = topics.get("player_topic", game_category)
            imposter_topic = topics.get(
                "imposter_topic", f"{game_category} (variant)"
            )
            update_game_session(session_id, {
                "player_topic": player_topic,
                "imposter_topic": imposter_topic,
                "topics_ready": True,
            })
            logger.info(
                "Topics ready for session %s: %s / %s",
                session_id, player_topic, imposter_topic,
            )
        except Exception as exc:
            logger.error(
                "Background topic generation failed for %s: %s",
                session_id, exc,
            )
            update_game_session(session_id, {
                "player_topic": game_category,
                "imposter_topic": f"{game_category} (variant)",
                "topics_ready": True,
            })

    @staticmethod
    def _start_topic_thread(
        session_id: str,
        game_category: str,
        previous_player_topic: Optional[str] = None,
        previous_imposter_topic: Optional[str] = None,
    ) -> None:
        """Fire a daemon thread for topic generation."""
        thread = threading.Thread(
            target=GameManager._generate_topics_background,
            args=(
                session_id,
                game_category,
                previous_player_topic,
                previous_imposter_topic,
            ),
            daemon=True,
        )
        thread.start()

    # ── Game lifecycle ───────────────────────────────────────────────────

    @staticmethod
    def create_new_game(
        creator_id: str,
        creator_name: str,
        game_category: str,
        max_players: int = 8,
    ) -> Tuple[bool, Dict]:
        """Create a new game session (topics generated in background)."""
        try:
            session_id = GameManager.generate_session_id()
            create_game_session(
                session_id=session_id,
                creator_id=creator_id,
                game_category=game_category,
                player_topic=PLACEHOLDER_PLAYER_TOPIC,
                imposter_topic=PLACEHOLDER_IMPOSTER_TOPIC,
                max_players=max_players,
            )
            update_game_session(session_id, {"topics_ready": False})
            add_game_player(
                session_id, creator_id, creator_name, is_imposter=False
            )

            GameManager._start_topic_thread(session_id, game_category)

            logger.info(
                "New game created: %s by %s (topics generating)",
                session_id, creator_name,
            )
            return True, {
                "success": True,
                "message": "Game created successfully",
                "session_id": session_id,
                "game_category": game_category,
                "max_players": max_players,
            }
        except Exception as exc:
            logger.error("Error creating game: %s", exc)
            return False, {
                "success": False,
                "message": f"Error creating game: {exc}",
            }

    @staticmethod
    def join_game(
        session_id: str, player_id: str, player_name: str
    ) -> Tuple[bool, Dict]:
        """Join an existing game session."""
        try:
            session = get_game_session(session_id)
            if not session:
                return False, {
                    "success": False,
                    "message": "Game session not found",
                }

            if session["status"] == GAME_STATUS_ENDED:
                return False, {
                    "success": False, "message": "Game has ended"
                }

            if session["status"] == GAME_STATUS_PLAYING:
                return False, {
                    "success": False, "message": "Game has already started"
                }

            if len(session["players_list"]) >= session["max_players"]:
                return False, {"success": False, "message": "Game is full"}

            if get_game_player(session_id, player_id):
                return False, {
                    "success": False,
                    "message": "Player already in this session",
                }

            add_player_to_session(session_id, player_id)
            add_game_player(
                session_id, player_id, player_name, is_imposter=False
            )

            logger.info(
                "Player %s joined session %s", player_name, session_id
            )
            return True, {
                "success": True,
                "message": "Joined game successfully",
                "session_id": session_id,
                "game_category": session["game_category"],
                "player_count": len(session["players_list"]) + 1,
                "max_players": session["max_players"],
            }
        except Exception as exc:
            logger.error("Error joining game: %s", exc)
            return False, {
                "success": False, "message": f"Error joining game: {exc}"
            }

    @staticmethod
    def start_game(
        session_id: str, player_id: str
    ) -> Tuple[bool, Dict]:
        """Start a game session — assign imposter and enter discussion."""
        try:
            session = get_game_session(session_id)
            if not session:
                return False, {
                    "success": False,
                    "message": "Game session not found",
                }

            if session["creator_id"] != player_id:
                return False, {
                    "success": False,
                    "message": "Only the creator can start the game",
                }

            if len(session["players_list"]) < 2:
                return False, {
                    "success": False,
                    "message": "Need at least 2 players to start",
                }

            if session["status"] != GAME_STATUS_WAITING:
                return False, {
                    "success": False,
                    "message": "Game has already started",
                }

            if not session.get("topics_ready", True):
                return False, {
                    "success": False,
                    "message": (
                        "Topics are still being generated, please wait"
                    ),
                }

            imposter_id = random.choice(session["players_list"])
            _assign_imposter(session_id, imposter_id)

            update_game_session(session_id, {
                "status": GAME_STATUS_PLAYING,
                "current_phase": GAME_PHASE_DISCUSSION,
                "imposter_id": imposter_id,
                "started_at": datetime.utcnow(),
            })

            logger.info(
                "Game %s started. Imposter: %s", session_id, imposter_id
            )
            return True, {
                "success": True,
                "message": "Game started",
                "session_id": session_id,
                "game_status": GAME_STATUS_PLAYING,
                "imposter_assigned": True,
            }
        except Exception as exc:
            logger.error("Error starting game: %s", exc)
            return False, {
                "success": False, "message": f"Error starting game: {exc}"
            }

    @staticmethod
    def get_game_info(
        session_id: str, player_id: Optional[str] = None
    ) -> Tuple[bool, Dict]:
        """Return current game state, customised per player."""
        try:
            session = get_game_session(session_id)
            if not session:
                return False, {
                    "success": False,
                    "message": "Game session not found",
                }

            if player_id:
                update_player_heartbeat(session_id, player_id)

            # Auto-clean inactive players in live phases
            if session["status"] in (
                GAME_STATUS_WAITING, GAME_STATUS_PLAYING
            ):
                removed = remove_inactive_players(session_id)
                if removed > 0:
                    session = get_game_session(session_id)

            players = get_session_players(session_id, only_alive=False)

            response: Dict = {
                "success": True,
                "session_id": session_id,
                "game_category": session["game_category"],
                "status": session["status"],
                "current_phase": session["current_phase"],
                "player_count": len(session["players_list"]),
                "max_players": session["max_players"],
                "discussion_time": session["discussion_time"],
                "voting_time": session["voting_time"],
                "voters": session.get("voters", []),
                "topics_ready": session.get("topics_ready", True),
                "players": [
                    {
                        "player_id": p["player_id"],
                        "player_name": p["player_name"],
                        "is_alive": p["is_alive"],
                        "votes_received": p["votes_received"],
                    }
                    for p in players
                ],
            }

            reveal_at = session.get("reveal_at")
            if reveal_at:
                response["reveal_at"] = reveal_at.isoformat()

            # Show the appropriate topic to each player
            if player_id and session["status"] == GAME_STATUS_PLAYING:
                player_data = get_game_player(session_id, player_id)
                if player_data and player_data["is_imposter"]:
                    response["your_topic"] = session["imposter_topic"]
                    response["topic_type"] = "imposter"
                else:
                    response["your_topic"] = session["player_topic"]
                    response["topic_type"] = "player"

            return True, response
        except Exception as exc:
            logger.error("Error getting game info: %s", exc)
            return False, {
                "success": False,
                "message": f"Error getting game info: {exc}",
            }

    # ── Voting ───────────────────────────────────────────────────────────

    @staticmethod
    def submit_vote(
        session_id: str, voter_id: str, voted_for_id: str
    ) -> Tuple[bool, Dict]:
        """Register a vote during the voting phase."""
        try:
            session = get_game_session(session_id)
            if not session:
                return False, {
                    "success": False,
                    "message": "Game session not found",
                }

            if session["current_phase"] != GAME_PHASE_VOTING:
                return False, {
                    "success": False, "message": "Not in voting phase"
                }

            if voter_id in session.get("voters", []):
                return False, {
                    "success": False, "message": "You have already voted"
                }

            voted_player = get_game_player(session_id, voted_for_id)
            if not voted_player or not voted_player["is_alive"]:
                return False, {
                    "success": False, "message": "Invalid vote target"
                }

            votes = session.get("votes", {})
            voters = session.get("voters", [])
            votes[voter_id] = voted_for_id
            voters.append(voter_id)
            update_game_session(
                session_id, {"votes": votes, "voters": voters}
            )

            vote_count = sum(1 for v in votes.values() if v == voted_for_id)
            update_player_votes(session_id, voted_for_id, vote_count)

            logger.info(
                "Player %s voted for %s in session %s",
                voter_id, voted_for_id, session_id,
            )

            # Auto-end voting if everyone has voted
            alive_players = get_session_players(session_id, only_alive=True)
            if len(voters) == len(alive_players):
                return GameManager.end_voting(session_id)

            return True, {"success": True, "message": "Vote registered"}
        except Exception as exc:
            logger.error("Error submitting vote: %s", exc)
            return False, {
                "success": False,
                "message": f"Error submitting vote: {exc}",
            }

    @staticmethod
    def end_voting(session_id: str) -> Tuple[bool, Dict]:
        """End the voting phase and transition to reveal."""
        try:
            session = get_game_session(session_id)
            if not session:
                return False, {
                    "success": False,
                    "message": "Game session not found",
                }

            if session["current_phase"] != GAME_PHASE_VOTING:
                return False, {
                    "success": False, "message": "Not in voting phase"
                }

            update_game_session(
                session_id, {"current_phase": GAME_PHASE_REVEAL}
            )
            logger.info(
                "Game %s voting ended. Ready for reveal.", session_id
            )
            return True, {
                "success": True,
                "message": "Voting ended. Ready for reveal.",
            }
        except Exception as exc:
            logger.error("Error ending voting: %s", exc)
            return False, {
                "success": False,
                "message": f"Error ending voting: {exc}",
            }

    @staticmethod
    def transition_to_voting(session_id: str) -> Tuple[bool, Dict]:
        """Move the game from discussion to the voting phase."""
        try:
            session = get_game_session(session_id)
            if not session:
                return False, {
                    "success": False,
                    "message": "Game session not found",
                }

            update_game_session(
                session_id, {"current_phase": GAME_PHASE_VOTING}
            )
            logger.info(
                "Game %s transitioned to voting phase", session_id
            )
            return True, {
                "success": True,
                "message": "Game transitioned to voting phase",
                "current_phase": GAME_PHASE_VOTING,
            }
        except Exception as exc:
            logger.error("Error transitioning to voting: %s", exc)
            return False, {
                "success": False,
                "message": f"Error transitioning to voting: {exc}",
            }

    # ── Results ──────────────────────────────────────────────────────────

    @staticmethod
    def get_game_result(session_id: str) -> Tuple[bool, Dict]:
        """Tally votes and determine the game outcome."""
        try:
            session = get_game_session(session_id)
            if not session:
                return False, {
                    "success": False,
                    "message": "Game session not found",
                }

            if session["current_phase"] == GAME_PHASE_RESULT:
                players = get_session_players(session_id, only_alive=False)
                return True, {
                    "success": True,
                    "message": "Game has already ended",
                    "game_result": session["game_result"],
                    "players": players,
                }

            if session["current_phase"] != GAME_PHASE_REVEAL:
                return False, {
                    "success": False,
                    "message": "Results are not ready to be revealed",
                }

            votes = session.get("votes", {})
            if not votes:
                return False, {
                    "success": False, "message": "No votes recorded"
                }

            result = _tally_votes(session_id, session, votes)
            if result is None:
                return False, {
                    "success": False, "message": "Invalid vote outcome"
                }

            update_game_session(session_id, {
                "status": GAME_STATUS_ENDED,
                "current_phase": GAME_PHASE_RESULT,
                "game_result": result,
                "ended_at": datetime.utcnow(),
            })

            logger.info("Game %s ended. Result: %s", session_id, result)
            players = get_session_players(session_id, only_alive=False)
            return True, {
                "success": True,
                "message": "Voting ended",
                "game_result": result,
                "players": players,
            }
        except Exception as exc:
            logger.error("Error getting game result: %s", exc)
            return False, {
                "success": False,
                "message": f"Error getting game result: {exc}",
            }

    # ── Rounds ───────────────────────────────────────────────────────────

    @staticmethod
    def new_round(session_id: str) -> Tuple[bool, Dict]:
        """Start a new round (topics generated in background)."""
        try:
            session = get_game_session(session_id)
            if not session:
                return False, {
                    "success": False,
                    "message": "Game session not found",
                }

            prev_player = session.get("player_topic")
            prev_imposter = session.get("imposter_topic")
            game_category = session["game_category"]

            imposter_id = random.choice(session["players_list"])

            update_game_session(session_id, {
                "status": GAME_STATUS_PLAYING,
                "current_phase": GAME_PHASE_DISCUSSION,
                "imposter_id": imposter_id,
                "player_topic": PLACEHOLDER_PLAYER_TOPIC,
                "imposter_topic": PLACEHOLDER_IMPOSTER_TOPIC,
                "topics_ready": False,
                "votes": {},
                "voters": [],
                "game_result": None,
                "started_at": datetime.utcnow(),
                "ended_at": None,
                "reveal_at": None,
            })

            _reset_players_for_new_round(session_id, imposter_id)

            GameManager._start_topic_thread(
                session_id, game_category, prev_player, prev_imposter
            )

            logger.info(
                "New round for game %s. Imposter: %s (topics generating)",
                session_id, imposter_id,
            )
            return True, {
                "success": True, "message": "New round started"
            }
        except Exception as exc:
            logger.error("Error starting new round: %s", exc)
            return False, {
                "success": False,
                "message": f"Error starting new round: {exc}",
            }

    # ── Listing & cleanup ────────────────────────────────────────────────

    @staticmethod
    def list_available_games() -> List[Dict]:
        """Return waiting games created in the last N minutes."""
        try:
            sessions = get_all_game_sessions(status=GAME_STATUS_WAITING)
            cutoff = datetime.utcnow() - timedelta(
                minutes=cfg.AVAILABLE_GAME_WINDOW_MINUTES
            )
            return [
                {
                    "session_id": s["session_id"],
                    "game_category": s["game_category"],
                    "player_count": len(s["players_list"]),
                    "max_players": s["max_players"],
                    "created_at": s["created_at"].isoformat(),
                }
                for s in sessions
                if s["created_at"] > cutoff
            ]
        except Exception as exc:
            logger.error("Error listing games: %s", exc)
            return []

    @staticmethod
    def delete_old_games() -> Tuple[bool, Dict]:
        """Delete waiting games older than the configured threshold."""
        try:
            sessions = get_all_game_sessions(status=GAME_STATUS_WAITING)
            cutoff = datetime.utcnow() - timedelta(
                minutes=cfg.OLD_GAME_THRESHOLD_MINUTES
            )
            deleted_count = 0
            for session in sessions:
                if session["created_at"] < cutoff:
                    remove_game_players(session["session_id"])
                    remove_game_session(session["session_id"])
                    deleted_count += 1
            logger.info("Deleted %d old game sessions", deleted_count)
            return True, {
                "success": True, "deleted_count": deleted_count
            }
        except Exception as exc:
            logger.error("Error deleting old games: %s", exc)
            return False, {
                "success": False,
                "message": f"Error deleting old games: {exc}",
            }

    @staticmethod
    def delete_game(session_id: str) -> Tuple[bool, Dict]:
        """Delete a specific game session and its players."""
        try:
            remove_game_players(session_id)
            remove_game_session(session_id)
            logger.info("Game %s deleted", session_id)
            return True, {"success": True, "message": "Game deleted"}
        except Exception as exc:
            logger.error("Error deleting game: %s", exc)
            return False, {
                "success": False,
                "message": f"Error deleting game: {exc}",
            }


# ══════════════════════════════════════════════════════════════════════════
#  MODULE-LEVEL HELPERS (private)
# ══════════════════════════════════════════════════════════════════════════


def _assign_imposter(session_id: str, imposter_id: str) -> None:
    """Mark all players as non-imposter, then flag the chosen one."""
    db = get_db()
    db[cfg.GAME_PLAYERS_COLLECTION].update_many(
        {"session_id": session_id}, {"$set": {"is_imposter": False}}
    )
    db[cfg.GAME_PLAYERS_COLLECTION].update_one(
        {"session_id": session_id, "player_id": imposter_id},
        {"$set": {"is_imposter": True}},
    )


def _reset_players_for_new_round(
    session_id: str, imposter_id: str
) -> None:
    """Reset all player states for a fresh round."""
    db = get_db()
    db[cfg.GAME_PLAYERS_COLLECTION].update_many(
        {"session_id": session_id},
        {"$set": {"is_imposter": False, "is_alive": True, "votes_received": 0}},
    )
    db[cfg.GAME_PLAYERS_COLLECTION].update_one(
        {"session_id": session_id, "player_id": imposter_id},
        {"$set": {"is_imposter": True}},
    )


def _tally_votes(
    session_id: str, session: Dict, votes: Dict
) -> Optional[Dict]:
    """Count votes, mark players out, and build the result dict."""
    vote_counts = Counter(votes.values())
    max_votes = max(vote_counts.values())
    tied_ids = [
        pid for pid, count in vote_counts.items() if count == max_votes
    ]

    voted_out_ids: List[str] = []
    voted_out_names: List[str] = []
    for pid in tied_ids:
        player = get_game_player(session_id, pid)
        if not player:
            continue
        mark_player_voted_out(session_id, pid)
        voted_out_ids.append(pid)
        voted_out_names.append(player["player_name"])

    if not voted_out_ids:
        return None

    imposter_id = session["imposter_id"]
    is_imposter_caught = imposter_id in voted_out_ids

    result: Dict = {
        "voted_out_ids": voted_out_ids,
        "voted_out_names": voted_out_names,
        "voted_out_id": voted_out_ids[0],
        "voted_out_name": voted_out_names[0],
        "is_tie": len(voted_out_ids) > 1,
        "is_imposter_caught": is_imposter_caught,
        "imposter_id": imposter_id,
    }

    if is_imposter_caught:
        result["winners"] = "All other players"
        result["message"] = "Imposter caught!"
    elif len(voted_out_ids) > 1:
        result["winners"] = "Imposter"
        result["message"] = (
            f"Tie! {', '.join(voted_out_names)} were all voted out, "
            "but the imposter was not among them. Imposter wins!"
        )
    else:
        result["winners"] = "Imposter"
        result["message"] = "Imposter escaped!"

    return result
