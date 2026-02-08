# Guess the Imposter - Game API Guide

## Overview

A fun real-time multiplayer game where players try to identify the "imposter" who has a different topic than everyone else. The game involves discussion, deduction, and social deception!

## Features

### 🎮 Game Mechanics

- **Create Games**: Set up a new game with a custom category and invite others
- **Join Games**: Browse available games and join with a unique player ID
- **Topic Generation**: AI-powered topic generation using DeepSeek model
- **Two Topics**: One topic for regular players, one different topic for the imposter
- **Discussion Phase**: 3 minutes of open discussion where the imposter tries to blend in
- **Voting Phase**: 1 minute where players vote on who they think is the imposter
- **Real-time Updates**: Live player list and game state synchronization
- **Game Results**: Detailed results showing winners and losers

### 📊 Database Schema

#### Game Sessions Collection (`game_sessions`)
```json
{
  "session_id": "ABC123XY",
  "creator_id": "uuid",
  "game_category": "animals",
  "player_topic": "Lion",
  "imposter_topic": "Tiger",
  "max_players": 8,
  "status": "waiting|playing|ended",
  "players_list": ["player_id1", "player_id2"],
  "imposter_id": "player_id_of_imposter",
  "current_phase": "discussion|voting|result",
  "votes": {"voter_id": "voted_for_id"},
  "game_result": {},
  "created_at": "timestamp",
  "started_at": "timestamp",
  "ended_at": "timestamp"
}
```

#### Game Players Collection (`game_players`)
```json
{
  "session_id": "ABC123XY",
  "player_id": "uuid",
  "player_name": "John Doe",
  "is_imposter": false,
  "is_alive": true,
  "votes_received": 2,
  "joined_at": "timestamp"
}
```

## API Endpoints

### 1. Create Game
**POST** `/api/game/create`

Create a new game session.

**Request Body:**
```json
{
  "player_name": "John",
  "game_category": "animals",
  "max_players": 8
}
```

**Response:**
```json
{
  "success": true,
  "session_id": "ABC123XY",
  "player_id": "uuid-of-creator",
  "game_category": "animals",
  "player_topic": "Lion",
  "imposter_topic": "Tiger",
  "max_players": 8,
  "message": "Game created successfully"
}
```

### 2. Join Game
**POST** `/api/game/{session_id}/join`

Join an existing game session.

**Request Body:**
```json
{
  "player_name": "Jane"
}
```

**Response:**
```json
{
  "success": true,
  "session_id": "ABC123XY",
  "player_id": "uuid-of-player",
  "game_category": "animals",
  "player_count": 3,
  "max_players": 8,
  "message": "Joined game successfully"
}
```

### 3. Start Game
**POST** `/api/game/{session_id}/start`

Start the game and assign the imposter role randomly.

**Response:**
```json
{
  "success": true,
  "session_id": "ABC123XY",
  "game_status": "playing",
  "imposter_assigned": true,
  "message": "Game started"
}
```

### 4. Get Game Info
**GET** `/api/game/{session_id}?player_id={player_id}`

Get current game information. Shows different topic based on player role.

**Response:**
```json
{
  "success": true,
  "session_id": "ABC123XY",
  "game_category": "animals",
  "status": "playing",
  "current_phase": "discussion",
  "player_count": 3,
  "max_players": 8,
  "your_topic": "Lion",
  "topic_type": "player",
  "discussion_time": 180,
  "voting_time": 60,
  "players": [
    {
      "player_id": "uuid1",
      "player_name": "John",
      "is_alive": true,
      "votes_received": 0
    },
    {
      "player_id": "uuid2",
      "player_name": "Jane",
      "is_alive": true,
      "votes_received": 1
    }
  ]
}
```

### 5. Transition to Voting
**POST** `/api/game/{session_id}/transition-voting`

End discussion phase and move to voting phase.

**Response:**
```json
{
  "success": true,
  "current_phase": "voting",
  "message": "Game transitioned to voting phase"
}
```

### 6. Submit Vote
**POST** `/api/game/{session_id}/vote?player_id={player_id}`

Submit a vote for who you think is the imposter.

**Request Body:**
```json
{
  "voted_for_id": "uuid-of-voted-player"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Vote registered"
}
```

### 7. End Voting
**POST** `/api/game/{session_id}/end-voting`

End voting phase and determine the game result.

