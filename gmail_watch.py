#!/usr/bin/env python3
"""
Gmail Education Trainer 메일 모니터 — 백그라운드 자동 감시 스크립트
새로운 Google Certified Trainer 관련 메일(특히 합격/불합격)이 도착하면
즉시 텔레그램으로 알림을 보냅니다.

launchd로 매 10분마다 실행됩니다.
"""

import json
import os
import subprocess
import base64
import re
from pathlib import Path
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# ─── 설정 ───
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# gws CLI 환경변수
GWS_ENV = {
    **os.environ,
    "GOOGLE_WORKSPACE_CLI_CLIENT_ID": os.getenv("GWS_CLIENT_ID", ""),
    "GOOGLE_WORKSPACE_CLI_CLIENT_SECRET": os.getenv("GWS_CLIENT_SECRET", ""),
}

# 마지막으로 확인한 메일 ID를 저장하는 파일
STATE_FILE = Path.home() / ".config" / "gmail-watch" / "last_seen.json"

# 검색 쿼리: 트레이너 합격/지원 관련 키워드
GMAIL_QUERY = (
    "from:(gfe-applications.com OR google.com OR googleforeducation.com) "
    "(certified trainer OR education trainer OR application OR 합격 OR accepted OR congratulations OR approved OR status)"
)


def load_state() -> dict:
    """마지막 확인 상태 로드."""
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text())
    except Exception:
        pass
    return {"last_seen_ids": [], "last_check": ""}


def save_state(state: dict):
    """상태 저장."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def send_telegram(message: str):
    """텔레그램으로 메시지 전송."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }, timeout=10)
        if resp.status_code == 200:
            print(f"✅ 텔레그램 전송 완료")
        else:
            print(f"❌ 텔레그램 전송 실패: {resp.text}")
    except Exception as e:
        print(f"❌ 텔레그램 오류: {e}")


def gws_command(resource_method: str, params: dict) -> dict | None:
    """gws CLI를 실행하여 JSON 결과 반환. resource_method 예: 'gmail users messages list'"""
    cmd = ["gws"] + resource_method.split() + ["--params", json.dumps(params)]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, env=GWS_ENV
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            print(f"❌ gws 오류: {result.stderr or result.stdout}")
            return None
    except Exception as e:
        print(f"❌ gws 실행 오류: {e}")
        return None


def get_message_detail(msg_id: str) -> dict | None:
    """메일 ID로 상세 내용 가져오기."""
    return gws_command("gmail users messages get", {
        "userId": "me",
        "id": msg_id,
        "format": "full"
    })


def extract_text_body(payload: dict) -> str:
    """메일 본문에서 텍스트 추출."""
    body = ""
    if "body" in payload and payload["body"].get("data"):
        body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", "replace")
    elif "parts" in payload:
        for part in payload["parts"]:
            mime = part.get("mimeType", "")
            if mime == "text/plain" and part.get("body", {}).get("data"):
                body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", "replace")
                break
            elif mime.startswith("multipart/"):
                for subpart in part.get("parts", []):
                    if subpart.get("mimeType") == "text/plain" and subpart.get("body", {}).get("data"):
                        body = base64.urlsafe_b64decode(subpart["body"]["data"]).decode("utf-8", "replace")
                        break
                if body:
                    break
    return body.strip()


def is_acceptance_email(subject: str, body: str) -> bool:
    """합격/결과 관련 메일인지 판별."""
    keywords = [
        "accepted", "approved", "congratulations", "certified",
        "passed", "welcome", "합격", "승인", "통과",
        "status update", "application update", "decision",
        "result", "outcome"
    ]
    text = (subject + " " + body).lower()
    return any(kw in text for kw in keywords)


def check_emails():
    """새 메일 확인 및 알림."""
    state = load_state()
    seen = set(state.get("last_seen_ids", []))

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 메일 확인 중...")

    # Gmail에서 트레이너 관련 메일 검색
    data = gws_command("gmail users messages list", {
        "userId": "me",
        "q": GMAIL_QUERY,
        "maxResults": 10,
    })

    if not data or "messages" not in data:
        print("  검색 결과 없음.")
        state["last_check"] = datetime.now().isoformat()
        save_state(state)
        return

    messages = data["messages"]
    new_messages = [m for m in messages if m["id"] not in seen]

    if not new_messages:
        print(f"  새 메일 없음 (총 {len(messages)}건 중 모두 확인 완료)")
        state["last_check"] = datetime.now().isoformat()
        save_state(state)
        return

    print(f"  🆕 새 메일 {len(new_messages)}건 발견!")

    for msg in new_messages:
        detail = get_message_detail(msg["id"])
        if not detail:
            continue

        headers = {
            h["name"]: h["value"]
            for h in detail.get("payload", {}).get("headers", [])
        }
        subject = headers.get("Subject", "(제목 없음)")
        sender = headers.get("From", "(알 수 없음)")
        date = headers.get("Date", "")
        body = extract_text_body(detail.get("payload", {}))

        # 합격/결과 관련 메일 여부 확인
        is_important = is_acceptance_email(subject, body)
        priority = "🚨 *중요!*" if is_important else "📬"

        telegram_msg = (
            f"{priority} *Google Education Trainer 메일 도착!*\n\n"
            f"📧 *제목:* {subject}\n"
            f"👤 *보낸이:* {sender}\n"
            f"📅 *날짜:* {date}\n\n"
            f"📝 *내용:*\n{body[:500]}"
        )

        send_telegram(telegram_msg)
        seen.add(msg["id"])

    # 최근 10개 ID만 유지
    state["last_seen_ids"] = list(seen)[-50:]
    state["last_check"] = datetime.now().isoformat()
    save_state(state)
    print(f"  완료. 상태 저장됨.")


if __name__ == "__main__":
    check_emails()
