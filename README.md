# 🎬 Video Transcriber

Convert videos to subtitles with AI-powered transcription powered by OpenAI's Whisper via faster-whisper.

## ✨ Features

- 🎥 Upload video files and auto-transcribe
- 🌍 Multi-language support (auto-detection)
- 🔄 Translate subtitles to English
- 📊 Real-time progress tracking
- 💾 MongoDB persistence for job history
- 🎨 Modern, responsive web UI
- ⚡ No automatic polling - manual status checks only
- 🔍 View all jobs with filtering
- 🗑️ Delete completed/failed jobs
- 📥 Download SRT subtitles

---

## 🚀 Quick Start

### 1. Prerequisites

- Python 3.8+
- MongoDB 4.0+
- FFmpeg
- 2GB free disk space

### 2. Install & Run

```bash
cd /home/ubuntu/video-transcriber

# First time setup (install dependencies)
bash setup.sh

# Make sure MongoDB is running
mongod &

# Start the application
cd app
python3 main.py
```

The app will be available at: **http://localhost:8000** (web UI). If deployed, the Transcribe UI is available at https://subs.ayush.ltd and the Game UI at https://game.ayush.ltd.

---

## 📋 Setup Instructions

### Step 1: Install Python Dependencies

```bash
# Navigate to app directory
cd app

# Install requirements
pip3 install -r requirements.txt
```

Or use the automated setup script:
```bash
bash ../setup.sh
```

### Step 2: Start MongoDB

**Option A: Local MongoDB**
```bash
mongod &
```

**Option B: Docker**
```bash
docker run -d -p 27017:27017 --name mongo mongo:latest
```

**Option C: Verify it's running**
```bash
# Check if MongoDB is running
pgrep mongod

# Or connect to it
mongo
```

### Step 3: Start the Application

```bash
cd app

# Simple start
python3 main.py

# Or with auto-reload (development)
uvicorn main:app --reload

# Or customize host/port
python3 main.py --host 0.0.0.0 --port 8000
```

The app starts at: **http://localhost:8000** (web UI). If hosted, access the Transcribe UI at https://subs.ayush.ltd and the Game UI at https://game.ayush.ltd.

---

## 🎯 Usage

### Via Web UI

1. Open http://localhost:8000 in your browser
2. Select a video file (MP4, MKV, AVI, etc.)
3. Optional: Choose language and enable translation
4. Click "Upload & Transcribe"
5. Click "Check Status" to see progress
6. When done, click "Download Subtitles"

### Via CLI (list_jobs.py)

```bash
cd app

# List all jobs
python3 list_jobs.py

# List only running jobs
python3 list_jobs.py --status running

# List completed jobs
python3 list_jobs.py --status done
```

### Via CLI (delete_jobs.py)

```bash
cd app

# Delete a specific job
python3 delete_jobs.py job_abc123

# Delete all failed jobs
python3 delete_jobs.py --status failed

# Delete all done jobs
python3 delete_jobs.py --status done
```

### Via REST API

```bash
# Create job
curl -X POST http://localhost:8000/api/jobs \
  -F "file=@video.mp4" \
  -F "language=en" \
  -F "translate=true"

# Response
# {
#   "job_id": "job_xyzw",
#   "status": "pending"
# }

# Check status
curl http://localhost:8000/api/jobs/job_xyzw

# Download subtitles
curl http://localhost:8000/api/jobs/job_xyzw/subtitles -o subtitles.srt

# List all jobs
curl http://localhost:8000/api/jobs

# List running jobs
curl http://localhost:8000/api/jobs?status=running

```

## 🎮 Game API (Endpoints)

The Game API provides endpoints to create and manage multiplayer "Guess the Imposter" sessions. Base path: `/api`.

### Core Game Endpoints

Create a game (creator):
```
POST /api/game/create
Body: { "player_name": "Alice", "game_category": "animals", "max_players": 8 }
```

Join a game:
```
POST /api/game/{session_id}/join
Body: { "player_name": "Bob" }
```

Start game (creator only):
```
POST /api/game/{session_id}/start
Body: { "player_id": "<creator_id>" }
```

