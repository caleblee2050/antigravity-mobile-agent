#!/usr/bin/env python3
"""
안티그래비티 모바일 에이전트 — 텔레그램 봇 (양방향 통신)
텔레그램을 통해 안티그래비티와 양방향으로 메시지를 주고받습니다.

기능:
- 텔레그램 메시지 수신 → Host 서버에 전달 → 안티그래비티에 입력
- AI 응답 폴링 → 텔레그램으로 푸시 전송
- 명령어: /status, /screenshot, /help

설정:
  .env에 TELEGRAM_TOKEN, TELEGRAM_CHAT_ID 설정 필요
"""

import os
import sys
import time
import signal
import threading
import logging
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# STT(음성 인식) 활성화 여부
ENABLE_STT = os.getenv("ENABLE_STT", "false").lower() == "true"
voice_transcriber = None
if ENABLE_STT:
    try:
        import voice_transcriber as _vt
        voice_transcriber = _vt
    except ImportError:
        logging.getLogger("telegram_bot").warning("voice_transcriber 모듈을 찾을 수 없습니다. STT 비활성화됨.")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(BASE_DIR, "logs")
PID_FILE = os.path.join(BASE_DIR, "telegram_bot.pid")
os.makedirs(LOGS_DIR, exist_ok=True)

# 로그 설정 (중복 핸들러 방지)
logger = logging.getLogger("telegram_bot")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh = logging.FileHandler(os.path.join(LOGS_DIR, "telegram.log"), encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    logger.propagate = False

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

HOST_URL = f"http://localhost:{os.getenv('PORT', '9150')}"
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "antigravity2026")

POLL_INTERVAL = 3  # AI 응답 폴링 간격 (초)


def ensure_single_instance():
    """PID 파일로 중복 실행 방지 — 이미 실행 중이면 기존 프로세스 kill"""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                old_pid = int(f.read().strip())
            # 기존 프로세스가 살아있으면 종료
            os.kill(old_pid, signal.SIGTERM)
            time.sleep(1)
            logger.info(f"⚠️ 기존 프로세스(PID {old_pid}) 종료함")
        except (ProcessLookupError, ValueError):
            pass  # 이미 죽었거나 잘못된 PID
        except PermissionError:
            logger.warning("기존 프로세스 종료 권한 없음")

    # 현재 PID 기록
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def cleanup_pid():
    """종료 시 PID 파일 삭제"""
    try:
        os.remove(PID_FILE)
    except FileNotFoundError:
        pass


if not TELEGRAM_TOKEN:
    print("❌ TELEGRAM_TOKEN이 .env에 설정되지 않았습니다.")
    exit(1)

if not TELEGRAM_CHAT_ID:
    print("❌ TELEGRAM_CHAT_ID가 .env에 설정되지 않았습니다.")
    exit(1)


