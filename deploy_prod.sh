#!/bin/bash
set -e

# ============================================
# Baby AI Cam - Production Deployment Script
# Target: gq@10.11.100.56
# Ports: 54291 (web UI)
# Ollama: localhost:11434 (default, internal only)
# ============================================

REMOTE_HOST="gq@10.11.100.56"
REMOTE_DIR="~/works/baby-ai-cam/baby-ai-cam-1"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

WEB_PORT=54291

echo "=== Baby AI Cam Production Deploy ==="
echo "Target: $REMOTE_HOST:$REMOTE_DIR"
echo "Web UI Port: $WEB_PORT"
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
cat <<'ENVEOF' | ssh "$REMOTE_HOST" "cat > $REMOTE_DIR/.env"
FLASK_HOST=0.0.0.0
FLASK_PORT=54291
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=moondream

DISCORD_WARNING_WEBHOOK=https://discord.com/api/webhooks/1469017862223036712/BcLQ9mpmV60taBuWl2o3D_8hRxWGFonx2FYyTAg8-GR7OudmioBDJCj3SkSeMcYRhqJh
DISCORD_STATUS_WEBHOOK=https://discord.com/api/webhooks/1469018038211969065/KxE0FjQ_b1VpgMKg354YO1UMZW66CbjKTY_aTdefuf1irrnSwx2uoCDLGQY23bsBDz2d

CAMERA_ID=0
MICROPHONE_ID=0
VISION_FPS=2
MOTION_FPS=15
VIDEO_STREAM_FPS=30
STATUS_REPORT_INTERVAL=300
ENVEOF

# --- Step 6: Install Python dependencies + configure Ollama ---
echo "[6/8] Installing deps + configuring Ollama..."
ssh "$REMOTE_HOST" "cd $REMOTE_DIR && ~/.local/bin/uv sync 2>&1 | tail -5"

# Revert Ollama to default port (localhost:11434 only)
ssh "$REMOTE_HOST" 'sudo rm -f /etc/systemd/system/ollama.service.d/override.conf && sudo systemctl daemon-reload && sudo systemctl restart ollama'
sleep 2

# Wait for Ollama
ssh "$REMOTE_HOST" 'for i in $(seq 1 15); do curl -s http://localhost:11434/api/tags >/dev/null 2>&1 && echo "Ollama ready on 11434!" && break || (echo "waiting..." && sleep 2); done'

# Pull moondream model
echo "Pulling moondream model..."
ssh "$REMOTE_HOST" "ollama pull moondream"

# --- Step 7: Install systemd service ---
echo "[7/8] Installing systemd service..."
REMOTE_DIR_EXPANDED=$(ssh "$REMOTE_HOST" "echo $REMOTE_DIR")
UV_PATH=$(ssh "$REMOTE_HOST" 'readlink -f ~/.local/bin/uv')

cat <<SVCEOF | ssh "$REMOTE_HOST" "sudo tee /etc/systemd/system/baby-ai-cam.service > /dev/null"
[Unit]
Description=Baby AI Cam Monitor
After=network.target ollama.service
Wants=ollama.service

[Service]
Type=simple
User=gq
WorkingDirectory=${REMOTE_DIR_EXPANDED}
ExecStart=${UV_PATH} run python -m src.main
Restart=always
RestartSec=10
StandardOutput=append:/home/gq/baby-ai-cam.log
StandardError=append:/home/gq/baby-ai-cam.log
Environment=HOME=/home/gq
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
SVCEOF

ssh "$REMOTE_HOST" 'sudo systemctl daemon-reload && sudo systemctl enable baby-ai-cam.service'
echo "systemd service installed and enabled"

# --- Step 8: Start the application ---
echo "[8/8] Starting Baby AI Cam..."

# Stop any existing instance (nohup or systemd)
ssh "$REMOTE_HOST" 'ps aux | grep "src.main" | grep -v grep | awk "{print \$2}" | xargs -r kill 2>/dev/null; sleep 1; echo "cleaned old processes"'

# Clear log and start via systemd
ssh "$REMOTE_HOST" '> ~/baby-ai-cam.log && sudo systemctl restart baby-ai-cam.service'
sleep 5

# Verify
ssh "$REMOTE_HOST" 'if systemctl is-active --quiet baby-ai-cam.service; then echo "=== Baby AI Cam is running (systemd) ==="; else echo "ERROR: Service failed"; sudo systemctl status baby-ai-cam.service --no-pager; journalctl -u baby-ai-cam.service --no-pager -n 20; exit 1; fi'

echo ""
echo "=== Deployment Complete ==="
echo "Web UI: http://10.11.100.56:$WEB_PORT"
echo "Service: sudo systemctl {start|stop|restart|status} baby-ai-cam.service"
echo "Logs: tail -f ~/baby-ai-cam.log"
