#!/bin/bash
#
# Baby Safety Cam - Cloudflare Tunnel 실행
#

TUNNEL_NAME="baby-cam-e9a2888148d3"

echo "============================================"
echo "  Baby Safety Cam - 터널 시작"
echo "============================================"
echo ""
echo "  외부 접속 URL: https://$TUNNEL_NAME.cfargotunnel.com"
echo ""
echo "  종료: Ctrl+C"
echo ""
echo "============================================"
echo ""

cloudflared tunnel run "$TUNNEL_NAME"
