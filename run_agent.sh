#!/bin/bash

# Antigravity Mobile Agent 런처 스크립트 (LaunchAgent용)
# 시스템 환경변수 및 가상환경 세팅을 강제로 적용하여 백그라운드 구동 안정성을 확보합니다.

# 현재 스크립트의 절대 경로 찾기
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

# 기본 PATH 추가 (Homebrew, Node 등)
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

# 로그 폴더가 없으면 생성
mkdir -p "$SCRIPT_DIR/logs"

# 런처 시작 로그 기록
echo "[$(date '+%Y-%m-%d %H:%M:%S')] LaunchAgent가 런처를 실행했습니다." >> "$SCRIPT_DIR/logs/launcher.log"

# 가상환경 활성화 (필수)
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
else
    echo "[!] 가상환경(venv)을 찾을 수 없습니다!" >> "$SCRIPT_DIR/logs/launcher.log"
    exit 1
fi

# 필요 모듈 검증
if ! python -c "import pyautogui" 2>/dev/null; then
    echo "[!] pyautogui 등 필수 모듈 누락. 의존성 확인 요망." >> "$SCRIPT_DIR/logs/launcher.log"
fi

# 메인 에이전트 브레인 실행
# stderr 2>&1 리다이렉트는 LaunchAgent 자체 설정(StandardErrorPath)에서 처리하므로
# 여기서는 표준 출력만 유지합니다. (내부 로깅 라이브러리가 logs 폴더를 별도로 관리하긴 함)
exec python agent_brain.py
