"""
Admin / cleanup API routes.

All endpoints require a valid ``X-Admin-Key`` header.

Endpoints:
    POST   /api/games/cleanup-inactive — remove inactive players
    POST   /api/games/cleanup          — delete old waiting games
    DELETE /api/game/{session_id}       — delete a specific game
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from commons import limiter

from security import require_admin_key, safe_error_response, validate_session_id
from src.database.game_repository import (
    get_all_game_sessions,
    remove_inactive_players,
)
from src.game.manager import GameManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["admin"])


@router.post("/games/cleanup-inactive")
@limiter.limit("10/minute")
async def cleanup_inactive_players(
    request: Request, _=Depends(require_admin_key)
) -> dict:
    """Remove inactive players from all active game sessions."""
    try:
        waiting_sessions = get_all_game_sessions(status="waiting")
        playing_sessions = get_all_game_sessions(status="playing")
        all_sessions = waiting_sessions + playing_sessions
        cleaned = sum(
            remove_inactive_players(s["session_id"]) for s in all_sessions
        )
        return {
            "success": True,
            "message": f"Removed {cleaned} inactive players",
        }
    except Exception as exc:
        safe_error_response(exc, context="cleanup_inactive_players")


@router.post("/games/cleanup")
@limiter.limit("5/minute")
async def cleanup_old_games(
    request: Request, _=Depends(require_admin_key)
) -> dict:
    """Delete old (stale) waiting game sessions."""
    try:
        success, response = GameManager.delete_old_games()
        if success:
            logger.info("Old games cleaned up successfully")
            return response
        raise HTTPException(
            status_code=500, detail="Failed to clean up old games"
        )
    except HTTPException:
        raise
    except Exception as exc:
        safe_error_response(exc, context="cleanup_old_games")


@router.delete("/game/{session_id}")
@limiter.limit("5/minute")
async def delete_game(
    request: Request, session_id: str, _=Depends(require_admin_key)
) -> dict:
    """Delete a specific game session (admin only)."""
    validate_session_id(session_id)
    try:
        success, response = GameManager.delete_game(session_id)
        if success:
            logger.info("Game %s deleted", session_id)
            return response
        raise HTTPException(
            status_code=400,
            detail=response.get("message", "Failed to delete game"),
        )
    except HTTPException:
        raise
    except Exception as exc:
        safe_error_response(exc, context="delete_game")
