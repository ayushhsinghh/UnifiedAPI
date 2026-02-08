"""
Game logic for "Guess the Imposter" game
Handles game sessions, player management, voting, and game outcomes
"""

import uuid
import random
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from database import (
    create_game_session, get_game_session, update_game_session,
    add_player_to_session, get_all_game_sessions,
    add_game_player, get_game_player, get_session_players,
    update_player_votes, mark_player_voted_out, remove_game_players,
    remove_game_session
)
from deepseek import generate_game_topics

logger = logging.getLogger(__name__)

# Game status constants
GAME_STATUS_WAITING = "waiting"
GAME_STATUS_PLAYING = "playing"
GAME_STATUS_VOTING = "voting"
GAME_STATUS_ENDED = "ended"

GAME_PHASE_DISCUSSION = "discussion"
GAME_PHASE_VOTING = "voting"
GAME_PHASE_RESULT = "result"

class GameManager:
    """Manages game sessions and game logic"""
    
    @staticmethod
    def generate_session_id() -> str:
        """Generate a unique session ID"""
        return str(uuid.uuid4())[:8].upper()
    
    @staticmethod
    def generate_player_id() -> str:
        """Generate a unique player ID"""
        return str(uuid.uuid4())
    
    @staticmethod
    def create_new_game(creator_id: str, creator_name: str, game_category: str, max_players: int = 8) -> Tuple[bool, Dict]:
        """
        Create a new game session
        
        Args:
            creator_id: ID of the player creating the game
            creator_name: Name of the creator
            game_category: Category for game topics
            max_players: Maximum number of players allowed
            
        Returns:
            Tuple of (success, response_dict)
        """
        try:
            # Generate topics using deepseek
            topics = generate_game_topics(game_category)
            player_topic = topics.get("player_topic", game_category)
            imposter_topic = topics.get("imposter_topic", f"{game_category} (variant)")
            
            # Create game session
            session_id = GameManager.generate_session_id()
            session = create_game_session(
                session_id=session_id,
                creator_id=creator_id,
                game_category=game_category,
                player_topic=player_topic,
                imposter_topic=imposter_topic,
                max_players=max_players
            )
            
            # Add creator as first player
            add_game_player(session_id, creator_id, creator_name, is_imposter=False)
            
            logger.info(f"New game created: {session_id} by {creator_name}")
            
            return True, {
                "success": True,
                "message": "Game created successfully",
                "session_id": session_id,
                "game_category": game_category,
                "max_players": max_players,
                "player_topic": player_topic,
                "imposter_topic": imposter_topic
            }
        except Exception as e:
            logger.error(f"Error creating game: {str(e)}")
            return False, {
                "success": False,
                "message": f"Error creating game: {str(e)}"
            }
    
    @staticmethod
    def join_game(session_id: str, player_id: str, player_name: str) -> Tuple[bool, Dict]:
        """
        Join an existing game session
        
        Args:
            session_id: ID of the session to join
            player_id: ID of the player
            player_name: Name of the player
            
        Returns:
            Tuple of (success, response_dict)
        """
        try:
            session = get_game_session(session_id)
            if not session:
                return False, {"success": False, "message": "Game session not found"}
            
            if session["status"] == GAME_STATUS_ENDED:
                return False, {"success": False, "message": "Game has ended"}
            
            if session["status"] == GAME_STATUS_PLAYING:
                return False, {"success": False, "message": "Game has already started"}
            
            if len(session["players_list"]) >= session["max_players"]:
                return False, {"success": False, "message": "Game is full"}
            
            # Check if player already in session
            existing_player = get_game_player(session_id, player_id)
            if existing_player:
                return False, {"success": False, "message": "Player already in this session"}
            
            # Add player to session
            add_player_to_session(session_id, player_id)
            add_game_player(session_id, player_id, player_name, is_imposter=False)
            
            logger.info(f"Player {player_name} joined session {session_id}")
            
            return True, {
                "success": True,
                "message": "Joined game successfully",
                "session_id": session_id,
                "game_category": session["game_category"],
                "player_count": len(session["players_list"]) + 1,
                "max_players": session["max_players"]
            }
        except Exception as e:
            logger.error(f"Error joining game: {str(e)}")
            return False, {"success": False, "message": f"Error joining game: {str(e)}"}
    
    @staticmethod
    def start_game(session_id: str) -> Tuple[bool, Dict]:
        """
        Start a game session - assign imposter and transition to playing state
        
        Args:
            session_id: ID of the session to start
            
        Returns:
            Tuple of (success, response_dict)
        """
        try:
            session = get_game_session(session_id)
            if not session:
                return False, {"success": False, "message": "Game session not found"}
            
            if len(session["players_list"]) < 2:
                return False, {"success": False, "message": "Need at least 2 players to start"}
            
            if session["status"] != GAME_STATUS_WAITING:
                return False, {"success": False, "message": "Game has already started"}
            
            # Randomly select imposter
            imposter_id = random.choice(session["players_list"])
            
            # Update imposter in game_players collection
            # First, mark all as non-imposter, then mark the selected one
            players = get_session_players(session_id)
            from database import DatabaseManager
            db = DatabaseManager().get_db()
            db["game_players"].update_many(
                {"session_id": session_id},
                {"$set": {"is_imposter": False}}
            )
            db["game_players"].update_one(
                {"session_id": session_id, "player_id": imposter_id},
                {"$set": {"is_imposter": True}}
            )
            
            # Update session
            update_game_session(session_id, {
                "status": GAME_STATUS_PLAYING,
                "current_phase": GAME_PHASE_DISCUSSION,
                "imposter_id": imposter_id,
                "started_at": datetime.utcnow()
            })
            
            logger.info(f"Game {session_id} started. Imposter: {imposter_id}")
            
            return True, {
                "success": True,
                "message": "Game started",
                "session_id": session_id,
                "game_status": GAME_STATUS_PLAYING,
                "imposter_assigned": True
            }
        except Exception as e:
            logger.error(f"Error starting game: {str(e)}")
            return False, {"success": False, "message": f"Error starting game: {str(e)}"}
    
    @staticmethod
    def get_game_info(session_id: str, player_id: Optional[str] = None) -> Tuple[bool, Dict]:
        """
        Get game information
        
        Args:
            session_id: ID of the session
            player_id: ID of the player requesting info (optional, to hide imposter topic)
            
        Returns:
            Tuple of (success, response_dict)
        """
        try:
            session = get_game_session(session_id)
            if not session:
                return False, {"success": False, "message": "Game session not found"}
            
            players = get_session_players(session_id)
            
            # Prepare response
            response = {
                "success": True,
                "session_id": session_id,
                "game_category": session["game_category"],
                "status": session["status"],
                "current_phase": session["current_phase"],
                "player_count": len(session["players_list"]),
                "max_players": session["max_players"],
                "discussion_time": session["discussion_time"],
                "voting_time": session["voting_time"],
                "players": []
            }
            
            # Add player information
            for player in players:
                player_info = {
                    "player_id": player["player_id"],
                    "player_name": player["player_name"],
                    "is_alive": player["is_alive"],
                    "votes_received": player["votes_received"]
                }
                response["players"].append(player_info)
            
            # Determine which topic to show
            if player_id and session["status"] == GAME_STATUS_PLAYING:
                player_data = get_game_player(session_id, player_id)
                if player_data and player_data["is_imposter"]:
                    response["your_topic"] = session["imposter_topic"]
                    response["topic_type"] = "imposter"
                else:
                    response["your_topic"] = session["player_topic"]
                    response["topic_type"] = "player"
            
            return True, response
        except Exception as e:
            logger.error(f"Error getting game info: {str(e)}")
            return False, {"success": False, "message": f"Error getting game info: {str(e)}"}
    
    @staticmethod
    def submit_vote(session_id: str, voter_id: str, voted_for_id: str) -> Tuple[bool, Dict]:
        """
        Submit a vote during voting phase
        
        Args:
            session_id: ID of the session
            voter_id: ID of the voting player
            voted_for_id: ID of the player being voted for
            
        Returns:
            Tuple of (success, response_dict)
        """
        try:
            session = get_game_session(session_id)
            if not session:
                return False, {"success": False, "message": "Game session not found"}
            
            if session["current_phase"] != GAME_PHASE_VOTING:
                return False, {"success": False, "message": "Not in voting phase"}
            
            # Check if voted player exists and is alive
            voted_player = get_game_player(session_id, voted_for_id)
            if not voted_player or not voted_player["is_alive"]:
                return False, {"success": False, "message": "Invalid vote target"}
            
            # Update votes
            votes = session.get("votes", {})
            votes[voter_id] = voted_for_id
            update_game_session(session_id, {"votes": votes})
            
            # Count votes for the voted player
            vote_count = sum(1 for v in votes.values() if v == voted_for_id)
            update_player_votes(session_id, voted_for_id, vote_count)
            
            logger.info(f"Player {voter_id} voted for {voted_for_id} in session {session_id}")
            
            return True, {
                "success": True,
                "message": "Vote registered"
            }
        except Exception as e:
            logger.error(f"Error submitting vote: {str(e)}")
            return False, {"success": False, "message": f"Error submitting vote: {str(e)}"}
    
    @staticmethod
    def end_voting(session_id: str) -> Tuple[bool, Dict]:
        """
        End voting phase and determine game result
        
        Args:
            session_id: ID of the session
            
        Returns:
            Tuple of (success, response_dict)
        """
        try:
            session = get_game_session(session_id)
            if not session:
                return False, {"success": False, "message": "Game session not found"}
            
            votes = session.get("votes", {})
            players = get_session_players(session_id)
            
            # Find player with most votes
            if not votes:
                return False, {"success": False, "message": "No votes recorded"}
            
            voted_out_id = max(votes.values(), key=lambda x: sum(v == x for v in votes.values()))
            voted_out_player = get_game_player(session_id, voted_out_id)
            
            if not voted_out_player:
                return False, {"success": False, "message": "Invalid vote outcome"}
            
            # Mark player as voted out
            mark_player_voted_out(session_id, voted_out_id)
            
            # Determine game result
            imposter_id = session["imposter_id"]
            is_imposter_caught = voted_out_id == imposter_id
            
            result = {
                "voted_out_id": voted_out_id,
                "voted_out_name": voted_out_player["player_name"],
                "is_imposter_caught": is_imposter_caught,
                "imposter_id": imposter_id
            }
            
            # Determine winners
            if is_imposter_caught:
                result["winners"] = "All other players"
                result["message"] = "Imposter caught!"
            else:
                result["winners"] = "Imposter"
                result["message"] = "Imposter escaped!"
            
            # Update session
            update_game_session(session_id, {
                "status": GAME_STATUS_ENDED,
                "current_phase": GAME_PHASE_RESULT,
                "game_result": result,
                "ended_at": datetime.utcnow()
            })
            
            logger.info(f"Game {session_id} ended. Result: {result}")
            
            return True, {
                "success": True,
                "message": "Voting ended",
                "game_result": result
            }
        except Exception as e:
            logger.error(f"Error ending voting: {str(e)}")
            return False, {"success": False, "message": f"Error ending voting: {str(e)}"}
    
    @staticmethod
    def transition_to_voting(session_id: str) -> Tuple[bool, Dict]:
        """
        Transition game from discussion to voting phase
        
        Args:
            session_id: ID of the session
            
        Returns:
            Tuple of (success, response_dict)
        """
        try:
            session = get_game_session(session_id)
            if not session:
                return False, {"success": False, "message": "Game session not found"}
            
            update_game_session(session_id, {
                "current_phase": GAME_PHASE_VOTING
            })
            
            logger.info(f"Game {session_id} transitioned to voting phase")
            
            return True, {
                "success": True,
                "message": "Game transitioned to voting phase",
                "current_phase": GAME_PHASE_VOTING
            }
        except Exception as e:
            logger.error(f"Error transitioning to voting: {str(e)}")
            return False, {"success": False, "message": f"Error transitioning to voting: {str(e)}"}
    
    @staticmethod
    def list_available_games() -> List[Dict]:
        """
        List all available games (waiting status)
        
        Returns:
            List of game sessions
        """
        try:
            sessions = get_all_game_sessions(status=GAME_STATUS_WAITING)
            games = []
            for session in sessions:
                games.append({
                    "session_id": session["session_id"],
                    "game_category": session["game_category"],
                    "player_count": len(session["players_list"]),
                    "max_players": session["max_players"],
                    "created_at": session["created_at"].isoformat() if isinstance(session["created_at"], datetime) else session["created_at"]
                })
            return games
        except Exception as e:
            logger.error(f"Error listing games: {str(e)}")
            return []
    
    @staticmethod
    def delete_game(session_id: str) -> Tuple[bool, Dict]:
        """
        Delete a game session
        
        Args:
            session_id: ID of the session
            
        Returns:
            Tuple of (success, response_dict)
        """
        try:
            remove_game_players(session_id)
            remove_game_session(session_id)
            
            logger.info(f"Game {session_id} deleted")
            
            return True, {"success": True, "message": "Game deleted"}
        except Exception as e:
            logger.error(f"Error deleting game: {str(e)}")
            return False, {"success": False, "message": f"Error deleting game: {str(e)}"}
