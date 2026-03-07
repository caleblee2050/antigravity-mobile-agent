#!/bin/bash
# ═══════════════════════════════════════════════════════
# 안티그래비티 모바일 에이전트 — 원커맨드 설치 스크립트
# ═══════════════════════════════════════════════════════
#
# 사용법 (터미널에 붙여넣기):
#   curl -sL https://raw.githubusercontent.com/YOUR_REPO/main/setup.sh | bash
#   또는
#   bash setup.sh
#
# 이 스크립트가 하는 것:
#   1. Python 3 확인
#   2. 프로젝트 폴더 생성
#   3. 가상환경 + 패키지 설치
#   4. 설정 파일 생성 (.env)
#   5. macOS 권한 안내
#   6. 디스코드 봇 설정 (선택)
#   7. 실행

set -e

# ─── 색상 ───
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

echo ""
echo -e "${PURPLE}═══════════════════════════════════════════${NC}"
echo -e "${PURPLE}  🚀 안티그래비티 모바일 에이전트 설치${NC}"
echo -e "${PURPLE}═══════════════════════════════════════════${NC}"
echo ""

# ─── 1. 시스템 확인 ───
echo -e "${BLUE}[1/6]${NC} 시스템 확인..."

# OS 확인
if [[ "$(uname)" != "Darwin" ]]; then
    echo -e "${RED}❌ 이 스크립트는 macOS 전용입니다.${NC}"
    exit 1
fi
echo -e "  ${GREEN}✅${NC} macOS 확인됨"

# Python 확인
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}❌ Python 3이 설치되어 있지 않습니다.${NC}"
    echo "   brew install python3"
    exit 1
fi
PYTHON_VER=$(python3 --version 2>&1 | awk '{print $2}')
echo -e "  ${GREEN}✅${NC} Python $PYTHON_VER"

# ─── 2. 설치 위치 선택 ───
echo ""
echo -e "${BLUE}[2/6]${NC} 설치 위치 선택"
DEFAULT_DIR="$HOME/안티그래비티 모바일에이전트"
read -p "  설치 경로 [$DEFAULT_DIR]: " INSTALL_DIR
INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_DIR}"

if [ -d "$INSTALL_DIR" ] && [ -f "$INSTALL_DIR/antigravity_host.py" ]; then
    echo -e "  ${YELLOW}⚠️  이미 설치되어 있습니다. 업데이트합니다.${NC}"
fi

mkdir -p "$INSTALL_DIR"
echo -e "  ${GREEN}✅${NC} $INSTALL_DIR"

# ─── 3. 파일 복사 / 생성 ───
echo ""
echo -e "${BLUE}[3/6]${NC} 프로젝트 파일 생성..."

