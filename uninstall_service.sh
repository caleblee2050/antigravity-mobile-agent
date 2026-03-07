#!/bin/bash
# 안티그래비티 모바일 에이전트 — launchd 서비스 제거 스크립트

PLIST_NAME="com.a4k.antigravity-mobile"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

echo "🛑 안티그래비티 모바일 에이전트 — 서비스 제거"
echo "═══════════════════════════════════════════"
echo ""

if [ -f "$PLIST_PATH" ]; then
    # 서비스 해제
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    echo "✅ 서비스 해제 완료"

    # plist 파일 삭제
    rm -f "$PLIST_PATH"
    echo "✅ plist 파일 삭제 완료: $PLIST_PATH"
else
    echo "ℹ️  설치된 서비스가 없습니다."
fi

echo ""
echo "✅ 제거 완료!"
