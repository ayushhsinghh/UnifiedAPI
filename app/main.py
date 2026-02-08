import uuid
import logging
import string
import random
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException, Form, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from storage import JobStatus
from worker import transcribe_job
from database import create_job, get_job, update_job_status, get_all_jobs, delete_job, update_player_heartbeat, remove_inactive_players
from game import GameManager
from pydantic import BaseModel
import os
import shutil

from logging_config import setup_logging

# Set up logging
setup_logging()
logger = logging.getLogger(__name__)

def generate_job_id() -> str:
    """Generate a short, memorable job ID (e.g., 'job_a1b2')"""
    chars = string.ascii_lowercase + string.digits
    random_part = ''.join(random.choices(chars, k=4))
    return f"job_{random_part}"

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount guessGame static files
guessGame_path = os.path.join(os.path.dirname(__file__), "guessGame")
if os.path.exists(guessGame_path):
    app.mount("/guessGame", StaticFiles(directory=guessGame_path, html=True), name="guessGame")

# Pydantic models for game APIs
class CreateGameRequest(BaseModel):
    player_name: str
    game_category: str
    max_players: int = 8

class JoinGameRequest(BaseModel):
    player_name: str

class StartGameRequest(BaseModel):
    player_id: str

class VoteRequest(BaseModel):
    voted_for_id: str
    player_id: str

class HeartbeatRequest(BaseModel):
    player_id: str

UPLOAD_DIR = "/mnt/extra/uploads"
OUTPUT_DIR = "/mnt/extra/outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Initialize database connection
try:
    from database import DatabaseManager
    db_manager = DatabaseManager()
    logger.info("Database manager initialized successfully")
except Exception as e:
    logger.warning(f"Failed to initialize database: {str(e)}. The application will continue with limited functionality.")