# 이 스크립트가 프로젝트 폴더 안에서 실행된 경우
SCRIPT_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"
if [ -f "$SCRIPT_DIR/antigravity_host.py" ] && [ "$SCRIPT_DIR" != "$INSTALL_DIR" ]; then
    echo "  파일 복사 중..."
    cp "$SCRIPT_DIR"/*.py "$INSTALL_DIR/" 2>/dev/null || true
    cp "$SCRIPT_DIR"/*.sh "$INSTALL_DIR/" 2>/dev/null || true
    cp "$SCRIPT_DIR"/*.txt "$INSTALL_DIR/" 2>/dev/null || true
    cp -r "$SCRIPT_DIR/templates" "$INSTALL_DIR/" 2>/dev/null || true
    cp -r "$SCRIPT_DIR/images" "$INSTALL_DIR/" 2>/dev/null || true
    echo -e "  ${GREEN}✅${NC} 파일 복사 완료"
elif [ ! -f "$INSTALL_DIR/antigravity_host.py" ]; then
    echo -e "${RED}❌ 프로젝트 파일을 찾을 수 없습니다.${NC}"
    echo "   이 스크립트를 프로젝트 폴더 안에서 실행하거나,"
    echo "   먼저 프로젝트 파일을 $INSTALL_DIR 에 복사하세요."
    exit 1
fi

# 디렉토리 생성
mkdir -p "$INSTALL_DIR/images"
mkdir -p "$INSTALL_DIR/logs"

# 실행 권한
chmod +x "$INSTALL_DIR"/*.sh 2>/dev/null || true

echo -e "  ${GREEN}✅${NC} 프로젝트 구조 준비 완료"

# ─── 4. 가상환경 + 패키지 설치 ───
echo ""
echo -e "${BLUE}[4/6]${NC} Python 패키지 설치..."

cd "$INSTALL_DIR"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -q -r requirements.txt 2>&1 | tail -1
echo -e "  ${GREEN}✅${NC} 패키지 설치 완료"

# ─── 5. 설정 (.env) ───
echo ""
echo -e "${BLUE}[5/6]${NC} 설정..."

if [ ! -f ".env" ]; then
    # 비밀번호 생성
    DEFAULT_PW="antigravity$(date +%s | shasum | head -c 6)"

    read -p "  서버 비밀번호 [$DEFAULT_PW]: " AUTH_PW
    AUTH_PW="${AUTH_PW:-$DEFAULT_PW}"

    read -p "  서버 포트 [9150]: " PORT
    PORT="${PORT:-9150}"

    cat > .env << EOF
# 안티그래비티 모바일 에이전트 설정
PORT=$PORT
AUTH_PASSWORD=$AUTH_PW
HOST_IP=0.0.0.0

# 디스코드 봇 (선택)
# DISCORD_TOKEN=여기에_봇_토큰
# DISCORD_CHANNEL_ID=여기에_채널_ID
EOF
    echo -e "  ${GREEN}✅${NC} .env 생성 완료 (비밀번호: $AUTH_PW)"
else
    echo -e "  ${YELLOW}⚠️${NC} 기존 .env 유지"
fi

# ─── 6. 디스코드 봇 (선택) ───
echo ""
echo -e "${BLUE}[6/6]${NC} 디스코드 봇 설정 (선택)"
read -p "  디스코드 봇을 설정할까요? (y/n) [n]: " SETUP_DISCORD
if [ "$SETUP_DISCORD" = "y" ]; then
    echo ""
    echo "  📋 Discord Developer Portal에서 봇을 만드세요:"
    echo "     https://discord.com/developers/applications"
    echo ""
    read -p "  봇 토큰: " DISCORD_TOKEN
    read -p "  채널 ID: " DISCORD_CHANNEL

    if [ -n "$DISCORD_TOKEN" ] && [ -n "$DISCORD_CHANNEL" ]; then
        sed -i '' "s|# DISCORD_TOKEN=.*|DISCORD_TOKEN=$DISCORD_TOKEN|" .env
        sed -i '' "s|# DISCORD_CHANNEL_ID=.*|DISCORD_CHANNEL_ID=$DISCORD_CHANNEL|" .env
        echo -e "  ${GREEN}✅${NC} 디스코드 봇 설정 완료"
    fi
else
    echo -e "  ${YELLOW}⏭️${NC}  건너뜀 (나중에 .env 수정 가능)"
fi

# ─── 완료 ───
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || echo 'localhost')
PORT=$(grep PORT .env | head -1 | cut -d= -f2)
AUTH_PW=$(grep AUTH_PASSWORD .env | cut -d= -f2)

echo ""
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✅ 설치 완료!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo ""
echo -e "  📁 설치 경로: ${PURPLE}$INSTALL_DIR${NC}"
echo -e "  📱 대시보드:  ${BLUE}http://$LOCAL_IP:$PORT${NC}"
echo -e "  🔑 비밀번호:  ${YELLOW}$AUTH_PW${NC}"
echo ""
echo -e "  ${YELLOW}⚠️  macOS 권한 필요:${NC}"
echo "     시스템 설정 > 개인정보 보호 > 접근성 → 터미널 허용"
echo "     시스템 설정 > 개인정보 보호 > 화면 녹음 → 터미널 허용"
echo ""
echo -e "  실행 명령어:"
echo -e "  ${BLUE}$INSTALL_DIR/run.sh${NC}"
echo ""

# 바로 실행할지 물어보기
read -p "  지금 바로 실행할까요? (y/n) [y]: " RUN_NOW
if [ "$RUN_NOW" != "n" ]; then
    exec "$INSTALL_DIR/run.sh"
fi
