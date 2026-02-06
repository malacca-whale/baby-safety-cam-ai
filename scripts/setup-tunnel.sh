#!/bin/bash
#
# Baby Safety Cam - Cloudflare Tunnel 설정 스크립트
# 외부에서 접속 가능한 고정 URL을 생성합니다.
#

set -e

TUNNEL_NAME="baby-cam-e9a2888148d3"
LOCAL_PORT="${1:-8080}"
CONFIG_DIR="$HOME/.cloudflared"
CONFIG_FILE="$CONFIG_DIR/config.yml"

echo "============================================"
echo "  Baby Safety Cam - Cloudflare Tunnel 설정"
echo "============================================"
echo ""

# 1. cloudflared 설치 확인
if ! command -v cloudflared &> /dev/null; then
    echo "[1/4] cloudflared 설치 중..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        brew install cloudflared
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
        sudo dpkg -i cloudflared.deb
        rm cloudflared.deb
    else
        echo "지원하지 않는 OS입니다. 수동으로 cloudflared를 설치해주세요."
        exit 1
    fi
else
    echo "[1/4] cloudflared 이미 설치됨 ✓"
fi

# 2. 로그인 확인
if [ ! -f "$CONFIG_DIR/cert.pem" ]; then
    echo "[2/4] Cloudflare 로그인 필요..."
    echo "     브라우저가 열리면 Cloudflare 계정으로 로그인하세요."
    cloudflared tunnel login
else
    echo "[2/4] Cloudflare 로그인 완료 ✓"
fi

# 3. 터널 생성 (이미 존재하면 스킵)
if cloudflared tunnel list | grep -q "$TUNNEL_NAME"; then
    echo "[3/4] 터널 '$TUNNEL_NAME' 이미 존재함 ✓"
else
    echo "[3/4] 터널 '$TUNNEL_NAME' 생성 중..."
    cloudflared tunnel create "$TUNNEL_NAME"
fi

# 터널 ID 가져오기
TUNNEL_ID=$(cloudflared tunnel list | grep "$TUNNEL_NAME" | awk '{print $1}')
echo "     터널 ID: $TUNNEL_ID"

# 4. 설정 파일 생성
echo "[4/4] 설정 파일 생성 중..."

cat > "$CONFIG_FILE" << EOF
tunnel: $TUNNEL_ID
credentials-file: $CONFIG_DIR/$TUNNEL_ID.json

ingress:
  - hostname: $TUNNEL_NAME.cfargotunnel.com
    service: http://localhost:$LOCAL_PORT
  - service: http_status:404
EOF

echo ""
echo "============================================"
echo "  설정 완료!"
echo "============================================"
echo ""
echo "  터널 이름: $TUNNEL_NAME"
echo "  외부 URL:  https://$TUNNEL_NAME.cfargotunnel.com"
echo "  로컬 포트: $LOCAL_PORT"
echo ""
echo "  터널 시작 명령어:"
echo "    cloudflared tunnel run $TUNNEL_NAME"
echo ""
echo "  또는 간단히:"
echo "    ./scripts/run-tunnel.sh"
echo ""
