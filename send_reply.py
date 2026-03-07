#!/usr/bin/env python3
"""
안티그래비티 모바일 에이전트 — 답장 도구
안티그래비티가 이 스크립트를 실행하여 스마트폰으로 답장을 보냅니다.

사용법:
  1. CLI:    python send_reply.py "답장 내용"
  2. stdin:  echo "답장 내용" | python send_reply.py
  3. 모듈:   from send_reply import send_reply; send_reply("텍스트")
"""

import sys
import os
import requests
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

HOST_URL = f"http://localhost:{os.getenv('PORT', '9150')}"


def send_reply(text: str) -> bool:
    """스마트폰으로 답장 전송

    Args:
        text: 전송할 메시지 텍스트

    Returns:
        전송 성공 여부
    """
    try:
        response = requests.post(
            f"{HOST_URL}/api/reply",
            json={"text": text},
            timeout=5,
        )
        if response.status_code == 200:
            print(f"✅ 답장 전송 완료: {text[:80]}...")
            return True
        else:
            print(f"❌ 답장 전송 실패: {response.text}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ 서버에 연결할 수 없습니다. antigravity_host.py가 실행 중인지 확인하세요.")
        return False
    except Exception as e:
        print(f"❌ 오류: {e}")
        return False


if __name__ == "__main__":
    # 인자로 받은 경우
    if len(sys.argv) >= 2:
        message = " ".join(sys.argv[1:])
        send_reply(message)
    # stdin으로 받은 경우
    elif not sys.stdin.isatty():
        message = sys.stdin.read().strip()
        if message:
            send_reply(message)
        else:
            print("❌ 빈 입력입니다.")
    else:
        print("사용법:")
        print("  python send_reply.py '답장 내용'")
        print("  echo '답장 내용' | python send_reply.py")
        sys.exit(1)
