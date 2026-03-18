#!/bin/bash
# 안티그래비티 모바일 에이전트 — 원터치 실행 스크립트 (macOS)
# 서버, 브레인 에이전트, 오토 어프로버를 한 번에 실행합니다.
# 선택적으로 디스코드 봇도 함께 실행합니다.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ─── 설정 상수 ───────────────────────────────────────
GITHUB_REPO="caleblee2050/antigravity-mobile-agent"
UPDATE_CHECK_COUNTER=0
UPDATE_CHECK_INTERVAL=240  # 240 × 15초 = 1시간
NOTIFIED_VERSION=""        # 이미 알린 버전 (중복 알림 방지)

# ─── 헬퍼 함수 ───────────────────────────────────────

send_telegram() {
    # curl로 텔레그램 메시지 직접 전송 (Python 불필요)
    local MSG="$1"
    local TG_TOKEN=$(grep TELEGRAM_TOKEN .env 2>/dev/null | cut -d= -f2)
    local TG_CHAT=$(grep TELEGRAM_CHAT_ID .env 2>/dev/null | cut -d= -f2)
    if [ -n "$TG_TOKEN" ] && [ -n "$TG_CHAT" ]; then
        curl -s -X POST "https://api.telegram.org/bot${TG_TOKEN}/sendMessage" \
            -d chat_id="$TG_CHAT" \
            -d text="$MSG" \
            -d parse_mode="HTML" > /dev/null 2>&1
    fi
}

get_local_version() {
    if [ -f "$SCRIPT_DIR/VERSION" ]; then
        cat "$SCRIPT_DIR/VERSION" | tr -d '[:space:]'
    else
        echo "0.0.0"
    fi
}

get_remote_version() {
    # GitHub 릴리즈 → 없으면 태그 체크
    local VER=""
    VER=$(curl -s --connect-timeout 5 "https://api.github.com/repos/${GITHUB_REPO}/releases/latest" 2>/dev/null \
        | grep '"tag_name"' | head -1 | sed 's/.*"tag_name": *"\([^"]*\)".*/\1/' | sed 's/^v//')
    if [ -z "$VER" ]; then
        VER=$(curl -s --connect-timeout 5 "https://api.github.com/repos/${GITHUB_REPO}/tags" 2>/dev/null \
            | grep '"name"' | head -1 | sed 's/.*"name": *"\([^"]*\)".*/\1/' | sed 's/^v//')
    fi
    echo "$VER"
}

check_and_update() {
    local LOCAL_VER=$(get_local_version)
    local REMOTE_VER=$(get_remote_version)

    if [ -z "$REMOTE_VER" ] || [ "$REMOTE_VER" = "$LOCAL_VER" ]; then
        return  # 최신 버전이거나 네트워크 오류
    fi

    # 이미 알린 버전이면 스킵
    if [ "$REMOTE_VER" = "$NOTIFIED_VERSION" ]; then
        return
    fi

    NOTIFIED_VERSION="$REMOTE_VER"

    echo "$(date '+%Y-%m-%d %H:%M:%S') 🆕 업데이트 감지: v${LOCAL_VER} → v${REMOTE_VER}"

    # 텔레그램 인라인 버튼으로 업데이트 선택 알림
    local TG_TOKEN=$(grep TELEGRAM_TOKEN .env 2>/dev/null | cut -d= -f2)
    local TG_CHAT=$(grep TELEGRAM_CHAT_ID .env 2>/dev/null | cut -d= -f2)
    if [ -n "$TG_TOKEN" ] && [ -n "$TG_CHAT" ]; then
        local MSG="🆕 <b>새 업데이트가 있습니다!</b>

현재: v${LOCAL_VER}
최신: v${REMOTE_VER}

업데이트를 적용하시겠습니까?"

        local KEYBOARD='{"inline_keyboard":[[{"text":"✅ 지금 업데이트","callback_data":"do_update"},{"text":"⏰ 나중에","callback_data":"skip_update"}]]}'

        curl -s -X POST "https://api.telegram.org/bot${TG_TOKEN}/sendMessage" \
            -H "Content-Type: application/json" \
            -d "{\"chat_id\":\"${TG_CHAT}\",\"text\":\"${MSG}\",\"parse_mode\":\"HTML\",\"reply_markup\":${KEYBOARD}}" \
            > /dev/null 2>&1
    fi
}

