#!/bin/bash
# Quick Start Script - Run this to start the app

cd /home/ubuntu/video-transcriber/app

echo "🎬 Video Transcriber - Starting..."
echo ""

# Check if MongoDB is running
if ! pgrep mongod > /dev/null; then
    echo "⚠️  MongoDB is not running."
    echo "Starting MongoDB in background..."
    mongod &
    sleep 2
    echo "✓ MongoDB started"
else
    echo "✓ MongoDB already running"
fi

echo ""
echo "Starting FastAPI application..."
echo ""

# Define certificate paths
CERT_FILE="/home/ubuntu/video-transcriber/app/certs/cert.pem"
KEY_FILE="/home/ubuntu/video-transcriber/app/certs/key.pem"

# Check if SSL certificates exist
if [ -f "$CERT_FILE" ] && [ -f "$KEY_FILE" ]; then
    echo "🔒 Using HTTPS with SSL certificates"
    echo "The app will be accessible at:"
    echo "  🔐 https://api.ayush.org:443"
    echo "  🔐 https://80.225.207.201:443"
    echo ""
    echo "Press Ctrl+C to stop the server"
    echo ""
    
    # Start the app with HTTPS
    python3 main.py --host 0.0.0.0 --port 443 --cert-file "$CERT_FILE" --key-file "$KEY_FILE"
else
    echo "⚠️  SSL certificates not found. Running in HTTP mode."
    echo "To enable HTTPS, generate certificates first:"
    echo "  bash setup_https.sh --self-signed"
    echo ""
    echo "The app will be accessible at:"
    echo "  🌐 http://api.ayush.org:8000"
    echo "  🌐 http://80.225.207.201:8000"
    echo ""
    echo "Press Ctrl+C to stop the server"
    echo ""
    
    # Start the app with HTTP
    python3 main.py --host 0.0.0.0 --port 8000
fi