@app.post("/api/jobs")
async def create_job_endpoint(
    file: UploadFile = File(...),
    language: str = Form(default=""),
    translate: str = Form(default="off"),
    model: str = Form(default="medium"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    job_id = generate_job_id()
    logger.info(f"Creating new job {job_id} for file: {file.filename}")

    video_path = f"{UPLOAD_DIR}/{job_id}_{file.filename}"
    audio_path = f"{UPLOAD_DIR}/{job_id}.wav"
    srt_path = f"{OUTPUT_DIR}/{job_id}.srt"

    # Convert form data strings to appropriate types
    translate_bool = translate.lower() in ('on', 'true', '1', 'yes')
    language_str = language if language else None
    model_str = model if model in ['tiny', 'base', 'small', 'medium', 'large-v3'] else 'medium'

    logger.info(f"Job config - language: {language_str}, translate: {translate_bool}, model: {model_str}")

    try:
        # Stream file to disk instead of reading all into memory
        with open(video_path, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)  # Read 1MB at a time
                if not chunk:
                    break
                f.write(chunk)
        logger.debug(f"File saved to {video_path}")

        job_data = {
            "status": JobStatus.PENDING,
            "video": video_path,
            "audio": audio_path,
            "srt": srt_path,
            "translate": translate_bool,
            "language": language_str,
            "model": model_str
        }
        
        create_job(job_id, job_data)
        logger.debug(f"Job {job_id} initialized in MongoDB with status PENDING")

        background_tasks.add_task(transcribe_job, job_id)
        logger.info(f"Background task queued for job {job_id}")

        return {
            "job_id": job_id,
            "status": JobStatus.PENDING
        }
    except Exception as e:
        logger.error(f"Error creating job {job_id}: {str(e)}", exc_info=True)
        raise
    
@app.get("/api/jobs/{job_id}")
def get_status(job_id: str):
    logger.debug(f"Status check for job {job_id}")
    job = get_job(job_id)
    if not job:
        logger.warning(f"Job {job_id} not found")
        return {"error": "not found"}

    logger.debug(f"Job {job_id} status: {job['status']}")
    return {
        "job_id": job_id,
        "status": job["status"],
        "progress_percentage": job.get("progress_percentage", 0),
        "completed_segments": job.get("completed_segments", 0),
        "total_segments": job.get("total_segments", 0),
        "language": job.get("language"),
        "detected_language": job.get("detected_language"),
        "translate": job.get("translate", False),
        "model": job.get("model", "base")
    }

@app.get("/api/jobs/{job_id}/subtitles")
def get_srt(job_id: str):
    logger.debug(f"Subtitle download requested for job {job_id}")
    job = get_job(job_id)
    if not job or job["status"] != JobStatus.DONE:
        logger.warning(f"Subtitle request for job {job_id} returned not ready (status: {job['status'] if job else 'N/A'})")
        return {"error": "not ready"}

    logger.info(f"Subtitle file retrieved for job {job_id}")
    return FileResponse(
        job["srt"],
        media_type="application/x-subrip",
        filename="subtitles.srt"
    )

@app.get("/api/jobs")
def list_jobs(status: str | None = None):
    """List all jobs, optionally filtered by status"""
    logger.debug(f"Listing jobs with status filter: {status}")
    jobs_list = get_all_jobs(status)
    return {"jobs": jobs_list, "total": len(jobs_list)}

@app.delete("/api/jobs/{job_id}")
def delete_job_endpoint(job_id: str):
    """Delete a job by ID"""
    logger.info(f"Deleting job {job_id}")
    job = get_job(job_id)
    if not job:
        logger.warning(f"Job {job_id} not found for deletion")
        raise HTTPException(status_code=404, detail="Job not found")
    
    try:
        # Delete job from database
        success = delete_job(job_id)
        if success:
            logger.info(f"Job {job_id} deleted successfully")
            return {"message": f"Job {job_id} deleted successfully", "job_id": job_id}
        else:
            logger.error(f"Failed to delete job {job_id}")
            raise HTTPException(status_code=500, detail="Failed to delete job")
    except Exception as e:
        logger.error(f"Error deleting job {job_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/", response_class=HTMLResponse)
def home():
    """Serve homepage from template"""
    template_path = os.path.join(os.path.dirname(__file__), "templates", "home.html")
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"Template not found at {template_path}")
        return """
        <html>
        <body style="font-family: sans-serif; padding: 20px;">
            <h1>🎬 Video Transcriber API</h1>
            <p>✅ API is running, but homepage template not found.</p>
            <p><a href="/api/jobs">View API</a></p>
            <p><a href="/guessGame">Play Guess the Imposter</a></p>
        </body>
        </html>
        """

@app.get("/game", response_class=HTMLResponse)
def game():
    """Serve the Guess the Imposter game"""
    game_path = os.path.join(os.path.dirname(__file__), "guessGame", "index.html")
    try:
        with open(game_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"Game template not found at {game_path}")
        raise HTTPException(status_code=404, detail="Game not found")

# ============== GAME API ENDPOINTS ==============

@app.post("/api/game/create")
async def create_game(request: CreateGameRequest):
    """Create a new game session"""
    try:
        player_id = GameManager.generate_player_id()
        success, response = GameManager.create_new_game(
            creator_id=player_id,
            creator_name=request.player_name,
            game_category=request.game_category,
            max_players=request.max_players
        )
        
        if success:
            logger.info(f"Game created by {request.player_name}")
            return {
                **response,
                "player_id": player_id
            }
        else:
            raise HTTPException(status_code=400, detail=response.get("message", "Failed to create game"))
    except Exception as e:
        logger.error(f"Error in create_game: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/game/{session_id}/join")
async def join_game(session_id: str, request: JoinGameRequest):
    """Join an existing game session"""
    try:
        player_id = GameManager.generate_player_id()
        success, response = GameManager.join_game(
            session_id=session_id,
            player_id=player_id,
            player_name=request.player_name
        )
        
        if success:
            logger.info(f"Player {request.player_name} joined game {session_id}")
            return {
                **response,
                "player_id": player_id
            }
        else:
            raise HTTPException(status_code=400, detail=response.get("message", "Failed to join game"))
    except Exception as e:
        logger.error(f"Error in join_game: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/game/{session_id}/start")
async def start_game(session_id: str, request: StartGameRequest):
    """Start a game session"""
    try:
        success, response = GameManager.start_game(session_id, request.player_id)
        
        if success:
            logger.info(f"Game {session_id} started")
            return response
        else:
            raise HTTPException(status_code=400, detail=response.get("message", "Failed to start game"))
    except Exception as e:
        logger.error(f"Error in start_game: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/game/{session_id}")
async def get_game(session_id: str, player_id: str = Query(None)):
    """Get game information"""
    try:
        success, response = GameManager.get_game_info(session_id, player_id)
        
        if success:
            return response
        else:
            raise HTTPException(status_code=404, detail=response.get("message", "Game not found"))
    except Exception as e:
        logger.error(f"Error in get_game: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/game/{session_id}/vote")
async def submit_vote(session_id: str, request: VoteRequest):
    """Submit a vote during voting phase"""
    try:
        success, response = GameManager.submit_vote(
            session_id=session_id,
            voter_id=request.player_id,
            voted_for_id=request.voted_for_id
        )
        
        if success:
            logger.info(f"Vote registered in game {session_id}")
            return response
        else:
            raise HTTPException(status_code=400, detail=response.get("message", "Failed to submit vote"))
    except Exception as e:
        logger.error(f"Error in submit_vote: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/game/{session_id}/result")
async def get_game_result(session_id: str):
    """Get game result after reveal time"""
    try:
        success, response = GameManager.get_game_result(session_id)
        
        if success:
            logger.info(f"Game result retrieved for {session_id}")
            return response
        else:
            raise HTTPException(status_code=400, detail=response.get("message", "Failed to get game result"))
    except Exception as e:
        logger.error(f"Error in get_game_result: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/game/{session_id}/end-voting")
async def end_voting(session_id: str):
    """End voting phase and determine results"""
    try:
        success, response = GameManager.end_voting(session_id)
        
        if success:
            logger.info(f"Voting ended in game {session_id}")
            return response
        else:
            raise HTTPException(status_code=400, detail=response.get("message", "Failed to end voting"))
    except Exception as e:
        logger.error(f"Error in end_voting: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/game/{session_id}/transition-voting")
async def transition_to_voting(session_id: str):
    """Transition game from discussion to voting phase"""
    try:
        success, response = GameManager.transition_to_voting(session_id)
        
        if success:
            logger.info(f"Game {session_id} transitioned to voting")
            return response
        else:
            raise HTTPException(status_code=400, detail=response.get("message", "Failed to transition"))
    except Exception as e:
        logger.error(f"Error in transition_to_voting: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/games/available")
async def list_available_games():
    """List all available games (waiting status)"""
    try:
        games = GameManager.list_available_games()
        logger.debug(f"Listed {len(games)} available games")
        return {
            "success": True,
            "games": games,
            "total": len(games)
        }
    except Exception as e:
        logger.error(f"Error in list_available_games: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/game/{session_id}/new-round")
async def new_round(session_id: str):
    """Start a new round for an existing game session"""
    try:
        success, response = GameManager.new_round(session_id)
        
        if success:
            logger.info(f"New round started for game {session_id}")
            return response
        else:
            raise HTTPException(status_code=400, detail=response.get("message", "Failed to start new round"))
    except Exception as e:
        logger.error(f"Error in new_round: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/game/{session_id}/heartbeat")
async def heartbeat(session_id: str, request: HeartbeatRequest):
    """Player heartbeat to stay active"""
    try:
        success = update_player_heartbeat(session_id, request.player_id)
        if success:
            return {"success": True}
        else:
            raise HTTPException(status_code=404, detail="Player not found")
    except Exception as e:
        logger.error(f"Error in heartbeat: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/games/cleanup-inactive")
async def cleanup_inactive_players():
    """Periodically clean up inactive players from all games"""
    try:
        sessions = GameManager.list_available_games()
        for session in sessions:
            remove_inactive_players(session["session_id"])
        return {"success": True, "message": "Inactive players cleaned up"}
    except Exception as e:
        logger.error(f"Error in cleanup_inactive_players: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/games/cleanup")
async def cleanup_old_games():
    """Periodically clean up old game sessions"""
    try:
        success, response = GameManager.delete_old_games()
        if success:
            logger.info("Old games cleaned up successfully")
            return response
        else:
            raise HTTPException(status_code=500, detail=response.get("message", "Failed to clean up old games"))
    except Exception as e:
        logger.error(f"Error in cleanup_old_games: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/game/{session_id}")
async def delete_game(session_id: str):
    """Delete a game session"""
    try:
        success, response = GameManager.delete_game(session_id)
        
        if success:
            logger.info(f"Game {session_id} deleted")
            return response
        else:
            raise HTTPException(status_code=400, detail=response.get("message", "Failed to delete game"))
    except Exception as e:
        logger.error(f"Error in delete_game: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))# Entry point for running the app
if __name__ == "__main__":
    import uvicorn
    import argparse
    
    parser = argparse.ArgumentParser(description="Run Video Transcriber")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload on code changes")
    parser.add_argument("--cert-file", default=None, help="Path to SSL certificate file (enables HTTPS)")
    parser.add_argument("--key-file", default=None, help="Path to SSL private key file (required with --cert-file)")
    
    args = parser.parse_args()
    
    # Validate SSL configuration
    if (args.cert_file and not args.key_file) or (args.key_file and not args.cert_file):
        logger.error("Both --cert-file and --key-file must be provided together")
        exit(1)
    
    protocol = "HTTPS" if args.cert_file else "HTTP"
    logger.info(f"Starting {protocol} server on {args.host}:{args.port}")
    logger.info("Access the app at:")
    if args.cert_file:
        logger.info(f"  Local: https://localhost:{args.port}")
        logger.info(f"  Network: https://0.0.0.0:{args.port}")
        logger.info(f"✅ SSL/TLS enabled with certificate from: {args.cert_file}")
    else:
        logger.info(f"  Local: http://localhost:{args.port}")
        logger.info(f"  Network: http://0.0.0.0:{args.port}")
    
    uvicorn.run(
        "main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
        ssl_certfile=args.cert_file,
        ssl_keyfile=args.key_file,
        limit_concurrency=1000,
        limit_max_requests=10000
    )