restart_all_children() {
    # Flask 호스트
    python3 antigravity_host.py >> logs/server.log 2>&1 &
    HOST_PID=$!
    echo "$(date '+%Y-%m-%d %H:%M:%S') ✅ Flask 호스트 시작 (PID: $HOST_PID)"

    # 오토 어프로버
    python3 auto_approver.py >> logs/approver_console.log 2>&1 &
    APPROVER_PID=$!
    echo "$(date '+%Y-%m-%d %H:%M:%S') ✅ 오토 어프로버 시작 (PID: $APPROVER_PID)"

    # 텔레그램 봇
    TELEGRAM_PID=""
    TELEGRAM_TOKEN_VAL=$(grep TELEGRAM_TOKEN .env 2>/dev/null | cut -d= -f2)
    if [ -n "$TELEGRAM_TOKEN_VAL" ] && [ "$TELEGRAM_TOKEN_VAL" != "" ]; then
        python3 telegram_bot.py > /dev/null 2>&1 &
        TELEGRAM_PID=$!
        echo "$(date '+%Y-%m-%d %H:%M:%S') ✅ 텔레그램 봇 시작 (PID: $TELEGRAM_PID)"
    fi

    # 브레인 에이전트
    python3 agent_brain.py >> logs/brain.log 2>&1 &
    BRAIN_PID=$!
    echo "$(date '+%Y-%m-%d %H:%M:%S') ✅ 브레인 에이전트 시작 (PID: $BRAIN_PID)"
}

# ─── 트랩: 종료 시 모든 프로세스 정리 ─────────────────
cleanup() {
    echo ""
    echo "🛑 모든 프로세스 종료 중..."
    kill $HOST_PID $APPROVER_PID $TELEGRAM_PID $BRAIN_PID 2>/dev/null
    wait $HOST_PID $APPROVER_PID $TELEGRAM_PID $BRAIN_PID 2>/dev/null
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

# 4. 브레인 에이전트 시작 (백그라운드)
echo "🧠 브레인 에이전트 시작..."
python3 agent_brain.py >> logs/brain.log 2>&1 &
BRAIN_PID=$!
echo "   PID: $BRAIN_PID"

echo ""
echo "🔄 워치독 모드: 프로세스 감시 + 자동 업데이트 체크 시작"
echo ""

# 5. 워치독 루프 — 프로세스 감시 + 업데이트 체크
while true; do
    sleep 15

    # ─── 프로세스 상태 감시 ─────────────────────────────

    # Flask 호스트 감시
    if ! kill -0 $HOST_PID 2>/dev/null; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') ⚠️ Flask 호스트 크래시 감지! 재시작..."
        python3 antigravity_host.py >> logs/server.log 2>&1 &
        HOST_PID=$!
        echo "$(date '+%Y-%m-%d %H:%M:%S') ✅ Flask 호스트 재시작 완료 (PID: $HOST_PID)"
    fi

    # 오토 어프로버 감시
    if ! kill -0 $APPROVER_PID 2>/dev/null; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') ⚠️ 오토 어프로버 크래시 감지! 재시작..."
        python3 auto_approver.py >> logs/approver_console.log 2>&1 &
        APPROVER_PID=$!
        echo "$(date '+%Y-%m-%d %H:%M:%S') ✅ 오토 어프로버 재시작 완료 (PID: $APPROVER_PID)"
    fi

    # 텔레그램 봇 감시
    if [ -n "$TELEGRAM_PID" ] && ! kill -0 $TELEGRAM_PID 2>/dev/null; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') ⚠️ 텔레그램 봇 크래시 감지! 재시작..."
        python3 telegram_bot.py > /dev/null 2>&1 &
        TELEGRAM_PID=$!
        echo "$(date '+%Y-%m-%d %H:%M:%S') ✅ 텔레그램 봇 재시작 완료 (PID: $TELEGRAM_PID)"
    fi

    # 브레인 에이전트 감시
    if ! kill -0 $BRAIN_PID 2>/dev/null; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') ⚠️ 브레인 에이전트 크래시 감지! 재시작..."
        python3 agent_brain.py >> logs/brain.log 2>&1 &
        BRAIN_PID=$!
        echo "$(date '+%Y-%m-%d %H:%M:%S') ✅ 브레인 에이전트 재시작 완료 (PID: $BRAIN_PID)"
    fi

    # ─── 주기적 업데이트 체크 (1시간마다) ─────────────────
    UPDATE_CHECK_COUNTER=$((UPDATE_CHECK_COUNTER + 1))
    if [ $UPDATE_CHECK_COUNTER -ge $UPDATE_CHECK_INTERVAL ]; then
        UPDATE_CHECK_COUNTER=0
        check_and_update
    fi
done
