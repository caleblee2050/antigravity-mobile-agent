#!/usr/bin/env python3
"""
안티그래비티 모바일 에이전트 — 통신 허브 (Host 서버)
Flask 기반 로컬 서버. 스마트폰 ↔ PC 간 메시지를 중계합니다.
"""

import json
import os
import base64
import subprocess
import threading
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
import telegram_notifier

load_dotenv()

app = Flask(__name__)
CORS(app)

PORT = int(os.getenv("PORT", 9150))
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "antigravity2026")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAILBOX_PATH = os.path.join(BASE_DIR, "mailbox.json")
HISTORY_PATH = os.path.join(BASE_DIR, "chat_history.json")

# 컴포넌트 상태 추적
component_status = {
    "server": {"status": "running", "since": datetime.now().isoformat()},
    "brain": {"status": "unknown", "since": ""},
    "approver": {"status": "unknown", "since": ""},
    "discord": {"status": "unknown", "since": ""},
}


def read_mailbox():
    """mailbox.json 읽기"""
    try:
        with open(MAILBOX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "inbound": {"text": "", "timestamp": ""},
            "outbound": {"text": "", "timestamp": ""},
            "approval_request": {"pending": False, "type": "", "timestamp": ""},
            "screenshot": {"data": "", "timestamp": ""},
        }


def write_mailbox(data):
    """mailbox.json 쓰기"""
    with open(MAILBOX_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_history():
    """대화 히스토리 읽기"""
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def write_history(history):
    """대화 히스토리 저장 (최대 200개)"""
    history = history[-200:]
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def add_to_history(sender: str, text: str, msg_type: str):
    """히스토리에 메시지 추가"""
    history = read_history()
    history.append({
        "sender": sender,
        "text": text,
        "type": msg_type,
        "timestamp": datetime.now().isoformat(),
    })
    write_history(history)


def auth_check():
    """비밀번호 인증"""
    password = (
        request.args.get("password")
        or (request.json.get("password", "") if request.is_json else None)
        or request.args.get("password", "")
    )
    return password == AUTH_PASSWORD


# ─── API 엔드포인트 ───────────────────────────────────

@app.route("/")
def index():
    """모바일 대시보드 (HTML)"""
    return render_template("dashboard.html", port=PORT)


@app.route("/api/msg", methods=["POST"])
def receive_message():
    """📱→🖥️ 스마트폰에서 메시지 수신"""
    if not auth_check():
        return jsonify({"error": "인증 실패"}), 401

    data = request.json
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "빈 메시지"}), 400

    mailbox = read_mailbox()
    mailbox["inbound"] = {
        "text": text,
        "timestamp": datetime.now().isoformat(),
    }
    write_mailbox(mailbox)

    # 히스토리에 기록
    sender = data.get("sender", "모바일")
    add_to_history(sender, text, "sent")

    return jsonify({"status": "ok", "message": "메시지 수신 완료"})


@app.route("/api/sync", methods=["GET"])
def sync_status():
    """📱←🖥️ 스마트폰이 현재 상태 확인 (폴링)"""
    mailbox = read_mailbox()
    return jsonify({
        "outbound": mailbox.get("outbound", {}),
        "approval_request": mailbox.get("approval_request", {}),
        "screenshot": {
            "timestamp": mailbox.get("screenshot", {}).get("timestamp", ""),
            "has_data": bool(mailbox.get("screenshot", {}).get("data", "")),
        },
    })


@app.route("/api/screenshot", methods=["GET"])
def get_screenshot():
    """📱←🖥️ 스크린샷 데이터 반환"""
    mailbox = read_mailbox()
    screenshot_data = mailbox.get("screenshot", {}).get("data", "")
    return jsonify({"data": screenshot_data})


