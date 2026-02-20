"""
Game status and phase constants for the Guess-the-Imposter game.
"""

# Game status values (stored in session.status)
GAME_STATUS_WAITING = "waiting"
GAME_STATUS_PLAYING = "playing"
GAME_STATUS_VOTING = "voting"
GAME_STATUS_ENDED = "ended"

# Game phase values (stored in session.current_phase)
GAME_PHASE_WAITING = "waiting"
GAME_PHASE_DISCUSSION = "discussion"
GAME_PHASE_VOTING = "voting"
GAME_PHASE_REVEAL = "reveal"
GAME_PHASE_RESULT = "result"

# Placeholder topics used while Gemini generates real ones
PLACEHOLDER_PLAYER_TOPIC = "Sun"
PLACEHOLDER_IMPOSTER_TOPIC = "Moon"
