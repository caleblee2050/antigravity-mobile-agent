#!/usr/bin/env python3
"""
안티그래비티 모바일 에이전트 — 텔레그램 알림 모듈
AI 응답, 작업 완료, 승인 요청 등을 텔레그램 푸시 알림으로 보냅니다.

설정:
  .env에 다음 값을 추가하세요:
    TELEGRAM_TOKEN=<BotFather에서 발급받은 토큰>
    TELEGRAM_CHAT_ID=<본인의 chat_id>
"""

import os
import logging
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

logger = logging.getLogger("telegram_notifier")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# 텔레그램 메시지 최대 길이
MAX_MESSAGE_LENGTH = 4096


def is_configured() -> bool:
    """텔레그램 설정이 완료되었는지 확인"""
    return bool(TELEGRAM_TOKEN) and bool(TELEGRAM_CHAT_ID)


def send_message(text: str, parse_mode: str = "HTML") -> bool:
    """텔레그램 메시지 전송

    Args:
        text: 전송할 메시지 (HTML 또는 일반 텍스트)
        parse_mode: "HTML" 또는 "Markdown" 또는 None

    Returns:
        전송 성공 여부
    """
    if not is_configured():
        logger.debug("텔레그램 미설정 — 알림 건너뜀")
        return False

    try:
        # 메시지가 너무 길면 분할 전송
        if len(text) > MAX_MESSAGE_LENGTH:
            chunks = _split_message(text)
            success = True
            for chunk in chunks:
                if not _send_single(chunk, parse_mode):
                    success = False
            return success
        else:
            return _send_single(text, parse_mode)
    except Exception as e:
        logger.error(f"텔레그램 알림 전송 실패: {e}")
        return False


def _send_single(text: str, parse_mode: str = "HTML") -> bool:
    """단일 메시지 전송"""
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode

    try:
        resp = requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json=payload,
            timeout=10,
        )
        if resp.status_code == 200:
            return True
        else:
            # parse_mode 문제일 수 있으므로 plain text로 재시도
            if parse_mode:
                logger.warning(f"HTML 파싱 실패, 일반 텍스트로 재시도: {resp.text}")
                payload.pop("parse_mode", None)
                # HTML 태그 제거
                import re
                payload["text"] = re.sub(r"<[^>]+>", "", text)
                resp2 = requests.post(
                    f"{TELEGRAM_API}/sendMessage",
                    json=payload,
                    timeout=10,
                )
                return resp2.status_code == 200
            return False
    except requests.exceptions.RequestException as e:
        logger.error(f"텔레그램 API 요청 실패: {e}")
        return False


def _split_message(text: str) -> list:
    """긴 메시지를 분할"""
    chunks = []
    while text:
        if len(text) <= MAX_MESSAGE_LENGTH:
            chunks.append(text)
            break
        # 줄바꿈 기준으로 자르기
        split_pos = text.rfind("\n", 0, MAX_MESSAGE_LENGTH)
        if split_pos == -1:
            split_pos = MAX_MESSAGE_LENGTH
        chunks.append(text[:split_pos])
        text = text[split_pos:].lstrip("\n")
    return chunks


# ─── 포맷팅 헬퍼 ──────────────────────────────────────

def notify_ai_reply(reply_text: str) -> bool:
    """AI 응답 알림"""
    # 너무 긴 응답은 요약
    if len(reply_text) > 3000:
        preview = reply_text[:3000] + "\n\n⋯ (이하 생략)"
    else:
        preview = reply_text

    msg = f"🧠 <b>AI 응답</b>\n\n{_escape_html(preview)}"
    return send_message(msg)


def notify_message_received(text: str) -> bool:
    """모바일 메시지 접수 확인 알림"""
    msg = f"📨 <b>요청 접수</b>\n\n{_escape_html(text)}\n\n⏳ 처리 중..."
    return send_message(msg)


def notify_task_complete(task: str, result: str) -> bool:
    """작업 완료 알림"""
    msg = f"✅ <b>처리 완료</b>\n\n<b>요청:</b> {_escape_html(task)}\n<b>결과:</b> {_escape_html(result)}"
    return send_message(msg)


def notify_approval_needed(details: str) -> bool:
    """승인 요청 알림"""
    msg = f"⚠️ <b>승인 필요</b>\n\n{_escape_html(details)}\n\n🔐 대시보드에서 승인/거부해주세요."
    return send_message(msg)


def notify_error(error: str) -> bool:
    """시스템 오류 알림"""
    msg = f"🔴 <b>오류 발생</b>\n\n{_escape_html(error)}"
    return send_message(msg)


def notify_system_start() -> bool:
    """시스템 시작 알림"""
    msg = "🚀 <b>안티그래비티 모바일 에이전트</b> 시작됨!\n\n📱 텔레그램 알림이 활성화되었습니다."
    return send_message(msg)


def notify_custom(title: str, body: str) -> bool:
    """범용 알림"""
    msg = f"📬 <b>{_escape_html(title)}</b>\n\n{_escape_html(body)}"
    return send_message(msg)


def _escape_html(text: str) -> str:
    """HTML 특수문자 이스케이프 (텔레그램 HTML 모드용)"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ─── CLI 테스트 ────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if not is_configured():
        print("❌ .env에 TELEGRAM_TOKEN과 TELEGRAM_CHAT_ID를 설정하세요.")
        print("")
        print("1. 텔레그램에서 @BotFather → /newbot → 토큰 복사")
        print("2. 생성된 봇에게 아무 메시지 전송")
        print(f"3. https://api.telegram.org/bot<TOKEN>/getUpdates 에서 chat_id 확인")
        sys.exit(1)

    if len(sys.argv) >= 2:
        test_msg = " ".join(sys.argv[1:])
        if send_message(f"🧪 테스트 알림: {test_msg}"):
            print("✅ 텔레그램 알림 전송 성공!")
        else:
            print("❌ 텔레그램 알림 전송 실패")
    else:
        if notify_system_start():
            print("✅ 시스템 시작 알림 전송 성공!")
        else:
            print("❌ 알림 전송 실패")
