import logging
from datetime import datetime, timedelta
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# MongoDB connection settings
MONGODB_URL = "mongodb://localhost:27017"
DATABASE_NAME = "video_transcriber"
JOBS_COLLECTION = "jobs"
GAME_SESSIONS_COLLECTION = "game_sessions"
GAME_PLAYERS_COLLECTION = "game_players"

class DatabaseManager:
    _instance = None
    _client = None
    _db = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._client is None:
            self.connect()
    
    def connect(self):
        """Connect to MongoDB"""
        try:
            self._client = MongoClient(MONGODB_URL, serverSelectionTimeoutMS=5000)
            # Verify connection
            self._client.admin.command('ping')
            self._db = self._client[DATABASE_NAME]
            logger.info(f"Connected to MongoDB at {MONGODB_URL}")
            
            # Create indexes for efficient querying
            self._db[JOBS_COLLECTION].create_index("job_id", unique=True)
            self._db[JOBS_COLLECTION].create_index("created_at")
            
            # Create indexes for game collections
            self._db[GAME_SESSIONS_COLLECTION].create_index("session_id", unique=True)
            self._db[GAME_SESSIONS_COLLECTION].create_index("created_at")
            self._db[GAME_SESSIONS_COLLECTION].create_index("status")
            
            self._db[GAME_PLAYERS_COLLECTION].create_index("session_id")
            self._db[GAME_PLAYERS_COLLECTION].create_index("player_id")
            self._db[GAME_PLAYERS_COLLECTION].create_index([("session_id", 1), ("player_id", 1)], unique=True)
            
            logger.info("Database indexes created/verified")
        except ConnectionFailure as e:
            logger.error(f"Failed to connect to MongoDB: {str(e)}")
            raise
    
    def get_db(self):
        """Get database instance"""
        if self._db is None:
            self.connect()
        return self._db
    
    def close(self):
        """Close database connection"""
        if self._client:
            self._client.close()
            logger.info("MongoDB connection closed")

def get_db():
    """Convenience function to get database"""
    manager = DatabaseManager()
    return manager.get_db()

def create_job(job_id: str, job_data: Dict) -> Dict:
    """Create a new job in MongoDB"""
    db = get_db()
    job_document = {
        "job_id": job_id,
        "status": job_data["status"],
        "video": job_data["video"],
        "audio": job_data["audio"],
        "srt": job_data["srt"],
        "translate": job_data.get("translate", False),
        "language": job_data.get("language"),
        "model": job_data.get("model", "medium"),
        "detected_language": None,
        "total_segments": 0,
        "completed_segments": 0,
        "progress_percentage": 0,
        "error": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    result = db[JOBS_COLLECTION].insert_one(job_document)
    logger.debug(f"Job {job_id} created in MongoDB")
    return job_document

def get_job(job_id: str) -> Optional[Dict]:
    """Get a job from MongoDB"""
    try:
        db = get_db()
        job = db[JOBS_COLLECTION].find_one({"job_id": job_id})
        if job:
            # Remove MongoDB's internal _id field for cleaner response
            job.pop("_id", None)
            logger.debug(f"Job {job_id} retrieved from MongoDB")
            return job
        else:
            logger.warning(f"Job {job_id} not found in MongoDB")
            return None
    except Exception as e:
        logger.error(f"Error getting job {job_id} from MongoDB: {str(e)}", exc_info=True)
        return None

def update_job_status(job_id: str, status: str) -> bool:
    """Update job status in MongoDB"""
    try:
        db = get_db()
        result = db[JOBS_COLLECTION].update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "status": status,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        if result.modified_count > 0:
            logger.info(f"Job {job_id} status updated to {status}")
            return True
        else:
            logger.warning(f"Job {job_id} status update to {status} failed - no documents matched")
            return False
    except Exception as e:
        logger.error(f"Error updating job status for {job_id}: {str(e)}", exc_info=True)
        return False

def update_job_progress(job_id: str, completed_segments: int, progress_percentage: int) -> bool:
    """Update job progress in MongoDB"""
    db = get_db()
    # Ensure progress_percentage is between 0 and 100
    progress_percentage = max(0, min(progress_percentage, 100))
    
    try:
        result = db[JOBS_COLLECTION].update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "completed_segments": completed_segments,
                    "progress_percentage": progress_percentage,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        if result.modified_count > 0:
            logger.debug(f"Job {job_id} progress updated: {completed_segments} segments, {progress_percentage}% complete")
        else:
            logger.warning(f"Job {job_id} progress update failed - no documents matched")
        return result.modified_count > 0
    except Exception as e:
        logger.error(f"Job {job_id} progress update error: {str(e)}", exc_info=True)
        return False

def update_job_error(job_id: str, error: str) -> bool:
    """Update job with error information"""
    try:
        db = get_db()
        result = db[JOBS_COLLECTION].update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "error": error,
                    "status": "error",
                    "updated_at": datetime.utcnow()
                }
            }
        )
        if result.modified_count > 0:
            logger.error(f"Job {job_id} marked as error: {error}")
            return True
        else:
            logger.warning(f"Job {job_id} error update failed - no documents matched")
            return False
    except Exception as e:
        logger.error(f"Error updating job error for {job_id}: {str(e)}", exc_info=True)
        return False

