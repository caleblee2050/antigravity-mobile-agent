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
    """macOS: Antigravity 앱을 활성화 (최상단으로)"""
    script = f'tell application "{APP_NAME}" to activate'
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True, timeout=5)
        time.sleep(0.8)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        logger.warning(f"⚠️ {APP_NAME} 앱을 활성화할 수 없습니다.")
        return False


def get_window_bounds():
    """Antigravity 윈도우의 위치와 크기를 반환"""
    script = '''
    tell application "System Events"
        tell process "Electron"
            if (count of windows) > 0 then
                set wPos to position of window 1
                set wSize to size of window 1
                return (item 1 of wPos as text) & "," & (item 2 of wPos as text) & "," & (item 1 of wSize as text) & "," & (item 2 of wSize as text)
            end if
        end tell
    end tell
    return ""
    '''
    try:
        result = subprocess.run(
            ["osascript", "-e", script], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split(",")
            return {
                "x": int(parts[0]),
                "y": int(parts[1]),
                "w": int(parts[2]),
                "h": int(parts[3]),
            }
    except Exception as e:
        logger.debug(f"윈도우 좌표 가져오기 실패: {e}")
    return None


def load_chat_input_config():
    """agent_config.json에서 채팅 입력 좌표 설정 로드"""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_config.json")
    try:
        if os.path.exists(config_path):
            import json
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            return cfg.get("chat_input_offset", None)
    except Exception:
        pass
    return None


def focus_chat_input():
    """
    채팅 입력창에 포커스

    좌측 패널(Explorer)에 포커스가 박혀서 모든 가상 단축키를 잡아먹는 현상을 완전히 회피하기 위해,
    실제 윈도우 좌표를 계산해 화면 우측 하단(채팅 입력창)을 마우스로 직접 강제 클릭합니다.
    """
    logger.info("🎯 마우스 클릭을 이용해 물리적인 포커스 탈취 시도...")
    
    # 1. 앱을 우선 활성화
    subprocess.run(["osascript", "-e", f'tell application "{APP_NAME}" to activate'], check=False)
    time.sleep(0.3)

    bounds = get_window_bounds()
    if bounds:
        x, y, w, h = bounds["x"], bounds["y"], bounds["w"], bounds["h"]
        
        # 기본 타겟: 우측 패널 하단 중앙 (채팅창 위치)
        target_x = x + w - 150
        target_y = y + h - 60
        
        # config 오프셋 덮어쓰기
        custom_offset = load_chat_input_config()
        if custom_offset:
            if "x_ratio" in custom_offset:
                target_x = x + int(w * custom_offset["x_ratio"])
            if "y_ratio" in custom_offset:
                target_y = y + int(h * custom_offset["y_ratio"])
        
        logger.info(f"👉 윈도우 내부 {target_x}, {target_y} 마우스 강제 클릭!")
        
        # 마우스 위치 백업 및 강제 클릭
        orig_x, orig_y = pyautogui.position()
        pyautogui.click(target_x, target_y)
        time.sleep(0.3)
        pyautogui.moveTo(orig_x, orig_y) # 원위치
    else:
        logger.warning("⚠️ 윈도우 좌표 획득 실패. 클릭 패스.")

    # 2. 보험용 Cmd+L 한 번 더 전송
    logger.info("🎯 보험용 Cmd+L 한 번 더 전송...")
    script = '''
    tell application "System Events"
        keystroke "l" using command down
    end tell
    '''
    subprocess.run(["osascript", "-e", script], check=False)
    time.sleep(0.3)
    
    return True


def type_message_to_antigravity(text: str):
    """
    Antigravity 채팅창에 메시지 입력.
    1. Antigravity 앱 활성화
    2. 채팅 입력창 포커스 (다단계 전략)
    3. 클립보드에 텍스트 복사 → Cmd+V 붙여넣기
    4. Enter 전송
    """
    # 모바일에서 온 메시지임을 표시
    prefixed_text = f"{MOBILE_PREFIX}{text}"
    logger.info(f"📩 메시지 입력 시도: {text[:80]}...")

    if not activate_antigravity():
        return False

    time.sleep(0.3)

    # 채팅 입력창에 포커스
    focus_chat_input()
    time.sleep(0.3)

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
        # LaunchAgent 백그라운드 구동 시 pyautogui.screenshot()이 
        # "could not create image from display" 에러를 내며 죽는 현상 방지
        import tempfile
        from PIL import Image
        
        tmp_file = os.path.join(tempfile.gettempdir(), "antigravity_screen.png")
        # macOS 네이티브 캡처 도구 사용 (-x: 소리 없음)
        result = subprocess.run(["screencapture", "-x", tmp_file], capture_output=True)
        
        if result.returncode != 0 or not os.path.exists(tmp_file):
            return ""
            
        img = Image.open(tmp_file)
        # 용량 절약을 위해 리사이즈
        img = img.resize((img.width // 2, img.height // 2), Image.LANCZOS)
        
        buffer = io.BytesIO()
        # RGB 변환 (RGBA 등일 경우 JPEG 저장 오류 방지)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        img.save(buffer, format="JPEG", quality=50)
        
        # 임시 파일 삭제
        os.remove(tmp_file)
        
        return base64.b64encode(buffer.getvalue()).decode("utf-8")
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
