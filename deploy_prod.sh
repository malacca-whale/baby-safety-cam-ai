#!/bin/bash
set -e

# ============================================
# Baby AI Cam - Production Deployment Script
# Target: gq@10.11.100.57
# Ports: 54291 (web UI), 54292 (Ollama)
# ============================================

REMOTE_HOST="gq@10.11.100.57"
REMOTE_DIR="~/works/baby-ai-cam/baby-ai-cam-1"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

WEB_PORT=54291
OLLAMA_PORT=54292

echo "=== Baby AI Cam Production Deploy ==="
echo "Target: $REMOTE_HOST:$REMOTE_DIR"
echo "Web UI Port: $WEB_PORT"
echo "Ollama Port: $OLLAMA_PORT"
echo ""

# --- Step 1: Prepare remote directory ---
echo "[1/8] Preparing remote directory..."
ssh "$REMOTE_HOST" "mkdir -p ~/works/baby-ai-cam/baby-ai-cam-1"

# --- Step 2: Sync project files ---
echo "[2/8] Syncing project files..."
rsync -avz --delete \
    --exclude '.venv' \
    --exclude '.env' \
    --exclude '__pycache__' \
    --exclude '*.db' \
    --exclude '*.db-wal' \
    --exclude '*.db-shm' \
    --exclude '.git' \
    --exclude '.DS_Store' \
    --exclude 'node_modules' \
    --exclude '*.png' \
    --exclude '*.jpg' \
    --exclude '*.jpeg' \
    --exclude '.ruff_cache' \
    --exclude '.mypy_cache' \
    --exclude '.pytest_cache' \
    --exclude '.playwright-mcp' \
    --exclude 'test_videos' \
    "$LOCAL_DIR/" "$REMOTE_HOST:$REMOTE_DIR/"

# --- Step 3: Install uv on remote if needed ---
echo "[3/8] Ensuring uv is installed..."
ssh "$REMOTE_HOST" 'command -v ~/.local/bin/uv >/dev/null 2>&1 && echo "uv already installed" || (curl -LsSf https://astral.sh/uv/install.sh | sh)'

# --- Step 4: Install system dependencies ---
echo "[4/8] Installing system dependencies..."
ssh "$REMOTE_HOST" 'sudo apt-get install -y -qq libportaudio2 libsndfile1 libgl1 libglib2.0-0 2>&1 | tail -3'

# --- Step 5: Create production .env ---
echo "[5/8] Creating production .env..."
cat <<ENVEOF | ssh "$REMOTE_HOST" "cat > $REMOTE_DIR/.env"
FLASK_HOST=0.0.0.0
FLASK_PORT=${WEB_PORT}
OLLAMA_URL=http://localhost:${OLLAMA_PORT}
OLLAMA_MODEL=qwen3-vl:latest

DISCORD_WARNING_WEBHOOK=https://discord.com/api/webhooks/1469017862223036712/BcLQ9mpmV60taBuWl2o3D_8hRxWGFonx2FYyTAg8-GR7OudmioBDJCj3SkSeMcYRhqJh
DISCORD_STATUS_WEBHOOK=https://discord.com/api/webhooks/1469018038211969065/KxE0FjQ_b1VpgMKg354YO1UMZW66CbjKTY_aTdefuf1irrnSwx2uoCDLGQY23bsBDz2d

CAMERA_ID=0
MICROPHONE_ID=0
VISION_FPS=2
MOTION_FPS=15
VIDEO_STREAM_FPS=30
STATUS_REPORT_INTERVAL=300
ENVEOF

# --- Step 6: Install Python dependencies ---
echo "[6/8] Installing Python dependencies..."
ssh "$REMOTE_HOST" "cd $REMOTE_DIR && ~/.local/bin/uv sync 2>&1 | tail -5"

# --- Step 7: Configure Ollama on port 54292 + update + pull model ---
echo "[7/8] Configuring Ollama on port $OLLAMA_PORT..."

# Update Ollama
ssh "$REMOTE_HOST" 'curl -fsSL https://ollama.com/install.sh | sh 2>&1 | tail -3'

# Create systemd override for port
ssh "$REMOTE_HOST" "sudo mkdir -p /etc/systemd/system/ollama.service.d"
cat <<EOF | ssh "$REMOTE_HOST" "sudo tee /etc/systemd/system/ollama.service.d/override.conf > /dev/null"
[Service]
Environment="OLLAMA_HOST=0.0.0.0:${OLLAMA_PORT}"
EOF
ssh "$REMOTE_HOST" 'sudo systemctl daemon-reload && sudo systemctl restart ollama'

# Wait for Ollama to be ready
echo "Waiting for Ollama on port $OLLAMA_PORT..."
ssh "$REMOTE_HOST" 'for i in $(seq 1 15); do curl -s http://localhost:'"$OLLAMA_PORT"'/api/tags >/dev/null 2>&1 && echo "Ollama ready!" && break || (echo "waiting..." && sleep 2); done'

# Pull qwen3-vl model
echo "Pulling qwen3-vl model..."
ssh "$REMOTE_HOST" "OLLAMA_HOST=http://localhost:$OLLAMA_PORT ollama pull qwen3-vl:latest"

# --- Step 8: Start the application ---
echo "[8/8] Starting Baby AI Cam..."

# Kill any existing instance
ssh "$REMOTE_HOST" 'kill $(pgrep -f "python.*src.main") 2>/dev/null; sleep 1; echo "cleaned"'

# Start the app with nohup
ssh "$REMOTE_HOST" "cd $REMOTE_DIR && nohup ~/.local/bin/uv run python -m src.main > ~/baby-ai-cam.log 2>&1 &"
sleep 4

# Verify
ssh "$REMOTE_HOST" 'if pgrep -f "python.*src.main" > /dev/null; then echo "=== Baby AI Cam is running! ==="; else echo "ERROR: Check ~/baby-ai-cam.log"; tail -20 ~/baby-ai-cam.log; exit 1; fi'

echo ""
echo "=== Deployment Complete ==="
echo "Web UI:  http://10.11.100.57:$WEB_PORT"
echo "Ollama:  http://10.11.100.57:$OLLAMA_PORT"
