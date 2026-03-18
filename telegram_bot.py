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

# ─── 버전 정보 ───────────────────────────────────────
import os

def _read_version() -> str:
    """VERSION 파일에서 버전 읽기 (없으면 기본값)"""
    try:
        vf = os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")
        with open(vf, "r") as f:
            return f.read().strip()
    except Exception:
        return "0.0.0"

VERSION = _read_version()
GITHUB_REPO = "caleblee2050/antigravity-mobile-agent"

import json
import sys
import time
import signal
import subprocess
import threading
import logging
import hashlib
import tempfile
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

# TTS(음성 합성) 활성화 여부
ENABLE_TTS = os.getenv("ENABLE_TTS", "true").lower() == "true"
tts_engine_instance = None
if ENABLE_TTS:
    try:
        from tts_engine import get_tts_engine, list_available_engines
        tts_engine_instance = get_tts_engine()
        if tts_engine_instance:
            logging.getLogger("telegram_bot").info(f"🔊 TTS 엔진 로드: {tts_engine_instance.name}")
        else:
            logging.getLogger("telegram_bot").warning("⚠️ 사용 가능한 TTS 엔진이 없습니다.")
    except ImportError:
        logging.getLogger("telegram_bot").warning("tts_engine 모듈을 찾을 수 없습니다. TTS 비활성화됨.")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(BASE_DIR, "logs")
# 글로벌 PID: 같은 토큰이면 어느 디렉토리에서 실행해도 중복 감지
_token_hash = hashlib.md5(os.getenv("TELEGRAM_TOKEN", "").encode()).hexdigest()[:8]
PID_FILE = os.path.join(tempfile.gettempdir(), f"telegram_bot_{_token_hash}.pid")
PID_FILE_LOCAL = os.path.join(BASE_DIR, "telegram_bot.pid")  # 하위 호환
CONFIG_FILE = os.path.join(BASE_DIR, "agent_config.json")
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
    """PID 파일로 중복 실행 방지 — 이미 실행 중이면 자기 자신이 종료

    글로벌(/tmp) PID 파일을 사용하여 같은 봇 토큰이면
    어떤 디렉토리에서 실행하든 중복을 감지합니다.
    """
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                old_pid = int(f.read().strip())
            if old_pid != os.getpid():
                # 기존 프로세스가 살아있으면 → 자기가 종료
                os.kill(old_pid, 0)  # 존재 확인만 (signal 0)
                logger.info(f"⚠️ 이미 실행 중(PID {old_pid}), 새 인스턴스 종료")
                sys.exit(0)
        except (ProcessLookupError, ValueError):
            pass  # 이미 죽었거나 잘못된 PID
        except PermissionError:
            pass  # 확인 불가 → 새로 시작

    # 현재 PID 기록 (글로벌 + 로컬 하위 호환)
    current_pid = str(os.getpid())
    with open(PID_FILE, "w") as f:
        f.write(current_pid)
    try:
        with open(PID_FILE_LOCAL, "w") as f:
            f.write(current_pid)
    except Exception:
        pass  # 로컬 파일 쓰기 실패는 무시


