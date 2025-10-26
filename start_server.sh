#!/bin/bash

echo "========================================================"
echo "Starting Server with Clean Environment"
echo "========================================================"
echo ""

# Kill any existing servers
pkill -f "python.*run.py" 2>/dev/null && echo "✓ Stopped existing servers" || echo "ℹ No existing servers"
sleep 1

# Unset any conflicting environment variables
unset FLASK_ENV
unset CORS_ORIGINS
unset SECRET_KEY
unset JWT_SECRET_KEY

echo "✓ Cleared shell environment variables"
echo ""

# Load .env file explicitly
if [ -f .env ]; then
    echo "✓ Loading configuration from .env file:"
    export $(cat .env | grep -v '^#' | grep -v '^$' | xargs)
    echo "  FLASK_ENV=${FLASK_ENV}"
    echo "  CORS_ORIGINS=${CORS_ORIGINS}"
else
    echo "✗ Error: .env file not found!"
    exit 1
fi

echo ""
echo "========================================================"
echo "Starting server on http://0.0.0.0:5000"
echo "Your Cloudflare tunnel should now work!"
echo "========================================================"
echo ""

# Start the server
python run.py