def update_job_completion(job_id: str, detected_language: str) -> bool:
    """Update job after successful completion"""
    try:
        db = get_db()
        result = db[JOBS_COLLECTION].update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "detected_language": detected_language,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        if result.modified_count > 0:
            logger.info(f"Job {job_id} marked as completed with language {detected_language}")
            return True
        else:
            logger.warning(f"Job {job_id} completion update failed - no documents matched")
            return False
    except Exception as e:
        logger.error(f"Error updating job completion for {job_id}: {str(e)}", exc_info=True)
        return False

def get_all_jobs(status: Optional[str] = None) -> list:
    """Get all jobs, optionally filtered by status"""
    try:
        db = get_db()
        query = {} if status is None else {"status": status}
        jobs = list(db[JOBS_COLLECTION].find(query).sort("created_at", -1))
        for job in jobs:
            job.pop("_id", None)
        logger.debug(f"Retrieved {len(jobs)} jobs with status: {status}")
        return jobs
    except Exception as e:
        logger.error(f"Error getting all jobs: {str(e)}", exc_info=True)
        return []

def delete_job(job_id: str) -> bool:
    """Delete a job from MongoDB"""
    try:
        db = get_db()
        result = db[JOBS_COLLECTION].delete_one({"job_id": job_id})
        if result.deleted_count > 0:
            logger.info(f"Job {job_id} deleted from MongoDB")
            return True
        else:
            logger.warning(f"Job {job_id} delete failed - no documents matched")
            return False
    except Exception as e:
        logger.error(f"Error deleting job {job_id}: {str(e)}", exc_info=True)
        return False

# ============== GAME SESSION FUNCTIONS ==============

def create_game_session(session_id: str, creator_id: str, game_category: str, player_topic: str, imposter_topic: str, max_players: int = 8) -> Dict:
    """Create a new game session"""
    db = get_db()
    session_document = {
        "session_id": session_id,
        "creator_id": creator_id,
        "game_category": game_category,
        "player_topic": player_topic,
        "imposter_topic": imposter_topic,
        "max_players": max_players,
        "status": "waiting",  # waiting, playing, voting, ended
        "players_list": [creator_id],
        "imposter_id": None,
        "discussion_time": 180,  # 3 minutes
        "voting_time": 60,  # 1 minute
        "current_phase": "waiting",  # discussion, voting, result
        "votes": {},  # {player_id: voted_for_id}
        "voters": [],  # list of player_ids who have voted
        "game_result": None,  # winner info
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "started_at": None,
        "ended_at": None
    }
    
    result = db[GAME_SESSIONS_COLLECTION].insert_one(session_document)
    logger.info(f"Game session {session_id} created by {creator_id}")
    return session_document

def get_game_session(session_id: str) -> Optional[Dict]:
    """Get a game session from MongoDB"""
    try:
        db = get_db()
        session = db[GAME_SESSIONS_COLLECTION].find_one({"session_id": session_id})
        if session:
            session.pop("_id", None)
            # logger.debug(f"Game session {session_id} retrieved")
            return session
        else:
            logger.warning(f"Game session {session_id} not found")
            return None
    except Exception as e:
        logger.error(f"Error getting game session {session_id}: {str(e)}", exc_info=True)
        return None

def update_game_session(session_id: str, update_data: Dict) -> bool:
    """Update a game session"""
    try:
        db = get_db()
        update_data["updated_at"] = datetime.utcnow()
        result = db[GAME_SESSIONS_COLLECTION].update_one(
            {"session_id": session_id},
            {"$set": update_data}
        )
        if result.modified_count > 0:
            logger.debug(f"Game session {session_id} updated with: {update_data}")
            return True
        else:
            logger.warning(f"Game session {session_id} update failed - no documents matched")
            return False
    except Exception as e:
        logger.error(f"Error updating game session {session_id}: {str(e)}", exc_info=True)
        return False