@app.route("/api/agent/poll", methods=["GET"])
def agent_poll():
    """🤖←🖥️ 브레인 에이전트가 새 메시지 확인"""
    mailbox = read_mailbox()
    inbound = mailbox.get("inbound", {})

    if inbound.get("text"):
        text = inbound["text"]
        mailbox["inbound"] = {"text": "", "timestamp": ""}
        write_mailbox(mailbox)
        return jsonify({"has_message": True, "text": text})

    return jsonify({"has_message": False})


@app.route("/api/reply", methods=["POST"])
def post_reply():
    """🤖→🖥️ AI 응답을 mailbox에 저장"""
    data = request.json
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "빈 응답"}), 400

    mailbox = read_mailbox()
    mailbox["outbound"] = {
        "text": text,
        "timestamp": datetime.now().isoformat(),
    }
    write_mailbox(mailbox)

    # 히스토리에 기록
    add_to_history("AI", text, "received")

    return jsonify({"status": "ok"})


@app.route("/api/notify", methods=["POST"])
def send_notification():
    """📬 범용 텔레그램 알림 전송 (Antigravity가 직접 결과를 보낼 때)"""
    data = request.json
    title = data.get("title", "알림")
    body = data.get("body", "").strip()
    notify_type = data.get("type", "custom")

    if not body:
        return jsonify({"error": "빈 내용"}), 400

    # 타입별 알림 함수 선택
    notifier_map = {
        "task_complete": lambda: telegram_notifier.notify_task_complete(title, body),
        "error": lambda: telegram_notifier.notify_error(body),
        "approval": lambda: telegram_notifier.notify_approval_needed(body),
        "custom": lambda: telegram_notifier.notify_custom(title, body),
    }

    notify_fn = notifier_map.get(notify_type, notifier_map["custom"])
    threading.Thread(target=notify_fn, daemon=True).start()

    # 히스토리에도 기록
    add_to_history("시스템", f"[{title}] {body}", "notification")

    return jsonify({"status": "ok"})


@app.route("/api/screenshot/update", methods=["POST"])
def update_screenshot():
    """🤖→🖥️ 스크린샷 업데이트"""
    data = request.json
    screenshot_data = data.get("data", "")

    mailbox = read_mailbox()
    mailbox["screenshot"] = {
        "data": screenshot_data,
        "timestamp": datetime.now().isoformat(),
    }
    write_mailbox(mailbox)

    return jsonify({"status": "ok"})


@app.route("/api/approval/respond", methods=["POST"])
def approval_respond():
    """📱→🖥️ 승인 요청에 대한 응답"""
    if not auth_check():
        return jsonify({"error": "인증 실패"}), 401

    data = request.json
    approved = data.get("approved", False)

    mailbox = read_mailbox()
    mailbox["approval_request"] = {
        "pending": False,
        "type": "approved" if approved else "rejected",
        "timestamp": datetime.now().isoformat(),
    }
    write_mailbox(mailbox)

    return jsonify({"status": "ok"})


@app.route("/api/history", methods=["GET"])
def get_history():
    """📱←🖥️ 대화 히스토리 반환"""
    limit = request.args.get("limit", 50, type=int)
    history = read_history()
    return jsonify({"messages": history[-limit:]})


@app.route("/api/history/clear", methods=["POST"])
def clear_history():
    """대화 히스토리 초기화"""
    if not auth_check():
        return jsonify({"error": "인증 실패"}), 401
    write_history([])
    return jsonify({"status": "ok"})


@app.route("/api/status", methods=["GET"])
def get_status():
    """📊 시스템 상태 반환"""
    tailscale_ip = os.getenv("TAILSCALE_IP", "")
    return jsonify({
        "components": component_status,
        "tailscale_ip": tailscale_ip,
        "local_ip": _get_local_ip(),
        "port": PORT,
    })


@app.route("/api/component/status", methods=["POST"])
def update_component_status():
    """컴포넌트 상태 업데이트"""
    data = request.json
    name = data.get("component", "")
    status = data.get("status", "unknown")

    if name in component_status:
        component_status[name] = {
            "status": status,
            "since": datetime.now().isoformat(),
        }

    return jsonify({"status": "ok"})


