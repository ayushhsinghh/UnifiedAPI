#!/bin/bash

# Production Server Startup - With SUDO for HTTPS on port 443
# Or HTTP on port 8000 without sudo

set -e

cd /home/ubuntu/video-transcriber/app

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║     🚀 Video Transcriber - Production Startup                  ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Check MongoDB
echo "✓ Checking MongoDB..."
if ! pgrep mongod > /dev/null; then
    echo "  Starting MongoDB..."
    mongod --quiet &
    sleep 2
fi
echo "✓ MongoDB running"
echo ""

# Check Certificates
CERT_FILE="/home/ubuntu/video-transcriber/app/certs/cert.pem"
KEY_FILE="/home/ubuntu/video-transcriber/app/certs/key.pem"

if [ -f "$CERT_FILE" ] && [ -f "$KEY_FILE" ]; then
    echo "✓ SSL certificates found"
    EXPIRY=$(openssl x509 -in "$CERT_FILE" -noout -enddate | cut -d= -f2)
    echo "✓ Certificate expires: $EXPIRY"
    echo ""
    
    # Check if running with sudo
    if [ "$EUID" -eq 0 ]; then
        echo "╔════════════════════════════════════════════════════════════════╗"
        echo "║  🔐 HTTPS Server Starting (Port 443)                           ║"
        echo "║  URL: https://api.ayush.org                                    ║"
        echo "╚════════════════════════════════════════════════════════════════╝"
        echo ""
        python3 main.py \
            --host 0.0.0.0 \
            --port 443 \
            --cert-file "$CERT_FILE" \
            --key-file "$KEY_FILE"
    else
        echo "⚠️  Port 443 requires sudo. Running on port 8443 instead..."
        echo ""
        echo "╔════════════════════════════════════════════════════════════════╗"
        echo "║  🔐 HTTPS Server Starting (Port 8443)                          ║"
        echo "║  URL: https://api.ayush.org:8443                              ║"
        echo "║  (Point your domain to this with a reverse proxy, or use sudo) ║"
        echo "╚════════════════════════════════════════════════════════════════╝"
        echo ""
        python3 main.py \
            --host 0.0.0.0 \
            --port 8443 \
            --cert-file "$CERT_FILE" \
            --key-file "$KEY_FILE"
    fi
else
    echo "⚠️  SSL certificates not found"
    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║  🌐 HTTP Server Starting (Port 8000)                           ║"
    echo "║  URL: http://api.ayush.org:8000                               ║"
    echo "║  URL: http://80.225.207.201:8000                              ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "To enable HTTPS:"
    echo "1. Generate Let's Encrypt certificate:"
    echo "   sudo certbot certonly --standalone -d api.ayush.org"
    echo ""
    echo "2. Copy to app directory:"
    echo "   sudo cp /etc/letsencrypt/live/api.ayush.org/fullchain.pem certs/cert.pem"
    echo "   sudo cp /etc/letsencrypt/live/api.ayush.org/privkey.pem certs/key.pem"
    echo "   sudo chown ubuntu:ubuntu certs/*"
    echo ""
    echo "3. Run with sudo:"
    echo "   sudo bash start_production_https.sh"
    echo ""
    
    python3 main.py \
        --host 0.0.0.0 \
        --port 8000
fi
