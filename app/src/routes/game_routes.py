"""
Guess-the-Imposter game API routes.

Endpoints:
    POST /api/game/create                      — create game
    POST /api/game/{session_id}/join            — join game
    POST /api/game/{session_id}/start           — start game
    GET  /api/game/{session_id}                 — get game info
    POST /api/game/{session_id}/vote            — submit vote
    GET  /api/game/{session_id}/result          — get result
    POST /api/game/{session_id}/end-voting      — end voting
    POST /api/game/{session_id}/transition-voting — move to voting
    GET  /api/games/available                   — list waiting games
    POST /api/game/{session_id}/new-round       — start new round
    POST /api/game/{session_id}/heartbeat       — player heartbeat
"""

import logging

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from commons import limiter
from security import safe_error_response, validate_session_id
from src.database.game_repository import update_player_heartbeat
from src.game.manager import GameManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["game"])


# ── Pydantic request bodies ─────────────────────────────────────────────


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


# ── Endpoints ────────────────────────────────────────────────────────────


@router.post("/game/create")
@limiter.limit("5/minute")
async def create_game(request: Request, body: CreateGameRequest) -> dict:
    """Create a new game session."""
    try:
        player_id = GameManager.generate_player_id()
        success, response = GameManager.create_new_game(
            creator_id=player_id,
            creator_name=body.player_name,
            game_category=body.game_category,
            max_players=body.max_players,
        )
        if success:
            logger.info("Game created by %s", body.player_name)
            return {**response, "player_id": player_id}
        raise HTTPException(
            status_code=400,
            detail=response.get("message", "Failed to create game"),
        )
    except HTTPException:
        raise
    except Exception as exc:
        safe_error_response(exc, context="create_game")


@router.post("/game/{session_id}/join")
@limiter.limit("25/minute")
async def join_game(
    request: Request, session_id: str, body: JoinGameRequest
) -> dict:
    """Join an existing game session."""
    validate_session_id(session_id)
    try:
        player_id = GameManager.generate_player_id()
        success, response = GameManager.join_game(
            session_id=session_id,
            player_id=player_id,
            player_name=body.player_name,
        )
        if success:
            logger.info(
                "Player %s joined game %s", body.player_name, session_id
            )
            return {**response, "player_id": player_id}
        raise HTTPException(
            status_code=400,
            detail=response.get("message", "Failed to join game"),
        )
    except HTTPException:
        raise
    except Exception as exc:
        safe_error_response(exc, context="join_game")


@router.post("/game/{session_id}/start")
@limiter.limit("10/minute")
async def start_game(
    request: Request, session_id: str, body: StartGameRequest
) -> dict:
    """Start a game session."""
    validate_session_id(session_id)
    try:
        success, response = GameManager.start_game(
            session_id, body.player_id
        )
        if success:
            logger.info("Game %s started", session_id)
            return response
        raise HTTPException(
            status_code=400,
            detail=response.get("message", "Failed to start game"),
        )
    except HTTPException:
        raise
    except Exception as exc:
        safe_error_response(exc, context="start_game")


@router.get("/game/{session_id}")
@limiter.limit("200/minute")
async def get_game(
    request: Request,
    session_id: str,
    player_id: str = Query(None),
) -> dict:
    """Get game information."""
    validate_session_id(session_id)
    try:
        success, response = GameManager.get_game_info(session_id, player_id)
        if success:
            return response
        raise HTTPException(
            status_code=404,
            detail=response.get("message", "Game not found"),
        )
    except HTTPException:
        raise
    except Exception as exc:
        safe_error_response(exc, context="get_game")


@router.post("/game/{session_id}/vote")
@limiter.limit("60/minute")
async def submit_vote(
    request: Request, session_id: str, body: VoteRequest
) -> dict:
    """Submit a vote during the voting phase."""
    validate_session_id(session_id)
    try:
        success, response = GameManager.submit_vote(
            session_id=session_id,
            voter_id=body.player_id,
            voted_for_id=body.voted_for_id,
        )
        if success:
            logger.info("Vote registered in game %s", session_id)
            return response
        raise HTTPException(
            status_code=400,
            detail=response.get("message", "Failed to submit vote"),
        )
    except HTTPException:
        raise
    except Exception as exc:
        safe_error_response(exc, context="submit_vote")


@router.get("/game/{session_id}/result")
@limiter.limit("120/minute")
async def get_game_result(request: Request, session_id: str) -> dict:
    """Get the game result after the reveal phase."""
    validate_session_id(session_id)
    try:
        success, response = GameManager.get_game_result(session_id)
        if success:
            return response
        raise HTTPException(
            status_code=400,
            detail=response.get("message", "Failed to get game result"),
        )
    except HTTPException:
        raise
    except Exception as exc:
        safe_error_response(exc, context="get_game_result")


@router.post("/game/{session_id}/end-voting")
@limiter.limit("60/minute")
async def end_voting(request: Request, session_id: str) -> dict:
    """End the voting phase and determine results."""
    validate_session_id(session_id)
    try:
        success, response = GameManager.end_voting(session_id)
        if success:
            logger.info("Voting ended in game %s", session_id)
            return response
        raise HTTPException(
            status_code=400,
            detail=response.get("message", "Failed to end voting"),
        )
    except HTTPException:
        raise
    except Exception as exc:
        safe_error_response(exc, context="end_voting")


@router.post("/game/{session_id}/transition-voting")
@limiter.limit("10/minute")
async def transition_to_voting(
    request: Request, session_id: str
) -> dict:
    """Transition game from discussion to voting phase."""
    validate_session_id(session_id)
    try:
        success, response = GameManager.transition_to_voting(session_id)
        if success:
            logger.info("Game %s transitioned to voting", session_id)
            return response
        raise HTTPException(
            status_code=400,
            detail=response.get("message", "Failed to transition"),
        )
    except HTTPException:
        raise
    except Exception as exc:
        safe_error_response(exc, context="transition_to_voting")


@router.get("/games/available")
@limiter.limit("60/minute")
async def list_available_games(request: Request) -> dict:
    """List all available (waiting) games."""
    try:
        games = GameManager.list_available_games()
        logger.debug("Listed %d available games", len(games))
        return {"success": True, "games": games, "total": len(games)}
    except Exception as exc:
        safe_error_response(exc, context="list_available_games")


@router.post("/game/{session_id}/new-round")
@limiter.limit("50/minute")
async def new_round(request: Request, session_id: str) -> dict:
    """Start a new round for an existing game session."""
    validate_session_id(session_id)
    try:
        success, response = GameManager.new_round(session_id)
        if success:
            logger.info("New round started for game %s", session_id)
            return response
        raise HTTPException(
            status_code=400,
            detail=response.get("message", "Failed to start new round"),
        )
    except HTTPException:
        raise
    except Exception as exc:
        safe_error_response(exc, context="new_round")


@router.post("/game/{session_id}/heartbeat")
@limiter.limit("200/minute")
async def heartbeat(
    request: Request, session_id: str, body: HeartbeatRequest
) -> dict:
    """Player heartbeat to stay active."""
    validate_session_id(session_id)
    try:
        success = update_player_heartbeat(session_id, body.player_id)
        if success:
            return {"success": True}
        raise HTTPException(status_code=404, detail="Player not found")
    except HTTPException:
        raise
    except Exception as exc:
        safe_error_response(exc, context="heartbeat")
