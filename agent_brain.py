#!/usr/bin/env python3
"""
안티그래비티 모바일 에이전트 — 브레인 에이전트 (macOS)
서버에서 모바일 메시지를 폴링하여 Antigravity 채팅창에 자동 입력합니다.

macOS 전용: AppleScript + PyAutoGUI 사용
앱 이름: Antigravity (Electron 기반)
"""

import time
import subprocess
import requests
import pyautogui
import pyperclip
import base64
import io
import logging
import os

# 로그 설정
LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, "brain.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("agent_brain")

HOST_URL = "http://localhost:9150"
POLL_INTERVAL = 3  # 초
SCREENSHOT_INTERVAL = 10  # 스크린샷 업데이트 간격 (폴링 횟수)

# macOS에서 Antigravity 앱의 이름
APP_NAME = "Antigravity"

# 모바일 메시지 프리픽스
MOBILE_PREFIX = "[📱 모바일] "


def activate_antigravity():
    """macOS: Antigravity 앱을 활성화"""
    script = f'tell application "{APP_NAME}" to activate'
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True, timeout=5)
        time.sleep(0.8)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        logger.warning(f"⚠️ {APP_NAME} 앱을 활성화할 수 없습니다.")
        return False


def type_message_to_antigravity(text: str):
    """
    Antigravity 채팅창에 메시지 입력.
    1. Antigravity 앱 활성화
    2. 클립보드에 텍스트 복사 → Cmd+V 붙여넣기
    3. Enter 전송
    """
    # 모바일에서 온 메시지임을 표시
    prefixed_text = f"{MOBILE_PREFIX}{text}"
    logger.info(f"📩 메시지 입력 시도: {text[:80]}...")

    if not activate_antigravity():
        return False

    time.sleep(0.5)

    # 클립보드에 텍스트 복사 후 붙여넣기
    pyperclip.copy(prefixed_text)
    time.sleep(0.2)
    pyautogui.hotkey("command", "v")
    time.sleep(0.3)

    # Enter로 전송
    pyautogui.press("enter")
    time.sleep(0.2)

    logger.info(f"✅ 메시지 전송 완료!")
    return True


def capture_screenshot():
    """전체 화면 스크린샷을 base64로 반환 (권한 있을 때만)"""
    try:
        screenshot = pyautogui.screenshot()
        buffer = io.BytesIO()
        screenshot.save(buffer, format="PNG", optimize=True)
        # 용량 절약을 위해 리사이즈
        from PIL import Image

        img = Image.open(io.BytesIO(buffer.getvalue()))
        img = img.resize((img.width // 2, img.height // 2), Image.LANCZOS)
        buffer2 = io.BytesIO()
        img.save(buffer2, format="JPEG", quality=50)
        return base64.b64encode(buffer2.getvalue()).decode("utf-8")
    except Exception as e:
        logger.debug(f"스크린샷 캡처 실패: {e}")
        return ""


def update_screenshot():
    """스크린샷을 서버에 업데이트 (실패해도 무시)"""
    img_data = capture_screenshot()
    if img_data:
        try:
            requests.post(
                f"{HOST_URL}/api/screenshot/update",
                json={"data": img_data},
                timeout=5,
            )
        except Exception:
            pass


def poll_for_messages():
    """서버에서 새로운 메시지를 폴링"""
    try:
        response = requests.get(f"{HOST_URL}/api/agent/poll", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("has_message"):
                return data.get("text", "")
    except Exception:
        pass
    return None


def report_status(status: str):
    """브레인 에이전트 상태를 서버에 보고"""
    try:
        requests.post(
            f"{HOST_URL}/api/component/status",
            json={"component": "brain", "status": status},
            timeout=3,
        )
    except Exception:
        pass


def main():
    """메인 루프"""
    logger.info("🧠 브레인 에이전트 시작!")
    logger.info(f"📡 서버: {HOST_URL}")
    logger.info(f"🎯 대상 앱: {APP_NAME}")
    logger.info(f"⏱️ 폴링 간격: {POLL_INTERVAL}초")
    logger.info("─" * 40)
    logger.info("📱 스마트폰에서 메시지를 보내면 Antigravity에 자동 입력됩니다.")

    screenshot_counter = 0
    report_status("running")

    while True:
        try:
            # 1. 새 메시지 확인
            message = poll_for_messages()
            if message:
                type_message_to_antigravity(message)

            # 2. 주기적으로 스크린샷 업데이트
            screenshot_counter += 1
            if screenshot_counter >= SCREENSHOT_INTERVAL:
                update_screenshot()
                screenshot_counter = 0

            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            logger.info("🛑 브레인 에이전트 종료")
            report_status("stopped")
            break
        except Exception as e:
            logger.error(f"⚠️ 오류: {e}")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