class TelegramBot:
    def __init__(self):
        self.last_update_id = 0
        self.last_outbound_timestamp = ""
        self.running = True

    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """텔레그램 메시지 전송"""
        MAX_LEN = 4096
        try:
            # 긴 메시지 분할
            if len(text) > MAX_LEN:
                chunks = self._split_text(text, MAX_LEN)
                for chunk in chunks:
                    self._send_single(chunk, parse_mode)
                return True
            else:
                return self._send_single(text, parse_mode)
        except Exception as e:
            logger.error(f"메시지 전송 실패: {e}")
            return False

    def _send_single(self, text: str, parse_mode: str = "HTML") -> bool:
        """단일 메시지 전송"""
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        try:
            resp = requests.post(f"{TELEGRAM_API}/sendMessage", json=payload, timeout=10)
            if resp.status_code == 200:
                return True
            # HTML 파싱 실패 시 plain text로 재시도
            if parse_mode:
                import re
                payload["text"] = re.sub(r"<[^>]+>", "", text)
                payload.pop("parse_mode", None)
                resp2 = requests.post(f"{TELEGRAM_API}/sendMessage", json=payload, timeout=10)
                return resp2.status_code == 200
            return False
        except Exception as e:
            logger.error(f"API 요청 실패: {e}")
            return False

    def _split_text(self, text: str, max_len: int) -> list:
        """텍스트를 줄바꿈 기준으로 분할"""
        chunks = []
        while text:
            if len(text) <= max_len:
                chunks.append(text)
                break
            pos = text.rfind("\n", 0, max_len)
            if pos == -1:
                pos = max_len
            chunks.append(text[:pos])
            text = text[pos:].lstrip("\n")
        return chunks

    def _escape_html(self, text: str) -> str:
        """HTML 특수문자 이스케이프"""
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # ─── 텔레그램 메시지 수신 (Long Polling) ─────────────

    def poll_updates(self):
        """텔레그램 서버에서 새 메시지를 폴링"""
        try:
            resp = requests.get(
                f"{TELEGRAM_API}/getUpdates",
                params={
                    "offset": self.last_update_id + 1,
                    "timeout": 10,
                    "allowed_updates": '["message"]',
                },
                timeout=15,
            )
            if resp.status_code != 200:
                return []

            data = resp.json()
            if not data.get("ok"):
                return []

            updates = data.get("result", [])
            if updates:
                self.last_update_id = updates[-1]["update_id"]
            return updates
        except requests.exceptions.Timeout:
            return []
        except Exception as e:
            logger.error(f"텔레그램 폴링 오류: {e}")
            time.sleep(3)
            return []

    def handle_update(self, update: dict):
        """수신된 텔레그램 메시지 처리"""
        message = update.get("message", {})
        chat_id = str(message.get("chat", {}).get("id", ""))
        text = message.get("text", "").strip()

        # 허용된 chat_id만 처리
        if chat_id != TELEGRAM_CHAT_ID:
            logger.warning(f"미허용 chat_id: {chat_id}")
            return

        # 음성 메시지 처리
        voice = message.get("voice")
        if voice:
            self.handle_voice_message(voice)
            return

        if not text:
            return

        # 명령어 처리
        if text.startswith("/"):
            self.handle_command(text)
            return

        # 일반 메시지 → Host 서버로 전달
        self.forward_to_host(text)

    def handle_command(self, text: str):
        """텔레그램 명령어 처리"""
        cmd = text.split()[0].lower()

        if cmd == "/help" or cmd == "/start":
            help_text = (
                "🤖 <b>안티그래비티 모바일 에이전트</b>\n\n"
                "일반 메시지를 보내면 안티그래비티에 전달됩니다.\n\n"
                "<b>명령어:</b>\n"
                "/status — 시스템 상태 확인\n"
                "/screenshot — 현재 화면 스크린샷\n"
                "/help — 도움말"
            )
            self.send_message(help_text)

        elif cmd == "/status":
            try:
                resp = requests.get(f"{HOST_URL}/api/status", timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    components = data.get("components", {})
                    lines = ["📊 <b>시스템 상태</b>\n"]
                    for name, info in components.items():
                        icon = "🟢" if info.get("status") == "running" else "🔴"
                        lines.append(f"  {icon} {name}: {info.get('status', 'unknown')}")
                    if data.get("tailscale_ip"):
                        lines.append(f"  🌐 Tailscale: {data['tailscale_ip']}")
                    self.send_message("\n".join(lines))
                else:
                    self.send_message("❌ 상태 확인 실패")
            except Exception as e:
                self.send_message(f"❌ 서버 연결 실패: {e}")

        elif cmd == "/screenshot":
            try:
                resp = requests.get(f"{HOST_URL}/api/screenshot", timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("data"):
                        import base64
                        img_bytes = base64.b64decode(data["data"])
                        files = {"photo": ("screenshot.jpg", img_bytes, "image/jpeg")}
                        payload = {"chat_id": TELEGRAM_CHAT_ID}
                        requests.post(
                            f"{TELEGRAM_API}/sendPhoto",
                            data=payload,
                            files=files,
                            timeout=15,
                        )
                    else:
                        self.send_message("📸 스크린샷이 아직 없습니다.")
                else:
                    self.send_message("❌ 스크린샷 가져오기 실패")
            except Exception as e:
                self.send_message(f"❌ 스크린샷 오류: {e}")

        else:
            self.send_message("❓ 모르는 명령어입니다. /help 를 입력하세요.")

    def handle_voice_message(self, voice: dict):
        """텔레그램 음성 메시지 처리 (STT 변환)"""
        if not ENABLE_STT or voice_transcriber is None:
            self.send_message(
                "🎤 <b>음성 인식(STT)이 비활성화</b> 상태입니다.\n\n"
                "활성화하려면 <code>.env</code>에서:\n"
                "1. <code>ENABLE_STT=true</code> 설정\n"
                "2. <code>GOOGLE_CLOUD_API_KEY=...</code> 설정\n"
                "3. 봇 재시작"
            )
            return

        file_id = voice.get("file_id", "")
        duration = voice.get("duration", 0)

        if not file_id:
            self.send_message("❌ 음성 파일 ID를 가져올 수 없습니다.")
            return

        # 처리 중 알림
        self.send_message(f"🎤 음성 인식 중... ({duration}초)")
        logger.info(f"🎤 음성 메시지 수신 (duration={duration}s, file_id={file_id[:20]}...)")

        # 1) 음성 파일 다운로드
        audio_bytes = voice_transcriber.download_telegram_voice(file_id, TELEGRAM_TOKEN)
        if not audio_bytes:
            self.send_message("❌ 음성 파일 다운로드에 실패했습니다.")
            return

        # 2) STT 변환
        transcribed_text = voice_transcriber.transcribe_audio(audio_bytes)
        if not transcribed_text:
            self.send_message("❌ 음성을 인식하지 못했습니다. 다시 녹음해 주세요.")
            return

        # 3) 인식 결과 표시 후 Host로 전달
        self.send_message(f"📝 <b>인식 결과:</b>\n{self._escape_html(transcribed_text)}")
        self.forward_to_host(transcribed_text)

    def forward_to_host(self, text: str):
        """텔레그램 메시지를 Host 서버로 전달"""
        try:
            resp = requests.post(
                f"{HOST_URL}/api/msg",
                json={"text": text, "password": AUTH_PASSWORD, "sender": "텔레그램"},
                timeout=5,
            )
            if resp.status_code == 200:
                self.send_message(f"📨 <b>요청 접수</b>\n\n{self._escape_html(text)}\n\n⏳ 처리 중...")
                logger.info(f"📩 메시지 전달 완료: {text[:80]}")
            else:
                self.send_message("❌ 메시지 전달 실패")
                logger.error(f"메시지 전달 실패: {resp.text}")
        except Exception as e:
            self.send_message(f"❌ 서버 연결 실패: {e}")
            logger.error(f"서버 연결 실패: {e}")

    # ─── AI 응답 폴링 ─────────────────────────────────

    def poll_ai_replies(self):
        """Host 서버에서 AI 응답을 폴링하여 텔레그램으로 전송"""
        while self.running:
            try:
                resp = requests.get(f"{HOST_URL}/api/sync", timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    outbound = data.get("outbound", {})

                    if (
                        outbound.get("text")
                        and outbound.get("timestamp") != self.last_outbound_timestamp
                    ):
                        self.last_outbound_timestamp = outbound["timestamp"]
                        reply_text = outbound["text"]

                        # AI 응답을 텔레그램으로 전송
                        preview = reply_text[:3500] if len(reply_text) > 3500 else reply_text
                        msg = f"🧠 <b>AI 응답</b>\n\n{self._escape_html(preview)}"
                        if len(reply_text) > 3500:
                            msg += "\n\n⋯ (이하 생략)"
                        self.send_message(msg)
                        logger.info(f"🧠 AI 응답 전송 완료 ({len(reply_text)}자)")
            except Exception:
                pass

            time.sleep(POLL_INTERVAL)

    # ─── 메인 루프 ────────────────────────────────────

    def run(self):
        """메인 실행"""
        ensure_single_instance()

        logger.info("🤖 텔레그램 봇 시작!")
        logger.info(f"📡 Host 서버: {HOST_URL}")
        logger.info(f"📺 Chat ID: {TELEGRAM_CHAT_ID}")

        # 시작 알림
        self.send_message("🚀 <b>안티그래비티 모바일 에이전트</b> 연결됨!\n\n/help 로 사용법을 확인하세요.")

        # 컴포넌트 상태 보고
        try:
            requests.post(
                f"{HOST_URL}/api/component/status",
                json={"component": "telegram", "status": "running"},
                timeout=3,
            )
        except Exception:
            pass

        # AI 응답 폴링 스레드 시작
        reply_thread = threading.Thread(target=self.poll_ai_replies, daemon=True)
        reply_thread.start()

        # 텔레그램 메시지 수신 루프 (메인 스레드)
        try:
            while self.running:
                updates = self.poll_updates()
                for update in updates:
                    self.handle_update(update)
        except KeyboardInterrupt:
            logger.info("🛑 텔레그램 봇 종료")
            self.running = False
            cleanup_pid()
            try:
                requests.post(
                    f"{HOST_URL}/api/component/status",
                    json={"component": "telegram", "status": "stopped"},
                    timeout=3,
                )
            except Exception:
                pass


if __name__ == "__main__":
    import atexit
    atexit.register(cleanup_pid)
    bot = TelegramBot()
    bot.run()
