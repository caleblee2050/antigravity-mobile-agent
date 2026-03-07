#!/bin/bash
# 안티그래비티 모바일 에이전트 — launchd 서비스 설치 스크립트
# 맥 부팅 시 자동으로 서버, 브레인, 오토어프로버를 실행합니다.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_NAME="com.a4k.antigravity-mobile"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$PLIST_DIR/$PLIST_NAME.plist"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python3"
LOG_DIR="$SCRIPT_DIR/logs"

echo "🚀 안티그래비티 모바일 에이전트 — 서비스 설치"
echo "═══════════════════════════════════════════"
echo ""

# 가상환경 확인
if [ ! -f "$VENV_PYTHON" ]; then
    echo "❌ 가상환경이 없습니다. 먼저 run.sh를 실행하여 설정하세요."
    exit 1
fi

# 로그 디렉토리 생성
mkdir -p "$LOG_DIR"

# 기존 서비스 해제
if launchctl list 2>/dev/null | grep -q "$PLIST_NAME"; then
    echo "⏳ 기존 서비스 해제 중..."
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
fi

# plist 파일 생성
cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$PLIST_NAME</string>

    <key>ProgramArguments</key>
    <array>
        <string>$SCRIPT_DIR/run.sh</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$SCRIPT_DIR</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>$LOG_DIR/launchd_stdout.log</string>

    <key>StandardErrorPath</key>
    <string>$LOG_DIR/launchd_stderr.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
    </dict>

    <key>ThrottleInterval</key>
    <integer>10</integer>
</dict>
</plist>
EOF

echo "✅ plist 파일 생성 완료: $PLIST_PATH"

# 서비스 등록
launchctl load "$PLIST_PATH"
echo "✅ 서비스 등록 완료!"
echo ""

# 상태 확인
if launchctl list 2>/dev/null | grep -q "$PLIST_NAME"; then
    echo "🟢 서비스 상태: 실행 중"
else
    echo "🟡 서비스 상태: 등록됨 (재부팅 후 자동 시작)"
fi

echo ""
echo "📋 유용한 명령어:"
echo "  상태 확인:  launchctl list | grep antigravity"
echo "  로그 확인:  tail -f $LOG_DIR/launchd_stdout.log"
echo "  서비스 중지: launchctl unload $PLIST_PATH"
echo "  서비스 시작: launchctl load $PLIST_PATH"
echo "  제거:       ./uninstall_service.sh"
