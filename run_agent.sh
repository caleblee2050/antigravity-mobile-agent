#!/bin/bash

# Antigravity Mobile Agent 런처 스크립트 (LaunchAgent용)
# 내부적으로 기존 다중 프로세스 실행기인 run.sh를 호출하여
# 호스트 API, 텔레그램 봇, 오토 어프로버, 브레인 에이전트를 모두 통합 실행합니다.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

# 기본 PATH 추가 (Homebrew, Node 등)
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

export PYTHONUNBUFFERED=1

# 로그 폴더가 없으면 생성
mkdir -p "$SCRIPT_DIR/logs"

# 런처 시작 로그 기록
echo "[$(date '+%Y-%m-%d %H:%M:%S')] LaunchAgent가 전체 시스템 런처(run.sh)를 백그라운드 구동합니다." >> "$SCRIPT_DIR/logs/launcher.log"

# run.sh 로 권한 위임 및 실행 (run.sh 내부에 트랩(SIGTERM 등) 및 프로세스 관리가 있음)
exec ./run.sh
