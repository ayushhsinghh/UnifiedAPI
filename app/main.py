import os
import uuid
import logging
import string
import random
import shutil

from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException, Form, Query, Request, Depends
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from storage import JobStatus
from worker import transcribe_job
from database import (
    create_job, get_job, update_job_status, get_all_jobs, delete_job,
    update_player_heartbeat, remove_inactive_players,
)
from game import GameManager
from logging_config import setup_logging
from security import (
    SecurityHeadersMiddleware,
    RequestIdMiddleware,
    validate_job_id,
    validate_session_id,
    validate_file_extension,
    safe_error_response,
    require_admin_key,
    MAX_UPLOAD_SIZE,
    ENVIRONMENT,
)

# ── Logging ──────────────────────────────────────────────────────────────────
setup_logging()
logger = logging.getLogger(__name__)

# ── Rate Limiter ─────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

# ── App Factory ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="Video Transcriber & Imposter Game API",
    docs_url="/docs" if ENVIRONMENT == "development" else None,
    redoc_url="/redoc" if ENVIRONMENT == "development" else None,
    openapi_url="/openapi.json" if ENVIRONMENT == "development" else None,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Middleware Stack (order matters – outermost first) ───────────────────────

# 1. Request-ID tracking
app.add_middleware(RequestIdMiddleware)

# 2. Security response headers
app.add_middleware(SecurityHeadersMiddleware)

# 3. Trusted hosts
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[
        "game.ayush.ltd",
        "api.ayush.ltd",
        "subs.ayush.ltd",
        "ayush.ltd",
        "localhost",
        "127.0.0.1",
    ],
)

# 4. CORS – explicit methods & headers instead of wildcards
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://game.ayush.ltd",
        "https://subs.ayush.ltd",
        "https://ayush.ltd",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=[
        "Accept",
        "Accept-Language",
        "Authorization",
        "Content-Type",
        "Origin",
        "X-Requested-With",
        "X-Admin-Key",
        "X-Request-ID",
    ],
)


# ── Helpers ──────────────────────────────────────────────────────────────────
def generate_job_id() -> str:
    """Generate a short, memorable job ID (e.g., 'job_a1b2')"""
    chars = string.ascii_lowercase + string.digits
    random_part = ''.join(random.choices(chars, k=4))
    return f"job_{random_part}"


# ── Pydantic Models (with input constraints) ────────────────────────────────

class CreateGameRequest(BaseModel):
    player_name: str = Field(
        ..., min_length=1, max_length=30,
        pattern=r"^[a-zA-Z0-9 _\-]+$",
        description="Alphanumeric name, spaces/underscores/hyphens allowed",
    )
    game_category: str = Field(
        ..., min_length=1, max_length=50,
        description="Topic category for the game",
    )
    max_players: int = Field(default=8, ge=3, le=20)


class JoinGameRequest(BaseModel):
    player_name: str = Field(
        ..., min_length=1, max_length=30,
        pattern=r"^[a-zA-Z0-9 _\-]+$",
    )


class StartGameRequest(BaseModel):
    player_id: str = Field(
        ..., min_length=36, max_length=36,
        pattern=r"^[0-9a-f\-]{36}$",
    )


class VoteRequest(BaseModel):
    voted_for_id: str = Field(
        ..., min_length=36, max_length=36,
        pattern=r"^[0-9a-f\-]{36}$",
    )
    player_id: str = Field(
        ..., min_length=36, max_length=36,
        pattern=r"^[0-9a-f\-]{36}$",
    )


class HeartbeatRequest(BaseModel):
    player_id: str = Field(
        ..., min_length=36, max_length=36,
        pattern=r"^[0-9a-f\-]{36}$",
    )


# ── Directories ──────────────────────────────────────────────────────────────
UPLOAD_DIR = "/mnt/extra/uploads"
OUTPUT_DIR = "/mnt/extra/outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Database init ────────────────────────────────────────────────────────────
try:
    from database import DatabaseManager
    db_manager = DatabaseManager()
    logger.info("Database manager initialized successfully")
except Exception as e:
    logger.warning(
        f"Failed to initialize database: {str(e)}. "
        "The application will continue with limited functionality."
    )