**Response:**
```json
{
  "success": true,
  "game_result": {
    "voted_out_id": "uuid-of-voted-player",
    "voted_out_name": "Jane",
    "is_imposter_caught": true,
    "imposter_id": "uuid-of-imposter",
    "winners": "All other players",
    "message": "Imposter caught!"
  }
}
```

### 8. List Available Games
**GET** `/api/games/available`

List all games waiting for players.

**Response:**
```json
{
  "success": true,
  "games": [
    {
      "session_id": "ABC123XY",
      "game_category": "animals",
      "player_count": 3,
      "max_players": 8,
      "created_at": "2024-02-08T10:30:00"
    }
  ],
  "total": 1
}
```

### 9. Delete Game
**DELETE** `/api/game/{session_id}`

Delete a game session and all associated players.

**Response:**
```json
{
  "success": true,
  "message": "Game deleted"
}
```

## Game Flow

1. **Player 1 creates a game** → Gets a session ID (e.g., "ABC123XY")
2. **Other players join** using the session ID
3. **Creator starts the game** when ready (min 2 players)
4. **System assigns one random player as imposter** (imposter gets different topic)
5. **Discussion Phase (3 minutes)**:
   - All players discuss the topic
   - Imposter tries to blend in without knowing the real topic
   - Others try to identify the imposter through discussion
6. **Voting Phase (1 minute)**:
   - All players vote for who they think is the imposter
   - Player with most votes is voted out
7. **Game Result**:
   - If imposter was caught → All other players win
   - If imposter survived → Imposter wins

## Frontend Features

The web interface includes:

- **Home Screen**:
  - Create new game (choose category and player count)
  - Join existing game (enter game code or browse available games)
  
- **Lobby**:
  - Display game code for others to join
  - Show connected players
  - Start game button (enabled when 2+ players)
  
- **Game Screen**:
  - Display your topic (imposter sees different topic)
  - Real-time player list with status
  - Timer for discussion phase
  - Vote buttons during voting phase
  
- **Result Screen**:
  - Show who was voted out
  - Show if imposter was caught
  - Display winners
  - Player results table

## Topic Categories

Available categories for topic generation:
- 🦁 Animals
- 👨‍💼 Professions
- 🌍 Countries
- 🍎 Fruits
- ⚽ Sports
- 🎬 Movies
- 🦸 Superheroes
- 🍕 Foods

## Technologies Used

- **Backend**: FastAPI, Python
- **Database**: MongoDB
- **AI Model**: DeepSeek (via Hugging Face Transformers)
- **Frontend**: HTML5, CSS3, Vanilla JavaScript
- **Real-time Updates**: Polling mechanism (updates every 2 seconds)

## Running the Application

```bash
# Start the server
python main.py --host 0.0.0.0 --port 8000

# Enable auto-reload for development
python main.py --host 0.0.0.0 --port 8000 --reload

# With HTTPS (SSL)
python main.py --host 0.0.0.0 --port 8000 --cert-file certs/cert.pem --key-file certs/key.pem
```

## Example Game Scenario

**Setup**: 4 players join a game with category "Animals"

- **Regular Players Topic**: "Lion"
- **Imposter Topic**: "Tiger"

**Discussion** (3 minutes):
- Player 1: "This animal is known as the king of the jungle"
- Player 2: "It's very dangerous and has a loud roar"
- Player 3 (Imposter): "Yes, and it has beautiful stripes"
- Player 4: "Wait, that doesn't match. Stripes? That's weird."

**Voting**: 
- Players vote for Player 3 (the imposter)
- Player 3 gets 3 votes and is voted out

**Result**:
- ✅ Imposter caught!
- 🏆 Winners: Players 1, 2, 4

## Error Handling

All API endpoints return appropriate HTTP status codes:
- `200`: Successful request
- `400`: Bad request (invalid game state, etc.)
- `404`: Game not found
- `500`: Server error

## Notes

- Each player gets a unique `player_id` when creating or joining a game
- The session `session_id` is displayed for sharing with others
- Topics are generated using the DeepSeek AI model for variety
- Voting uses simple majority (player with most votes is voted out)
- All timestamps are in UTC
- Database uses MongoDB for scalability

## Future Enhancements

- WebSocket support for real-time updates (instead of polling)
- Multiple rounds per session
- Custom topic input
- Leaderboard system
- Chat messages during discussion
- Role-based analysis (show who suspected whom)
- Mobile app
- Spectator mode
- Save game replays
