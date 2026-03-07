#!/bin/bash
# 안티그래비티 모바일 에이전트 — Tailscale 설정 스크립트
# Tailscale VPN을 통해 외부 네트워크에서도 모바일 에이전트에 접속할 수 있게 합니다.

echo "🌐 안티그래비티 — Tailscale 연동 설정"
echo "═══════════════════════════════════════════"
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

# 1. Tailscale 설치 확인
if command -v tailscale &>/dev/null || [ -d "/Applications/Tailscale.app" ]; then
    echo "✅ Tailscale이 설치되어 있습니다."
else
    echo "⚠️  Tailscale이 설치되어 있지 않습니다."
    echo ""
    echo "설치 방법:"
    echo "  brew install --cask tailscale"
    echo ""
    read -p "지금 설치할까요? (y/n): " install_choice
    if [ "$install_choice" = "y" ]; then
        brew install --cask tailscale
        echo ""
        echo "✅ 설치 완료! Tailscale 앱을 실행하고 로그인하세요."
        echo "   (Applications > Tailscale.app)"
        echo ""
        read -p "로그인을 완료했으면 Enter를 누르세요..."
    else
        echo "나중에 설치하세요."
        exit 0
    fi
fi

# 2. Tailscale 상태 확인
echo ""
echo "📡 Tailscale 상태 확인..."

# tailscale CLI 경로 (macOS 앱 내장)
TAILSCALE_CLI="/Applications/Tailscale.app/Contents/MacOS/Tailscale"
if [ ! -f "$TAILSCALE_CLI" ]; then
    TAILSCALE_CLI="tailscale"
fi

TAILSCALE_IP=$($TAILSCALE_CLI ip -4 2>/dev/null)

if [ -z "$TAILSCALE_IP" ]; then
    echo "⚠️  Tailscale이 연결되지 않았습니다."
    echo "   Tailscale 앱을 실행하고 로그인하세요."
    exit 1
fi

echo "✅ Tailscale IP: $TAILSCALE_IP"

# 3. .env에 Tailscale IP 저장
if grep -q "TAILSCALE_IP" "$ENV_FILE" 2>/dev/null; then
    # 기존 값 업데이트
    sed -i '' "s|TAILSCALE_IP=.*|TAILSCALE_IP=$TAILSCALE_IP|" "$ENV_FILE"
else
    echo "" >> "$ENV_FILE"
    echo "# Tailscale VPN IP (외부 네트워크 접속용)" >> "$ENV_FILE"
    echo "TAILSCALE_IP=$TAILSCALE_IP" >> "$ENV_FILE"
fi

echo "✅ .env 파일에 Tailscale IP 저장 완료"

# 4. 접속 정보 표시
PORT=$(grep PORT "$ENV_FILE" | head -1 | cut -d= -f2)
echo ""
echo "════════════════════════════════════════"
echo "📱 모바일 접속 방법:"
echo ""
echo "  같은 Wi-Fi:  http://$(ipconfig getifaddr en0 2>/dev/null):$PORT"
echo "  외부 네트워크: http://$TAILSCALE_IP:$PORT"
echo ""
echo "💡 스마트폰에도 Tailscale 앱(iOS/Android)을 설치하고"
echo "   같은 계정으로 로그인하세요."
echo "════════════════════════════════════════"
echo ""

# 5. Tailscale Funnel (선택)
echo "🌍 Tailscale Funnel을 사용하면 공개 URL을 생성할 수 있습니다."
echo "   (Tailscale 앱 없이도 누구나 접속 가능)"
echo ""
read -p "Tailscale Funnel을 활성화할까요? (y/n): " funnel_choice
if [ "$funnel_choice" = "y" ]; then
    echo "Funnel 실행 중... (Ctrl+C로 종료)"
    $TAILSCALE_CLI funnel $PORT
fi