def cleanup_pid():
    """종료 시 PID 파일 삭제 (글로벌 + 로컬)"""
    for pf in (PID_FILE, PID_FILE_LOCAL):
        try:
            os.remove(pf)
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
        self.nickname_setup_state = None  # None | "awaiting_user_nick" | "awaiting_agent_nick"
        self.voice_mode = os.getenv("TTS_AUTO_REPLY", "false").lower() == "true"  # 음성 응답 모드
        self.config = self._load_config()
        self._update_checked = False  # 시작 시 1회만 체크

    def _load_config(self) -> dict:
        """agent_config.json 로드 (없으면 example에서 자동 생성)"""
        try:
            if not os.path.exists(CONFIG_FILE):
                # example 파일에서 자동 복사
                example_file = os.path.join(BASE_DIR, "agent_config.example.json")
                if os.path.exists(example_file):
                    import shutil
                    shutil.copy2(example_file, CONFIG_FILE)
                    logger.info("📋 agent_config.example.json → agent_config.json 자동 생성")
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {"user_nickname": "", "agent_nickname": "", "first_run_completed": False, "language": "ko"}

    def _save_config(self):
        """agent_config.json 저장"""
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"설정 저장 실패: {e}")

    def get_greeting(self, template: str) -> str:
        """호칭이 설정되어 있으면 적용된 인사말 반환"""
        user_nick = self.config.get("user_nickname", "")
        if user_nick:
            return template.replace("{user}", user_nick)
        return template.replace("{user} ", "").replace("{user}", "")

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

    def send_voice(self, text: str) -> bool:
        """텍스트를 TTS로 변환하여 텔레그램 음성 메시지로 전송"""
        if not tts_engine_instance:
            logger.warning("음성 전송 실패: TTS 엔진 없음")
            return False

        try:
            # 긴 텍스트는 요약하여 TTS
            tts_text = text[:500] if len(text) > 500 else text
            # 코드 블록 제거 (음성으로는 부적합)
            import re
            tts_text = re.sub(r'```[\s\S]*?```', '코드 블록 생략', tts_text)
            tts_text = re.sub(r'`[^`]+`', '', tts_text)
            # HTML 태그 제거
            tts_text = re.sub(r'<[^>]+>', '', tts_text)
            # 빈 줄 정리
            tts_text = re.sub(r'\n{3,}', '\n\n', tts_text).strip()

            if not tts_text:
                return False

            audio_bytes = tts_engine_instance.synthesize(tts_text)
            if not audio_bytes:
                logger.error("TTS 합성 실패: 오디오 없음")
                return False

            # 텔레그램 음성 메시지 전송
            files = {"voice": ("response.ogg", audio_bytes, "audio/ogg")}
            payload = {"chat_id": TELEGRAM_CHAT_ID}
            resp = requests.post(
                f"{TELEGRAM_API}/sendVoice",
                data=payload,
                files=files,
                timeout=30,
            )
            if resp.status_code == 200:
                logger.info(f"🔊 음성 응답 전송 완료 ({len(audio_bytes)} bytes)")
                return True
            else:
                logger.error(f"음성 전송 실패: {resp.status_code} {resp.text[:200]}")
                return False
        except Exception as e:
            logger.error(f"음성 전송 오류: {e}")
            return False

    # ─── 텔레그램 메시지 수신 (Long Polling) ─────────────

    def poll_updates(self):
        """텔레그램 서버에서 새 메시지를 폴링"""
        try:
            resp = requests.get(
                f"{TELEGRAM_API}/getUpdates",
                params={
                    "offset": self.last_update_id + 1,
                    "timeout": 10,
                    "allowed_updates": '["message","callback_query"]',
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
        """수신된 텔레그램 메시지/콜백 처리"""
        # 인라인 버튼 콜백 처리
        if "callback_query" in update:
            self._handle_callback_query(update["callback_query"])
            return

        message = update.get("message", {})
        chat_id = str(message.get("chat", {}).get("id", ""))
        text = message.get("text", "").strip()

        # 허용된 chat_id만 처리
        if chat_id != TELEGRAM_CHAT_ID:
            logger.warning(f"미허용 chat_id: {chat_id}")
            return

        # 호칭 설정 모드 처리
        if self.nickname_setup_state:
            self._handle_nickname_setup(text)
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

    def _start_nickname_setup(self):
        """호칭 설정 대화 시작"""
        self.nickname_setup_state = "awaiting_user_nick"
        self.send_message(
            "👋 <b>처음 만나서 반갑습니다!</b>\n\n"
            "서로 편하게 부를 수 있도록 호칭을 정해볼까요?\n\n"
            "<b>제가 당신을 어떻게 불러드릴까요?</b>\n"
            "(예: 보스, 대장, 형, 캡틴 등)",
        )
        logger.info("호칭 설정 대화 시작")

    def _handle_nickname_setup(self, text: str):
        """호칭 설정 대화 처리"""
        if not text:
            return

        if self.nickname_setup_state == "awaiting_user_nick":
            self.config["user_nickname"] = text
            self.nickname_setup_state = "awaiting_agent_nick"
            self.send_message(
                f"✅ 알겠습니다. 앞으로 <b>{text}</b>님이라고 부를게요!\n\n"
                f"그럼 <b>저를 뭐라고 불러주실 건가요?</b>\n"
                f"(예: 안티, 에이전트, 비서, 자비스 등)",
            )
        elif self.nickname_setup_state == "awaiting_agent_nick":
            self.config["agent_nickname"] = text
            self.config["first_run_completed"] = True
            self._save_config()
            self.nickname_setup_state = None
            user_nick = self.config["user_nickname"]
            self.send_message(
                f"🎉 호칭 설정 완료!\n\n"
                f"👤 당신 → <b>{user_nick}</b>\n"
                f"🤖 저 → <b>{text}</b>\n\n"
                f"{user_nick}님, 앞으로 잘 부탁드려요! 💪\n"
                f"이제 메시지를 보내시면 안티그래비티에 바로 전달됩니다."
            )
            logger.info(f"호칭 설정 완료: 사용자={user_nick}, 에이전트={text}")

    def handle_command(self, text: str):
        """텔레그램 명령어 처리"""
        cmd = text.split()[0].lower()

        if cmd == "/help" or cmd == "/start":
            help_text = (
                f"🤖 <b>안티그래비티 모바일 에이전트</b> v{VERSION}\n\n"
                "일반 메시지를 보내면 안티그래비티에 전달됩니다.\n\n"
                "<b>기본 명령어:</b>\n"
                "/status — 시스템 상태 확인\n"
                "/screenshot — 현재 화면 스크린샷\n"
                "/windows — 열린 창 목록\n"
                "/target [번호] — 타겟 창 변경\n"
                "/voice — 🔊 음성 응답 ON/OFF\n"
                "/tts — TTS 엔진 상태\n"
                "/help — 도움말\n\n"
                "<b>카카오톡 명령어:</b>\n"
                "/카톡 [메시지] — 나에게 카톡 보내기\n"
                "/카톡친구 [이름] [메시지] — 친구에게 카톡 보내기\n"
                "/카톡목록 — 발송 가능한 친구 목록\n"
                "/카톡상태 — 카카오 연동 상태\n"
                "/카톡인증 — 카카오 OAuth 인증\n\n"
                "<b>피드백:</b>\n"
                "/feedback [내용] — 요구사항·건의\n"
                "/bug [내용] — 버그 신고\n"
                "/update — 업데이트 확인"
            )
            self.send_message(help_text)
            # 시작 시 업데이트 체크 (1회)
            if not self._update_checked:
                self._update_checked = True
                self._check_for_updates(silent=True)

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

        # ─── 워크스페이스 명령어 ────────────────────────────

        elif cmd == "/windows":
            try:
                resp = requests.get(f"{HOST_URL}/api/windows", timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    windows = data.get("windows", [])
                    current = data.get("current_target", 1)
                    if not windows:
                        self.send_message("❌ 열린 안티그래비티 창이 없습니다.")
                        return
                    lines = ["🖥️ <b>안티그래비티 창 목록</b>\n"]
                    for w in windows:
                        marker = " 🎯" if w["is_target"] else ""
                        lines.append(
                            f"  <b>{w['index']}.</b> {w['title']}"
                            f" ({w['position']['x']},{w['position']['y']}){marker}"
                        )
                    lines.append(f"\n현재 타겟: <b>{current}번</b> 창")
                    lines.append("\n💡 /target [번호] 로 변경")
                    self.send_message("\n".join(lines))
                else:
                    self.send_message("❌ 창 목록 조회 실패")
            except Exception as e:
                self.send_message(f"❌ 오류: {e}")

        elif cmd == "/target":
            parts = text.split()
            if len(parts) < 2:
                self.send_message(
                    "🎯 <b>사용법</b>: /target [번호]\n\n"
                    "예시:\n"
                    "  /target 2 — 2번 창으로 변경\n"
                    "  /target auto — 자동 탐색 모드\n\n"
                    "💡 /windows 로 창 목록 먼저 확인하세요."
                )
                return
            target_val = parts[1]
            try:
                if target_val.lower() == "auto":
                    resp = requests.post(
                        f"{HOST_URL}/api/target",
                        json={"index": None},
                        timeout=5,
                    )
                    if resp.status_code == 200:
                        self.send_message("✅ 타겟을 <b>자동 탐색</b> 모드로 변경했습니다.")
                    else:
                        self.send_message(f"❌ 변경 실패: {resp.json().get('error', '')}")
                else:
                    index = int(target_val)
                    resp = requests.post(
                        f"{HOST_URL}/api/target",
                        json={"index": index},
                        timeout=5,
                    )
                    if resp.status_code == 200:
                        self.send_message(f"✅ 타겟을 <b>{index}번</b> 창으로 변경했습니다.")
                    else:
                        self.send_message(f"❌ {resp.json().get('error', '변경 실패')}")
            except ValueError:
                self.send_message("❌ 숫자를 입력해주세요. 예: /target 2")
            except Exception as e:
                self.send_message(f"❌ 오류: {e}")

        # ─── 카카오톡 명령어 ─────────────────────────────

        elif cmd == "/카톡":
            msg_text = text[len("/카톡"):].strip()
            if not msg_text:
                self.send_message("💬 사용법: /카톡 [보낼 메시지]\n\n예: /카톡 오늘 미팅 5시입니다")
                return
            self._kakao_send_to_me(msg_text)

        elif cmd == "/카톡친구":
            parts = text[len("/카톡친구"):].strip().split(" ", 1)
            if len(parts) < 2:
                self.send_message("💬 사용법: /카톡친구 [이름] [메시지]\n\n예: /카톡친구 홍길동 내일 점심 먹자")
                return
            friend_name, msg_text = parts[0], parts[1]
            self._kakao_send_to_friend(friend_name, msg_text)

        elif cmd == "/카톡목록":
            self._kakao_list_friends()

        elif cmd == "/카톡상태":
            self._kakao_check_status()

        elif cmd == "/카톡인증":
            self.send_message(
                "🔐 <b>카카오 OAuth 인증</b>\n\n"
                "PC에서 다음 명령어를 실행해주세요:\n\n"
                "<code>cd 안티그래비티\ 모바일에이전트</code>\n"
                "<code>python kakao_api.py auth</code>\n\n"
                "브라우저가 열리면 카카오 계정으로 로그인하세요."
            )

        # ─── 피드백 및 업데이트 명령어 ──────────────────

        elif cmd == "/feedback":
            content = text[len("/feedback"):].strip()
            if not content:
                self.send_message(
                    "💬 <b>사용법</b>: /feedback [내용]\n\n"
                    "예: /feedback 스크린샷 품질을 높여주세요\n\n"
                    "요구사항, 건의, 아이디어 등 자유롭게 보내주세요!"
                )
                return
            self._submit_feedback("enhancement", content)

        elif cmd == "/bug":
            content = text[len("/bug"):].strip()
            if not content:
                self.send_message(
                    "🐛 <b>사용법</b>: /bug [내용]\n\n"
                    "예: /bug 음성 인식이 가끔 빈 값을 반환합니다\n\n"
                    "가능하면 재현 방법도 적어주세요!"
                )
                return
            self._submit_feedback("bug", content)

        elif cmd == "/update":
            self._check_for_updates(silent=False)

        elif cmd == "/voice":
            self.voice_mode = not self.voice_mode
            status = "🔊 ON" if self.voice_mode else "🔇 OFF"
            engine_name = tts_engine_instance.name if tts_engine_instance else "없음"
            self.send_message(
                f"🎙️ <b>음성 응답 모드: {status}</b>\n\n"
                f"TTS 엔진: {engine_name}\n"
                f"음성 입력 시 음성으로 답변합니다."
            )

        elif cmd == "/tts":
            if tts_engine_instance:
                self.send_message(
                    f"🔊 <b>TTS 엔진 상태</b>\n\n"
                    f"  🟢 활성 엔진: {tts_engine_instance.name}\n"
                    f"  🎙️ 음성 모드: {'ON' if self.voice_mode else 'OFF'}\n\n"
                    f"💡 /voice 로 음성 응답을 토글하세요."
                )
            else:
                self.send_message(
                    "🔇 <b>TTS 비활성화</b>\n\n"
                    "edge-tts를 설치하세요:\n"
                    "<code>pip install edge-tts</code>"
                )

        else:
            self.send_message("❓ 모르는 명령어입니다. /help 를 입력하세요.")

    # ─── 카카오톡 헬퍼 메서드 ────────────────────────────

    def _kakao_send_to_me(self, text: str):
        """카카오톡 나에게 보내기"""
        try:
            resp = requests.post(
                f"{HOST_URL}/api/kakao/send",
                json={"text": text, "type": "me"},
                timeout=10,
            )
            data = resp.json()
            if resp.status_code == 200 and data.get("success"):
                self.send_message(f"✅ <b>카카오톡 전송 완료</b>\n\n💬 {self._escape_html(text[:200])}")
            else:
                self.send_message(f"❌ 카카오톡 전송 실패: {data.get('message', '알 수 없는 오류')}")
        except Exception as e:
            self.send_message(f"❌ 카카오톡 서버 오류: {e}")

    def _kakao_send_to_friend(self, friend_name: str, text: str):
        """카카오톡 친구에게 보내기"""
        try:
            # 1) 친구 목록 조회
            resp = requests.get(f"{HOST_URL}/api/kakao/friends", timeout=10)
            if resp.status_code != 200:
                self.send_message("❌ 친구 목록을 가져올 수 없습니다.")
                return

            data = resp.json()
            friends = data.get("friends", [])

            # 이름으로 친구 찾기
            matched = [f for f in friends if friend_name in f.get("profile_nickname", "")]
            if not matched:
                names = ", ".join([f.get("profile_nickname", "?") for f in friends[:10]])
                self.send_message(
                    f"❌ '{friend_name}' 친구를 찾을 수 없습니다.\n\n"
                    f"발송 가능한 친구: {names or '없음'}"
                )
                return

            # 2) 메시지 전송
            uuids = [f["uuid"] for f in matched]
            resp2 = requests.post(
                f"{HOST_URL}/api/kakao/send",
                json={"text": text, "type": "friend", "receiver_uuids": uuids},
                timeout=10,
            )
            data2 = resp2.json()
            if resp2.status_code == 200 and data2.get("success"):
                names = ", ".join([f.get("profile_nickname", "") for f in matched])
                self.send_message(f"✅ <b>카카오톡 전송 완료</b>\n👤 {names}\n💬 {self._escape_html(text[:200])}")
            else:
                self.send_message(f"❌ 전송 실패: {data2.get('message', '알 수 없는 오류')}")
        except Exception as e:
            self.send_message(f"❌ 카카오톡 오류: {e}")

    def _kakao_list_friends(self):
        """카카오톡 발송 가능한 친구 목록 조회"""
        try:
            resp = requests.get(f"{HOST_URL}/api/kakao/friends", timeout=10)
            data = resp.json()

            if resp.status_code == 200 and data.get("success"):
                friends = data.get("friends", [])
                if not friends:
                    self.send_message("📋 메시지 수신에 동의한 친구가 없습니다.")
                    return

                lines = [f"👥 <b>카카오톡 친구 목록</b> ({len(friends)}명)\n"]
                for i, f in enumerate(friends[:20], 1):
                    lines.append(f"  {i}. {f.get('profile_nickname', '알 수 없음')}")
                if len(friends) > 20:
                    lines.append(f"  ⋯ 외 {len(friends) - 20}명")
                self.send_message("\n".join(lines))
            else:
                self.send_message(f"❌ {data.get('message', '친구 목록 조회 실패')}")
        except Exception as e:
            self.send_message(f"❌ 친구 목록 오류: {e}")

    def _kakao_check_status(self):
        """카카오톡 연동 상태 확인"""
        try:
            resp = requests.get(f"{HOST_URL}/api/kakao/status", timeout=5)
            data = resp.json()

            configured = data.get("configured", False)
            authorized = data.get("authorized", False)
            expired = data.get("expired", None)

            lines = ["📊 <b>카카오톡 연동 상태</b>\n"]
            lines.append(f"  {'🟢' if configured else '🔴'} REST API 키: {'설정됨' if configured else '미설정'}")
            lines.append(f"  {'🟢' if authorized else '🔴'} OAuth 인증: {'완료' if authorized else '필요'}")
            if expired is not None:
                lines.append(f"  {'🔴' if expired else '🟢'} 토큰 상태: {'만료됨' if expired else '유효'}")

            if not configured:
                lines.append("\n💡 .env에 KAKAO_REST_API_KEY를 설정하세요.")
            elif not authorized:
                lines.append("\n💡 /카톡인증 으로 OAuth 인증을 진행하세요.")

            self.send_message("\n".join(lines))
        except Exception as e:
            self.send_message(f"❌ 상태 확인 실패: {e}")

    # ─── 업데이트 체크 & 피드백 ─────────────────────────
    # 주기적 업데이트 체크는 run.sh 워치독이 담당 (봇 버전 독립적)


    def _check_for_updates(self, silent: bool = True):
        """GitHub 최신 릴리즈/태그와 현재 버전 비교"""
        try:
            resp = requests.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                timeout=5,
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            if resp.status_code == 200:
                data = resp.json()
                latest = data.get("tag_name", "").lstrip("v")
                notes = data.get("body", "")[:200]

                if latest and latest != VERSION:
                    self._send_update_available(latest, notes)
                elif not silent:
                    self.send_message(f"✅ 최신 버전입니다 (v{VERSION})")
            elif resp.status_code == 404:
                # 릴리즈가 아직 없으면 태그로 체크
                resp2 = requests.get(
                    f"https://api.github.com/repos/{GITHUB_REPO}/tags",
                    timeout=5,
                    headers={"Accept": "application/vnd.github.v3+json"},
                )
                if resp2.status_code == 200:
                    tags = resp2.json()
                    if tags:
                        latest_tag = tags[0].get("name", "").lstrip("v")
                        if latest_tag and latest_tag != VERSION:
                            self._send_update_available(latest_tag, "")
                        elif not silent:
                            self.send_message(f"✅ 최신 버전입니다 (v{VERSION})")
                    elif not silent:
                        self.send_message(f"ℹ️ 현재 버전: v{VERSION} (릴리즈 정보 없음)")
                elif not silent:
                    self.send_message(f"ℹ️ 현재 버전: v{VERSION}")
            elif not silent:
                self.send_message(f"ℹ️ 현재 버전: v{VERSION} (업데이트 확인 실패)")
        except Exception as e:
            if not silent:
                self.send_message(f"⚠️ 업데이트 확인 실패: {e}")
            logger.warning(f"업데이트 확인 실패: {e}")

    def _send_update_available(self, latest: str, notes: str):
        """업데이트 가능 알림 + 인라인 키보드 버튼"""
        text = (
            f"🆕 <b>새 업데이트가 있습니다!</b>\n\n"
            f"현재 버전: v{VERSION}\n"
            f"최신 버전: v{latest}\n"
        )
        if notes:
            text += f"\n{notes[:200]}{'...' if len(notes) >= 200 else ''}\n"

        # 인라인 키보드 버튼
        keyboard = {
            "inline_keyboard": [[
                {"text": "✅ 지금 업데이트", "callback_data": "do_update"},
                {"text": "⏰ 나중에", "callback_data": "skip_update"},
            ]]
        }
        try:
            requests.post(
                f"{self.api_url}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "reply_markup": keyboard,
                },
                timeout=10,
            )
        except Exception:
            # 인라인 버튼 실패 시 일반 메시지로 폴백
            self.send_message(text + "\n💡 업데이트: <code>git pull</code>")

    def _handle_callback_query(self, callback_query: dict):
        """인라인 버튼 콜백 처리 (업데이트 등)"""
        callback_id = callback_query.get("id", "")
        data = callback_query.get("data", "")

        # 콜백 응답 (버튼 로딩 해제)
        try:
            requests.post(
                f"{self.api_url}/answerCallbackQuery",
                json={"callback_query_id": callback_id},
                timeout=5,
            )
        except Exception:
            pass

        if data == "do_update":
            self._do_update()
        elif data == "skip_update":
            self.send_message("⏰ 업데이트를 나중으로 미룹니다.")

    def _do_update(self):
        """실제 업데이트 수행: git pull + pip install + 재시작"""
        self.send_message("🔄 업데이트 중...")
        try:
            # git pull
            result = subprocess.run(
                ["git", "pull", "origin", "main"],
                capture_output=True, text=True, timeout=30,
                cwd=BASE_DIR,
            )
            if result.returncode != 0:
                self.send_message(f"❌ git pull 실패:\n<code>{result.stderr[:300]}</code>")
                return

            # pip install
            pip_result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-q"],
                capture_output=True, text=True, timeout=60,
                cwd=BASE_DIR,
            )

            self.send_message(
                f"✅ <b>업데이트 완료!</b>\n\n"
                f"<code>{result.stdout[:200]}</code>\n\n"
                f"🔄 봇을 재시작합니다..."
            )

            # 재시작 — 새 프로세스 시작 후 현재 종료
            import time
            time.sleep(1)
            os.execv(sys.executable, [sys.executable] + sys.argv)

        except Exception as e:
            self.send_message(f"❌ 업데이트 실패: {e}")

    def _submit_feedback(self, feedback_type: str, content: str):
        """사용자 피드백을 GitHub Issue로 생성하거나 로컬 저장"""
        label = "bug" if feedback_type == "bug" else "enhancement"
        icon = "🐛" if feedback_type == "bug" else "💡"
        title = f"[{label}] {content[:60]}"

        # GitHub Issue 생성 시도
        github_token = os.getenv("GITHUB_TOKEN", "")
        if github_token:
            try:
                resp = requests.post(
                    f"https://api.github.com/repos/{GITHUB_REPO}/issues",
                    json={
                        "title": title,
                        "body": (
                            f"## {icon} 사용자 피드백\n\n"
                            f"**유형**: {label}\n"
                            f"**버전**: v{VERSION}\n\n"
                            f"### 내용\n{content}\n\n"
                            f"---\n_텔레그램 봇에서 자동 생성됨_"
                        ),
                        "labels": [label],
                    },
                    headers={
                        "Authorization": f"token {github_token}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                    timeout=10,
                )
                if resp.status_code == 201:
                    issue_url = resp.json().get("html_url", "")
                    self.send_message(
                        f"{icon} <b>피드백이 접수되었습니다!</b>\n\n"
                        f"내용: {content[:100]}\n"
                        f"추적: {issue_url}"
                    )
                    return
            except Exception as e:
                logger.warning(f"GitHub Issue 생성 실패: {e}")

        # 폴백: 로컬 파일에 저장
        feedback_dir = os.path.join(BASE_DIR, "feedback")
        os.makedirs(feedback_dir, exist_ok=True)
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{label}_{timestamp}.txt"
        filepath = os.path.join(feedback_dir, filename)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"유형: {label}\n")
                f.write(f"버전: v{VERSION}\n")
                f.write(f"시간: {timestamp}\n")
                f.write(f"내용: {content}\n")
            self.send_message(
                f"{icon} <b>피드백이 저장되었습니다!</b>\n\n"
                f"내용: {content[:100]}\n"
                f"파일: {filename}\n\n"
                f"💡 GitHub 연동 시 자동으로 Issue가 생성됩니다."
            )
        except Exception as e:
            self.send_message(f"❌ 피드백 저장 실패: {e}")

    def handle_voice_message(self, voice: dict):
        """텔레그램 음성 메시지 처리 (STT 변환)"""
        if not ENABLE_STT or voice_transcriber is None:
            self.send_message(
                "🎤 <b>음성 인식(STT)이 비활성화</b> 상태입니다.\n\n"
                "활성화하려면 <code>.env</code>에서:\n"
                "1. <code>ENABLE_STT=true</code> 설정\n"
                "2. <code>pip install faster-whisper</code> 설치\n"
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

        # 4) 음성 입력이었으면 자동으로 음성 응답 모드 활성화 (자연스러운 대화)
        if tts_engine_instance and not self.voice_mode:
            self.voice_mode = True
            logger.info("🎙️ 음성 입력 감지 → 음성 응답 모드 자동 활성화")

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

                        # 음성 응답 모드면 TTS로 음성도 전송
                        if self.voice_mode and tts_engine_instance:
                            self.send_voice(reply_text)

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

        # 첫 실행 시 호칭 설정
        if not self.config.get("first_run_completed", False):
            self._start_nickname_setup()
        else:
            # 시작 알림 — 30초 쿨다운 (워치독 재시작 시 스팸 방지)
            startup_msg_file = os.path.join(os.path.dirname(__file__), ".last_startup_msg")
            should_send = True
            try:
                if os.path.exists(startup_msg_file):
                    last_ts = os.path.getmtime(startup_msg_file)
                    if time.time() - last_ts < 30:
                        should_send = False
                        logger.info("⏭️ 시작 메시지 쿨다운 (30초 이내 재시작)")
            except Exception:
                pass

            if should_send:
                user_nick = self.config.get("user_nickname", "")
                agent_nick = self.config.get("agent_nickname", "안티그래비티")
                greeting = f"{user_nick}님, " if user_nick else ""
                self.send_message(
                    f"🚀 <b>{agent_nick}</b> 연결됨!\n\n"
                    f"{greeting}준비 완료입니다. /help 로 사용법을 확인하세요."
                )

            # 쿨다운 타임스탬프 갱신
            try:
                with open(startup_msg_file, "w") as f:
                    f.write(str(time.time()))
            except Exception:
                pass

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