@app.route("/api/commands", methods=["GET"])
def get_quick_commands():
    """빠른 명령어 목록"""
    commands = [
        {"label": "📂 프로젝트 구조", "text": "현재 프로젝트의 폴더 구조를 보여줘"},
        {"label": "🔍 코드 리뷰", "text": "마지막 커밋의 코드를 리뷰해줘"},
        {"label": "🐛 디버그", "text": "현재 에러를 분석하고 수정해줘"},
        {"label": "📝 TODO", "text": "현재 프로젝트의 TODO 리스트를 정리해줘"},
        {"label": "🧪 테스트", "text": "테스트를 실행하고 결과를 알려줘"},
        {"label": "📊 상태", "text": "프로젝트의 현재 상태를 요약해줘"},
        {"label": "💬 카톡 보내기", "text": "나에게 카카오톡 메시지를 보내줘"},
    ]
    return jsonify({"commands": commands})


# ─── 카카오톡 API 엔드포인트 ──────────────────────────────

def _get_kakao_api():
    """kakao_api 모듈 lazy import (미설정 시 graceful 처리)"""
    try:
        import kakao_api
        return kakao_api
    except ImportError:
        return None


@app.route("/api/kakao/send", methods=["POST"])
def kakao_send():
    """💬 카카오톡 메시지 전송"""
    kakao = _get_kakao_api()
    if not kakao:
        return jsonify({"error": "kakao_api 모듈이 없습니다"}), 500

    data = request.json
    text = data.get("text", "").strip()
    send_type = data.get("type", "me")  # "me" | "friend"

    if not text:
        return jsonify({"error": "빈 메시지"}), 400

    if send_type == "me":
        result = kakao.send_to_me(text)
    elif send_type == "friend":
        uuids = data.get("receiver_uuids", [])
        if not uuids:
            return jsonify({"error": "수신자 UUID가 필요합니다"}), 400
        result = kakao.send_to_friend(uuids, text)
    else:
        return jsonify({"error": f"지원하지 않는 전송 타입: {send_type}"}), 400

    if result.get("success"):
        add_to_history("시스템", f"[카카오톡] {text[:100]}", "kakao_send")
        return jsonify(result)
    else:
        return jsonify(result), 400


@app.route("/api/kakao/friends", methods=["GET"])
def kakao_friends():
    """👥 카카오톡 친구 목록 조회"""
    kakao = _get_kakao_api()
    if not kakao:
        return jsonify({"error": "kakao_api 모듈이 없습니다"}), 500

    result = kakao.get_friends()
    if result.get("success"):
        return jsonify(result)
    else:
        return jsonify(result), 400


@app.route("/api/kakao/status", methods=["GET"])
def kakao_status():
    """📊 카카오톡 연동 상태"""
    kakao = _get_kakao_api()
    if not kakao:
        return jsonify({"configured": False, "authorized": False, "message": "kakao_api 모듈 없음"})

    return jsonify(kakao.get_status())


def _get_local_ip() -> str:
    """로컬 IP 주소 가져오기"""
    try:
        result = subprocess.run(
            ["ipconfig", "getifaddr", "en0"],
            capture_output=True, text=True, timeout=3
        )
        return result.stdout.strip()
    except Exception:
        return "localhost"


# ─── 서버 시작 ────────────────────────────────────────

if __name__ == "__main__":
    local_ip = _get_local_ip()
    tailscale_ip = os.getenv("TAILSCALE_IP", "")

    print(f"🚀 안티그래비티 모바일 에이전트 서버 시작!")
    print(f"📡 http://0.0.0.0:{PORT}")
    print(f"📱 로컬 대시보드: http://{local_ip}:{PORT}")
    if tailscale_ip:
        print(f"🌐 Tailscale: http://{tailscale_ip}:{PORT}")
    print(f"🔑 비밀번호: {AUTH_PASSWORD}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