Get game state (returns players, phase, your topic):
```
GET /api/game/{session_id}?player_id={player_id}
```

Transition to voting (end discussion):
```
POST /api/game/{session_id}/transition-voting
```

Submit a vote:
```
POST /api/game/{session_id}/vote
Body: { "player_id": "<you>", "voted_for_id": "<target>" }
```

End voting (server-side trigger):
```
POST /api/game/{session_id}/end-voting
```

Get reveal/result:
```
GET /api/game/{session_id}/result
```

Start a new round (creator only):
```
POST /api/game/{session_id}/new-round
```

Player heartbeat (keep player active):
```
POST /api/game/{session_id}/heartbeat
Body: { "player_id": "..." }
```

Maintenance endpoints:
```
POST /api/games/cleanup-inactive
POST /api/games/cleanup
DELETE /api/game/{session_id}
```

---

## 🏗️ Project Structure

```
video-transcriber/
├── app/
│   ├── main.py                 # FastAPI application
│   ├── worker.py               # Transcription worker
│   ├── database.py             # MongoDB operations
│   ├── game.py                 # Guess the Imposter game logic
│   ├── Gemini.py               # Gemini API integration (if applicable)
│   ├── logging_config.py       # Logging configuration
│   ├── storage.py              # Job status enums
│   ├── requirements.txt        # Python dependencies
│   └── app.log                 # Application logs
├── run.sh                      # Start the application
├── video-transcriber.service   # Systemd service file
```

---

## 🔧 Configuration

### MongoDB URL

Default: `mongodb://localhost:27017`

To change, edit [database.py](app/database.py):
```python
MONGODB_URL = "mongodb://localhost:27017"
DATABASE_NAME = "video_transcriber"
```

### Whisper Model Size

Default: `small` (good balance of speed/accuracy)

Options in [worker.py](app/worker.py):
- `tiny` - Fastest, less accurate
- `base` - Fast, decent accuracy
- `small` - Balanced (default)
- `medium` - Slower, better accuracy  
- `large` - Slowest, best accuracy

```python
model = WhisperModel(
    "small",  # Change model size here
    device="cpu",
    compute_type="int8"
)
```

---

## 📊 API Status Codes

```
POST /api/jobs
  200 OK - Job created
  400 Bad Request - Missing file
  500 Server Error - Upload failed

GET /api/jobs/{job_id}
  200 OK - Job found
  404 Not Found - Job doesn't exist

GET /api/jobs/{job_id}/subtitles
  200 OK - Subtitles ready for download
  404 Not Found - Job not found
  400 Bad Request - Transcription not complete

GET /api/jobs
  200 OK - Returns list of jobs

DELETE /api/jobs/{job_id}
  200 OK - Job deleted
  404 Not Found - Job doesn't exist
  500 Server Error - Deletion failed
```

### Transcription Takes Too Long

- First time takes 1-2 minutes (model download)
- Large videos take longer (proportional to duration)
- Using CPU instead of GPU is slower
- Check app.log for progress: `tail -f app.log`


## 🔐 Security Notes

- **CORS Enabled** - Currently allows all origins (fine for local use)
- **File Size Limit** - 1GB max per upload
- **No Authentication** - Add auth middleware for production (TODO)
- **Directory Listing** - Disabled by default

For production:
1. Restrict CORS origins
2. Add authentication/API keys
3. Set up HTTPS/SSL
4. Implement rate limiting
5. Use environment variables for config

---

## 🤝 Contributing

OPEN to contributions! To contribute:
1. Fork the repo
2. Create a new branch (`git checkout -b feature/my-feature`)
3. Make your changes and commit (`git commit -m "Add my feature"`)
4. Push to the branch (`git push origin feature/my-feature`)
5. Open a pull request should be well-documented and tested. Check existing issues for ideas or open a new one to discuss your idea.

---

## 📄 License

This project uses:
- FastAPI (MIT License)
- faster-whisper (MIT License)
- MongoDB (SSPL)
- FFmpeg (LGPL)

---
