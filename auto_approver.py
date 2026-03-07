#!/usr/bin/env python3
"""
안티그래비티 모바일 에이전트 — 오토 어프로버 (macOS)
안티그래비티가 "Run", "Accept", "Allow" 등의 승인 버튼을 띄우면
이미지 인식으로 감지 → 자동 클릭합니다.

macOS 사용 시 주의사항:
- 시스템 설정 > 개인정보 보호 > 접근성에서 Python/터미널에 권한 필요
- Retina 디스플레이의 경우 confidence 값 조정이 필요할 수 있음
- images/ 폴더에 btn_*.png 형태의 승인 버튼 스크린샷을 저장해야 함
"""

import time
import os
import glob
import logging
from datetime import datetime
import pyautogui
from PIL import Image

# 설정
SCAN_INTERVAL = 2  # 초
CONFIDENCE = 0.8  # 이미지 매칭 신뢰도 (0.0~1.0)
IMAGES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")
LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")

# 로그 설정
os.makedirs(LOGS_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, "approver.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("auto_approver")


def detect_retina():
    """Retina 디스플레이 여부 감지"""
    try:
        import subprocess
        result = subprocess.run(
            ["system_profiler", "SPDisplaysDataType"],
            capture_output=True, text=True, timeout=5
        )
        if "Retina" in result.stdout or "resolution" in result.stdout.lower():
            return True
    except Exception:
        pass
    return False


def load_button_images():
    """images/ 폴더에서 btn_*.png 파일을 자동 로드"""
    os.makedirs(IMAGES_DIR, exist_ok=True)
    images = sorted(glob.glob(os.path.join(IMAGES_DIR, "btn_*.png")))

    if not images:
        logger.warning("images/ 폴더에 승인 버튼 이미지가 없습니다!")
        logger.info("📸 캡처 도우미를 실행하세요: python capture_buttons.py")
        return []

    loaded = []
    for img_path in images:
        name = os.path.basename(img_path)
        try:
            # 이미지 유효성 검사
            img = Image.open(img_path)
            img.verify()
            loaded.append(img_path)
            logger.info(f"✅ 로드됨: {name} ({os.path.getsize(img_path):,} bytes)")
        except Exception as e:
            logger.warning(f"⚠️ 유효하지 않은 이미지: {name} - {e}")

    return loaded


def scan_and_click(button_images: list, confidence: float):
    """화면에서 승인 버튼을 찾아 클릭"""
    for img_path in button_images:
        img_name = os.path.basename(img_path)

        try:
            location = pyautogui.locateOnScreen(
                img_path,
                confidence=confidence,
            )

            if location:
                center = pyautogui.center(location)
                logger.info(f"🎯 '{img_name}' 감지! 위치: ({center.x}, {center.y})")

                # 클릭
                pyautogui.click(center.x, center.y)
                logger.info(f"✅ '{img_name}' 클릭 완료!")

                # 연속 클릭 방지
                time.sleep(1.5)
                return True

        except pyautogui.ImageNotFoundException:
            pass
        except Exception as e:
            logger.debug(f"스캔 오류 ({img_name}): {e}")

    return False


def watch_for_new_images(last_count: int) -> list:
    """새로 추가된 이미지 감지 (핫 리로드)"""
    current = sorted(glob.glob(os.path.join(IMAGES_DIR, "btn_*.png")))
    if len(current) != last_count:
        logger.info(f"🔄 이미지 변경 감지! ({last_count}개 → {len(current)}개)")
        return load_button_images()
    return None


def main():
    """메인 루프"""
    logger.info("👁️ 오토 어프로버 (Sentinel) 시작!")
    logger.info(f"⏱️ 스캔 간격: {SCAN_INTERVAL}초")

    # Retina 디스플레이 감지
    is_retina = detect_retina()
    confidence = CONFIDENCE
    if is_retina:
        confidence = max(0.7, CONFIDENCE - 0.05)
        logger.info(f"🖥️ Retina 디스플레이 감지 → 신뢰도: {confidence}")
    else:
        logger.info(f"🎯 감지 신뢰도: {confidence}")

    logger.info("─" * 40)

    # 이미지 로드
    button_images = load_button_images()
    if not button_images:
        logger.info("⏳ 이미지가 추가되면 자동으로 감지를 시작합니다...")

    click_count = 0
    image_check_counter = 0

    while True:
        try:
            # 주기적으로 새 이미지 확인 (30초마다)
            image_check_counter += 1
            if image_check_counter >= 15:
                new_images = watch_for_new_images(len(button_images))
                if new_images is not None:
                    button_images = new_images
                image_check_counter = 0

            # 이미지가 있을 때만 스캔
            if button_images:
                clicked = scan_and_click(button_images, confidence)
                if clicked:
                    click_count += 1
                    logger.info(f"📊 총 자동 승인 횟수: {click_count}")

            time.sleep(SCAN_INTERVAL)

        except KeyboardInterrupt:
            logger.info(f"🛑 오토 어프로버 종료 (총 {click_count}번 자동 승인)")
            break
        except Exception as e:
            logger.error(f"⚠️ 오류: {e}")
            time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    main()
