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

import json
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
        self.nickname_setup_state = None  # None | "awaiting_user_nick" | "awaiting_agent_nick"
        self.config = self._load_config()

    def _load_config(self) -> dict:
        """agent_config.json 로드"""
        try:
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
                "🤖 <b>안티그래비티 모바일 에이전트</b>\n\n"
                "일반 메시지를 보내면 안티그래비티에 전달됩니다.\n\n"
                "<b>기본 명령어:</b>\n"
                "/status — 시스템 상태 확인\n"
                "/screenshot — 현재 화면 스크린샷\n"
                "/windows — 열린 창 목록\n"
                "/target [번호] — 타겟 창 변경\n"
                "/help — 도움말\n\n"
                "<b>카카오톡 명령어:</b>\n"
                "/카톡 [메시지] — 나에게 카톡 보내기\n"
                "/카톡친구 [이름] [메시지] — 친구에게 카톡 보내기\n"
                "/카톡목록 — 발송 가능한 친구 목록\n"
                "/카톡상태 — 카카오 연동 상태\n"
                "/카톡인증 — 카카오 OAuth 인증"
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

        # 첫 실행 시 호칭 설정
        if not self.config.get("first_run_completed", False):
            self._start_nickname_setup()
        else:
            # 시작 알림 (호칭 적용)
            user_nick = self.config.get("user_nickname", "")
            agent_nick = self.config.get("agent_nickname", "안티그래비티")
            greeting = f"{user_nick}님, " if user_nick else ""
            self.send_message(
                f"🚀 <b>{agent_nick}</b> 연결됨!\n\n"
                f"{greeting}준비 완료입니다. /help 로 사용법을 확인하세요."
            )

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