# ═══════════════════════════════════════════════════════════════════════════
#  TRANSCRIPTION JOB ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/api/jobs")
@limiter.limit("2/hour")
async def create_job_endpoint(
    request: Request,
    file: UploadFile = File(...),
    language: str = Form(default=""),
    translate: str = Form(default="off"),
    model: str = Form(default="medium"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    # Validate file extension
    validate_file_extension(file.filename)

    job_id = generate_job_id()
    logger.info(f"Creating new job {job_id} for file: {file.filename}")

    video_path = f"{UPLOAD_DIR}/{job_id}_{file.filename}"
    audio_path = f"{UPLOAD_DIR}/{job_id}.wav"
    srt_path = f"{OUTPUT_DIR}/{job_id}.srt"

    # Sanitise form data
    translate_bool = translate.lower() in ('on', 'true', '1', 'yes')
    language_str = language if language else None
    model_str = model if model in ['tiny', 'base', 'small', 'medium', 'large-v3'] else 'medium'

    logger.info(f"Job config - language: {language_str}, translate: {translate_bool}, model: {model_str}")

    try:
        # Stream file to disk with size enforcement
        total_bytes = 0
        with open(video_path, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)  # 1 MB chunks
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_SIZE:
                    # Clean up partial file
                    f.close()
                    os.remove(video_path)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum allowed size is {MAX_UPLOAD_SIZE // (1024**3)} GB.",
                    )
                f.write(chunk)
        logger.debug(f"File saved to {video_path} ({total_bytes} bytes)")

        job_data = {
            "status": JobStatus.PENDING,
            "video": video_path,
            "audio": audio_path,
            "srt": srt_path,
            "translate": translate_bool,
            "language": language_str,
            "model": model_str,
        }

        create_job(job_id, job_data)
        logger.debug(f"Job {job_id} initialized in MongoDB with status PENDING")

        background_tasks.add_task(transcribe_job, job_id)
        logger.info(f"Background task queued for job {job_id}")

        return {"job_id": job_id, "status": JobStatus.PENDING}

    except HTTPException:
        raise  # re-raise HTTP exceptions as-is
    except Exception as e:
        safe_error_response(e, context="create_job")


@app.get("/api/jobs/{job_id}")
@limiter.limit("120/minute")
def get_status(request: Request, job_id: str):
    validate_job_id(job_id)
    logger.debug(f"Status check for job {job_id}")
    job = get_job(job_id)
    if not job:
        logger.warning(f"Job {job_id} not found")
        raise HTTPException(status_code=404, detail="Job not found")

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
        "model": job.get("model", "base"),
    }


@app.get("/api/jobs/{job_id}/subtitles")
@limiter.limit("30/minute")
def get_srt(request: Request, job_id: str):
    validate_job_id(job_id)
    logger.debug(f"Subtitle download requested for job {job_id}")
    job = get_job(job_id)
    if not job or job["status"] != JobStatus.DONE:
        logger.warning(
            f"Subtitle request for job {job_id} returned not ready "
            f"(status: {job['status'] if job else 'N/A'})"
        )
        raise HTTPException(status_code=404, detail="Subtitles not ready")

    logger.info(f"Subtitle file retrieved for job {job_id}")
    return FileResponse(
        job["srt"],
        media_type="application/x-subrip",
        filename="subtitles.srt",
    )


@app.get("/api/jobs")
@limiter.limit("60/minute")
def list_jobs(request: Request, status: str | None = None):
    """List all jobs, optionally filtered by status"""
    logger.debug(f"Listing jobs with status filter: {status}")
    jobs_list = get_all_jobs(status)
    return {"jobs": jobs_list, "total": len(jobs_list)}


@app.delete("/api/jobs/{job_id}")
@limiter.limit("10/minute")
def delete_job_endpoint(request: Request, job_id: str):
    """Delete a job by ID"""
    validate_job_id(job_id)
    logger.info(f"Deleting job {job_id}")
    job = get_job(job_id)
    if not job:
        logger.warning(f"Job {job_id} not found for deletion")
        raise HTTPException(status_code=404, detail="Job not found")

    try:
        success = delete_job(job_id)
        if success:
            logger.info(f"Job {job_id} deleted successfully")
            return {"message": f"Job {job_id} deleted successfully", "job_id": job_id}
        else:
            logger.error(f"Failed to delete job {job_id}")
            raise HTTPException(status_code=500, detail="Failed to delete job")
    except HTTPException:
        raise
    except Exception as e:
        safe_error_response(e, context="delete_job")


# ═══════════════════════════════════════════════════════════════════════════
#  HOMEPAGE
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
@limiter.limit("30/minute")
def home(request: Request):
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


# ═══════════════════════════════════════════════════════════════════════════
#  GAME API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/api/game/create")
@limiter.limit("5/minute")
async def create_game(request: Request, body: CreateGameRequest):
    """Create a new game session"""
    try:
        player_id = GameManager.generate_player_id()
        success, response = GameManager.create_new_game(
            creator_id=player_id,
            creator_name=body.player_name,
            game_category=body.game_category,
            max_players=body.max_players,
        )

        if success:
            logger.info(f"Game created by {body.player_name}")
            return {**response, "player_id": player_id}
        else:
            raise HTTPException(status_code=400, detail=response.get("message", "Failed to create game"))
    except HTTPException:
        raise
    except Exception as e:
        safe_error_response(e, context="create_game")


@app.post("/api/game/{session_id}/join")
@limiter.limit("25/minute")
async def join_game(request: Request, session_id: str, body: JoinGameRequest):
    """Join an existing game session"""
    validate_session_id(session_id)
    try:
        player_id = GameManager.generate_player_id()
        success, response = GameManager.join_game(
            session_id=session_id,
            player_id=player_id,
            player_name=body.player_name,
        )

        if success:
            logger.info(f"Player {body.player_name} joined game {session_id}")
            return {**response, "player_id": player_id}
        else:
            raise HTTPException(status_code=400, detail=response.get("message", "Failed to join game"))
    except HTTPException:
        raise
    except Exception as e:
        safe_error_response(e, context="join_game")


@app.post("/api/game/{session_id}/start")
@limiter.limit("10/minute")
async def start_game(request: Request, session_id: str, body: StartGameRequest):
    """Start a game session"""
    validate_session_id(session_id)
    try:
        success, response = GameManager.start_game(session_id, body.player_id)

        if success:
            logger.info(f"Game {session_id} started")
            return response
        else:
            raise HTTPException(status_code=400, detail=response.get("message", "Failed to start game"))
    except HTTPException:
        raise
    except Exception as e:
        safe_error_response(e, context="start_game")


@app.get("/api/game/{session_id}")
@limiter.limit("200/minute")
async def get_game(request: Request, session_id: str, player_id: str = Query(None)):
    """Get game information"""
    validate_session_id(session_id)
    try:
        success, response = GameManager.get_game_info(session_id, player_id)

        if success:
            return response
        else:
            raise HTTPException(status_code=404, detail=response.get("message", "Game not found"))
    except HTTPException:
        raise
    except Exception as e:
        safe_error_response(e, context="get_game")


@app.post("/api/game/{session_id}/vote")
@limiter.limit("60/minute")
async def submit_vote(request: Request, session_id: str, body: VoteRequest):
    """Submit a vote during voting phase"""
    validate_session_id(session_id)
    try:
        success, response = GameManager.submit_vote(
            session_id=session_id,
            voter_id=body.player_id,
            voted_for_id=body.voted_for_id,
        )

        if success:
            logger.info(f"Vote registered in game {session_id}")
            return response
        else:
            raise HTTPException(status_code=400, detail=response.get("message", "Failed to submit vote"))
    except HTTPException:
        raise
    except Exception as e:
        safe_error_response(e, context="submit_vote")


@app.get("/api/game/{session_id}/result")
@limiter.limit("120/minute")
async def get_game_result(request: Request, session_id: str):
    """Get game result after reveal time"""
    validate_session_id(session_id)
    try:
        success, response = GameManager.get_game_result(session_id)

        if success:
            return response
        else:
            raise HTTPException(status_code=400, detail=response.get("message", "Failed to get game result"))
    except HTTPException:
        raise
    except Exception as e:
        safe_error_response(e, context="get_game_result")


@app.post("/api/game/{session_id}/end-voting")
@limiter.limit("60/minute")
async def end_voting(request: Request, session_id: str):
    """End voting phase and determine results"""
    validate_session_id(session_id)
    try:
        success, response = GameManager.end_voting(session_id)

        if success:
            logger.info(f"Voting ended in game {session_id}")
            return response
        else:
            raise HTTPException(status_code=400, detail=response.get("message", "Failed to end voting"))
    except HTTPException:
        raise
    except Exception as e:
        safe_error_response(e, context="end_voting")


@app.post("/api/game/{session_id}/transition-voting")
@limiter.limit("10/minute")
async def transition_to_voting(request: Request, session_id: str):
    """Transition game from discussion to voting phase"""
    validate_session_id(session_id)
    try:
        success, response = GameManager.transition_to_voting(session_id)

        if success:
            logger.info(f"Game {session_id} transitioned to voting")
            return response
        else:
            raise HTTPException(status_code=400, detail=response.get("message", "Failed to transition"))
    except HTTPException:
        raise
    except Exception as e:
        safe_error_response(e, context="transition_to_voting")


@app.get("/api/games/available")
@limiter.limit("60/minute")
async def list_available_games(request: Request):
    """List all available games (waiting status)"""
    try:
        games = GameManager.list_available_games()
        logger.debug(f"Listed {len(games)} available games")
        return {"success": True, "games": games, "total": len(games)}
    except Exception as e:
        safe_error_response(e, context="list_available_games")


@app.post("/api/game/{session_id}/new-round")
@limiter.limit("50/minute")
async def new_round(request: Request, session_id: str):
    """Start a new round for an existing game session"""
    validate_session_id(session_id)
    try:
        success, response = GameManager.new_round(session_id)

        if success:
            logger.info(f"New round started for game {session_id}")
            return response
        else:
            raise HTTPException(status_code=400, detail=response.get("message", "Failed to start new round"))
    except HTTPException:
        raise
    except Exception as e:
        safe_error_response(e, context="new_round")


@app.post("/api/game/{session_id}/heartbeat")
@limiter.limit("200/minute")
async def heartbeat(request: Request, session_id: str, body: HeartbeatRequest):
    """Player heartbeat to stay active"""
    validate_session_id(session_id)
    try:
        success = update_player_heartbeat(session_id, body.player_id)
        if success:
            return {"success": True}
        else:
            raise HTTPException(status_code=404, detail="Player not found")
    except HTTPException:
        raise
    except Exception as e:
        safe_error_response(e, context="heartbeat")


# ═══════════════════════════════════════════════════════════════════════════
#  ADMIN / CLEANUP ENDPOINTS  (require X-Admin-Key header)
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/api/games/cleanup-inactive")
@limiter.limit("10/minute")
async def cleanup_inactive_players(request: Request, _=Depends(require_admin_key)):
    """Periodically clean up inactive players from all active games"""
    try:
        from database import get_all_game_sessions
        sessions = get_all_game_sessions(status="waiting") + get_all_game_sessions(status="playing")
        cleaned = 0
        for session in sessions:
            cleaned += remove_inactive_players(session["session_id"])
        return {"success": True, "message": f"Removed {cleaned} inactive players"}
    except Exception as e:
        safe_error_response(e, context="cleanup_inactive_players")


@app.post("/api/games/cleanup")
@limiter.limit("5/minute")
async def cleanup_old_games(request: Request, _=Depends(require_admin_key)):
    """Periodically clean up old game sessions"""
    try:
        success, response = GameManager.delete_old_games()
        if success:
            logger.info("Old games cleaned up successfully")
            return response
        else:
            raise HTTPException(status_code=500, detail="Failed to clean up old games")
    except HTTPException:
        raise
    except Exception as e:
        safe_error_response(e, context="cleanup_old_games")


@app.delete("/api/game/{session_id}")
@limiter.limit("5/minute")
async def delete_game(request: Request, session_id: str, _=Depends(require_admin_key)):
    """Delete a game session (admin only)"""
    validate_session_id(session_id)
    try:
        success, response = GameManager.delete_game(session_id)

        if success:
            logger.info(f"Game {session_id} deleted")
            return response
        else:
            raise HTTPException(status_code=400, detail=response.get("message", "Failed to delete game"))
    except HTTPException:
        raise
    except Exception as e:
        safe_error_response(e, context="delete_game")


# ═══════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

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
        limit_max_requests=10000,
    )