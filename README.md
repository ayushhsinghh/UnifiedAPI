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

The app will be available at: **http://localhost:8000**

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

The app starts at: **http://localhost:8000**

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

# Delete job
curl -X DELETE http://localhost:8000/api/jobs/job_xyzw
```

---

## 🏗️ Project Structure

```
video-transcriber/
├── app/
│   ├── main.py                 # FastAPI application
│   ├── worker.py               # Transcription worker
│   ├── database.py             # MongoDB operations
│   ├── storage.py              # Job status enums
│   ├── requirements.txt         # Python dependencies
│   ├── list_jobs.py            # CLI utility to list jobs
│   ├── delete_jobs.py          # CLI utility to delete jobs
│   ├── examples_list_jobs.py   # Usage examples
│   ├── frontend/
│   │   └── index.html          # Web UI
│   ├── uploads/                # Temporary upload storage
│   ├── outputs/                # SRT subtitle files
│   └── app.log                 # Application logs
├── setup.sh                    # Automated setup script
├── QUICK_START.md              # Quick reference
├── MONGODB_SETUP.md            # MongoDB configuration
├── TROUBLESHOOTING.md          # Performance & troubleshooting
├── IMPROVEMENTS.md             # UI improvements summary
└── CHANGES_SUMMARY.md          # Technical changes log
```

---

## 🔧 Configuration

### Job ID Generation

Job IDs are short and memorable: `job_abc123`

To change length, edit [main.py](app/main.py):
```python
def generate_job_id() -> str:
    chars = string.ascii_lowercase + string.digits
    random_part = ''.join(random.choices(chars, k=8))  # Change 8 to desired length
    return f"job_{random_part}"
```

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

---

## 🐛 Troubleshooting

### App Won't Start

```bash
# Check Python version
python3 --version  # Must be 3.8+

# Check if port 8000 is in use
lsof -i :8000

# Try different port
python3 main.py --port 8001
```

### MongoDB Connection Failed

```bash
# Check if MongoDB is running
pgrep mongod

# If not, start it
mongod &

# Test connection
mongo
```

### Transcription Takes Too Long

- First time takes 1-2 minutes (model download)
- Large videos take longer (proportional to duration)
- Using CPU instead of GPU is slower
- Check app.log for progress: `tail -f app.log`

### UI Not Loading

- Check browser for CORS errors (F12 → Console)
- Verify API is accessible: `curl http://localhost:8000/api/jobs`
- Clear browser cache (Ctrl+Shift+Delete)

### More Issues?

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

---

## 📚 Documentation

- **[QUICK_START.md](QUICK_START.md)** - Quick reference
- **[MONGODB_SETUP.md](MONGODB_SETUP.md)** - MongoDB configuration & API docs
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - Performance tips & debugging
- **[IMPROVEMENTS.md](IMPROVEMENTS.md)** - UI/performance changes summary
- **[CHANGES_SUMMARY.md](CHANGES_SUMMARY.md)** - Technical details of all changes

---

## 📝 Logging

Logs are written to `app/app.log` and console:

```bash
# Real-time logs
tail -f app.log

# Search for errors
grep ERROR app.log

# Search for specific job
grep job_abc123 app.log

# Count events
grep "Starting transcription" app.log | wc -l
```

---

## 💡 Performance Tips

1. **Use smaller job lengths** - Don't poll excessively with "Check Status"
2. **Start with small videos** - Test with 5-10 minute clips first
3. **Close other apps** - Free up CPU/RAM during transcription
4. **Use GPU if available** - Change device from "cpu" to "cuda" in worker.py
5. **Compress videos** - Smaller file sizes upload faster
6. **Build an index** - MongoDB indexes created automatically on first run

---

## 🔐 Security Notes

- **CORS Enabled** - Currently allows all origins (fine for local use)
- **File Size Limit** - 1GB max per upload
- **No Authentication** - Add auth middleware for production
- **Directory Listing** - Disabled by default

For production:
1. Restrict CORS origins
2. Add authentication/API keys
3. Set up HTTPS/SSL
4. Implement rate limiting
5. Use environment variables for config

---

## 🤝 Contributing

To improve the application:

1. Check [IMPROVEMENTS.md](IMPROVEMENTS.md) for recent changes
2. Review [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for known issues
3. Check [app.log](app/app.log) for errors

---

## 📄 License

This project uses:
- FastAPI (MIT License)
- faster-whisper (MIT License)
- MongoDB (SSPL)
- FFmpeg (LGPL)

---

## 🎉 Getting Help

If something isn't working:

1. **Check logs**: `tail -f app.log`
2. **Verify setup**: Run `bash setup.sh`
3. **Read docs**: See [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
4. **Test API**: `curl http://localhost:8000/api/jobs`

---

**Happy transcribing! 🎬**
