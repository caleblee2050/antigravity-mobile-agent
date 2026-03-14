#!/bin/bash
# 안티그래비티 모바일 에이전트 — 원터치 실행 스크립트 (macOS)
# 서버, 브레인 에이전트, 오토 어프로버를 한 번에 실행합니다.
# 선택적으로 디스코드 봇도 함께 실행합니다.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 트랩: 종료 시 모든 프로세스 정리
cleanup() {
    echo ""
    echo "🛑 모든 프로세스 종료 중..."
    kill $HOST_PID $APPROVER_PID $TELEGRAM_PID 2>/dev/null
    wait $HOST_PID $APPROVER_PID $TELEGRAM_PID 2>/dev/null
    echo "✅ 종료 완료"
    exit 0
}
trap cleanup SIGINT SIGTERM

echo "🚀 안티그래비티 모바일 에이전트 시작!"
echo "════════════════════════════════════════"
echo ""

# 로그 디렉토리 생성
mkdir -p logs

# Python 가상환경 확인
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "✅ 가상환경 활성화됨"
else
    echo "⚠️  가상환경이 없습니다. 생성합니다..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    echo "✅ 가상환경 생성 및 패키지 설치 완료"
fi

echo ""

# mailbox.json 초기화
cat > mailbox.json << 'EOF'
{
  "inbound": {"text": "", "timestamp": ""},
  "outbound": {"text": "", "timestamp": ""},
  "approval_request": {"pending": false, "type": "", "timestamp": ""},
  "screenshot": {"data": "", "timestamp": ""}
}
EOF

# 네트워크 정보
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || echo 'localhost')
TAILSCALE_CLI="/Applications/Tailscale.app/Contents/MacOS/Tailscale"
TAILSCALE_IP=""
if [ -f "$TAILSCALE_CLI" ]; then
    TAILSCALE_IP=$($TAILSCALE_CLI ip -4 2>/dev/null)
elif command -v tailscale &>/dev/null; then
    TAILSCALE_IP=$(tailscale ip -4 2>/dev/null)
fi

PORT=$(grep PORT .env 2>/dev/null | head -1 | cut -d= -f2 || echo "9150")
AUTH_PW=$(grep AUTH_PASSWORD .env 2>/dev/null | cut -d= -f2 || echo "antigravity2026")

# 1. Flask 서버 시작 (백그라운드)
echo "📡 통신 허브 서버 시작..."
python3 antigravity_host.py >> logs/server.log 2>&1 &
HOST_PID=$!
echo "   PID: $HOST_PID"
sleep 2

# 2. 오토 어프로버 시작 (백그라운드)
echo "👁️  오토 어프로버 시작..."
python3 auto_approver.py >> logs/approver_console.log 2>&1 &
APPROVER_PID=$!
echo "   PID: $APPROVER_PID"

# 3. 텔레그램 봇 (환경변수 있을 때만)
TELEGRAM_PID=""
TELEGRAM_TOKEN_VAL=$(grep TELEGRAM_TOKEN .env 2>/dev/null | cut -d= -f2)
if [ -n "$TELEGRAM_TOKEN_VAL" ] && [ "$TELEGRAM_TOKEN_VAL" != "" ]; then
    echo "📱 텔레그램 봇 시작..."
    python3 telegram_bot.py > /dev/null 2>&1 &
    TELEGRAM_PID=$!
    echo "   PID: $TELEGRAM_PID"
fi

# 접속 정보 표시
echo ""
echo "════════════════════════════════════════"
echo "📱 모바일 대시보드:"
echo "   🏠 로컬: http://${LOCAL_IP}:${PORT}"
if [ -n "$TAILSCALE_IP" ]; then
    echo "   🌐 Tailscale: http://${TAILSCALE_IP}:${PORT}"
fi
echo ""
echo "🔑 비밀번호: ${AUTH_PW}"
echo "════════════════════════════════════════"
echo ""
echo "📋 로그 확인: tail -f logs/server.log"
echo "종료하려면 Ctrl+C를 누르세요."
echo ""

# 4. 브레인 에이전트 시작 (포그라운드 — Ctrl+C로 전체 종료)
python3 agent_brain.py