def add_player_to_session(session_id: str, player_id: str) -> bool:
    """Add a player to a game session"""
    try:
        db = get_db()
        result = db[GAME_SESSIONS_COLLECTION].update_one(
            {"session_id": session_id},
            {
                "$addToSet": {"players_list": player_id},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )
        if result.modified_count > 0:
            logger.info(f"Player {player_id} added to session {session_id}'s player list")
            return True
        else:
            # This can happen if the player is already in the list, which is not an error
            logger.debug(f"Player {player_id} already in session {session_id}'s player list")
            return True
    except Exception as e:
        logger.error(f"Error adding player {player_id} to session {session_id}: {str(e)}", exc_info=True)
        return False

def get_all_game_sessions(status: Optional[str] = None) -> list:
    """Get all game sessions, optionally filtered by status"""
    db = get_db()
    query = {} if status is None else {"status": status}
    sessions = list(db[GAME_SESSIONS_COLLECTION].find(query).sort("created_at", -1))
    for session in sessions:
        session.pop("_id", None)
    return sessions

def remove_game_session(session_id: str) -> bool:
    """Delete a game session"""
    db = get_db()
    # Also remove all players from this session
    db[GAME_PLAYERS_COLLECTION].delete_many({"session_id": session_id})
    result = db[GAME_SESSIONS_COLLECTION].delete_one({"session_id": session_id})
    logger.info(f"Game session {session_id} deleted")
    return result.deleted_count > 0


# ============== GAME PLAYER FUNCTIONS ==============

def add_game_player(session_id: str, player_id: str, player_name: str, is_imposter: bool = False) -> Dict:
    """Add a player to game"""
    db = get_db()
    player_document = {
        "session_id": session_id,
        "player_id": player_id,
        "player_name": player_name,
        "is_imposter": is_imposter,
        "is_alive": True,  # False if voted out
        "votes_received": 0,
        "joined_at": datetime.utcnow(),
        "last_heartbeat": datetime.utcnow()
    }
    
    result = db[GAME_PLAYERS_COLLECTION].insert_one(player_document)
    logger.info(f"Player {player_name} ({player_id}) added to session {session_id}")
    return player_document

def update_player_heartbeat(session_id: str, player_id: str) -> bool:
    """Update player's last heartbeat"""
    db = get_db()
    result = db[GAME_PLAYERS_COLLECTION].update_one(
        {"session_id": session_id, "player_id": player_id},
        {"$set": {"last_heartbeat": datetime.utcnow()}}
    )
    return result.modified_count > 0

def remove_inactive_players(session_id: str) -> int:
    """Remove players who have not sent a heartbeat in the last 30 seconds"""
    db = get_db()
    thirty_seconds_ago = datetime.utcnow() - timedelta(seconds=30)
    result = db[GAME_PLAYERS_COLLECTION].delete_many(
        {"session_id": session_id, "last_heartbeat": {"$lt": thirty_seconds_ago}}
    )
    if result.deleted_count > 0:
        logger.info(f"Removed {result.deleted_count} inactive players from session {session_id}")
    return result.deleted_count

def get_game_player(session_id: str, player_id: str) -> Optional[Dict]:
    """Get a player from a game session"""
    db = get_db()
    player = db[GAME_PLAYERS_COLLECTION].find_one({"session_id": session_id, "player_id": player_id})
    if player:
        player.pop("_id", None)
    return player

def get_session_players(session_id: str, only_alive: bool = False) -> list:
    """Get all players in a session"""
    db = get_db()
    query = {"session_id": session_id}
    if only_alive:
        query["is_alive"] = True
    players = list(db[GAME_PLAYERS_COLLECTION].find(query))
    for player in players:
        player.pop("_id", None)
    return players

def update_player_votes(session_id: str, player_id: str, votes_count: int) -> bool:
    """Update votes received by a player"""
    db = get_db()
    result = db[GAME_PLAYERS_COLLECTION].update_one(
        {"session_id": session_id, "player_id": player_id},
        {"$set": {"votes_received": votes_count}}
    )
    return result.modified_count > 0

def mark_player_voted_out(session_id: str, player_id: str) -> bool:
    """Mark a player as voted out"""
    db = get_db()
    result = db[GAME_PLAYERS_COLLECTION].update_one(
        {"session_id": session_id, "player_id": player_id},
        {"$set": {"is_alive": False}}
    )
    return result.modified_count > 0

def remove_game_players(session_id: str) -> bool:
    """Remove all players from a session"""
    db = get_db()
    result = db[GAME_PLAYERS_COLLECTION].delete_many({"session_id": session_id})
    logger.info(f"All players removed from session {session_id}")
    return result.deleted_count > 0