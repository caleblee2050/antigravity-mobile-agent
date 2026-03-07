#!/usr/bin/env python3
"""
안티그래비티 모바일 에이전트 — 버튼 이미지 캡처 도우미
VS Code Antigravity의 승인 버튼 이미지를 쉽게 등록할 수 있는 대화형 스크립트입니다.

사용법: python capture_buttons.py
"""

import os
import sys
import shutil
import glob
import time
import subprocess

IMAGES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")
DESKTOP_PATH = os.path.expanduser("~/Desktop")
DOWNLOADS_PATH = os.path.expanduser("~/Downloads")

# 버튼별 추천 파일명
BUTTON_PRESETS = {
    "1": ("btn_run.png", "Run (실행) 버튼"),
    "2": ("btn_accept.png", "Accept (수락) 버튼"),
    "3": ("btn_allow.png", "Allow (허용) 버튼"),
    "4": ("btn_approve.png", "Approve (승인) 버튼"),
    "5": ("btn_yes.png", "Yes (예) 버튼"),
    "6": ("btn_continue.png", "Continue (계속) 버튼"),
    "7": ("btn_save.png", "Save (저장) 버튼"),
    "8": ("btn_confirm.png", "Confirm (확인) 버튼"),
}


def clear_screen():
    os.system("clear" if os.name != "nt" else "cls")


def show_status():
    """등록된 이미지 현황 표시"""
    os.makedirs(IMAGES_DIR, exist_ok=True)
    images = sorted(glob.glob(os.path.join(IMAGES_DIR, "btn_*.png")))

    print("\n📊 현재 등록된 버튼 이미지:")
    print("─" * 40)
    if images:
        for img in images:
            name = os.path.basename(img)
            size = os.path.getsize(img)
            print(f"  ✅ {name} ({size:,} bytes)")
    else:
        print("  ⚠️  등록된 이미지가 없습니다.")
    print("─" * 40)
    print()


def find_recent_screenshots():
    """최근 스크린샷 파일 목록 (데스크탑 + 다운로드)"""
    screenshots = []
    for directory in [DESKTOP_PATH, DOWNLOADS_PATH]:
        for pattern in ["Screenshot*.png", "스크린샷*.png", "Screen Shot*.png"]:
            screenshots.extend(glob.glob(os.path.join(directory, pattern)))

    # 수정 시간 기준 정렬 (최신 순)
    screenshots.sort(key=os.path.getmtime, reverse=True)
    return screenshots[:10]  # 최신 10개만


def capture_with_screencapture(button_name: str, filename: str):
    """macOS screencapture로 영역 캡처"""
    target = os.path.join(IMAGES_DIR, filename)

    print(f"\n🎯 '{button_name}' 캡처를 시작합니다.")
    print("   화면에서 해당 버튼 영역을 드래그로 선택해주세요.")
    print("   (ESC로 취소)")
    print()

    try:
        result = subprocess.run(
            ["screencapture", "-i", "-r", target],
            timeout=60
        )
        if result.returncode == 0 and os.path.exists(target):
            size = os.path.getsize(target)
            print(f"   ✅ 저장 완료: {filename} ({size:,} bytes)")
            return True
        else:
            print("   ❌ 캡처가 취소되었습니다.")
            return False
    except subprocess.TimeoutExpired:
        print("   ❌ 시간 초과 (60초)")
        return False


def import_from_file(filename: str):
    """기존 파일에서 가져오기"""
    recent = find_recent_screenshots()

    if recent:
        print("\n📸 최근 스크린샷:")
        for i, path in enumerate(recent, 1):
            name = os.path.basename(path)
            mtime = time.strftime("%m/%d %H:%M", time.localtime(os.path.getmtime(path)))
            print(f"  {i}. {name} ({mtime})")
        print()

    source = input("파일 경로 또는 번호 입력 (드래그 앤 드롭 가능): ").strip().strip("'\"")

    if source.isdigit() and 1 <= int(source) <= len(recent):
        source = recent[int(source) - 1]

    if not os.path.exists(source):
        print(f"❌ 파일을 찾을 수 없습니다: {source}")
        return False

    target = os.path.join(IMAGES_DIR, filename)
    shutil.copy2(source, target)
    print(f"✅ 복사 완료: {filename}")
    return True


def delete_image():
    """등록된 이미지 삭제"""
    images = sorted(glob.glob(os.path.join(IMAGES_DIR, "btn_*.png")))
    if not images:
        print("삭제할 이미지가 없습니다.")
        return

    print("\n삭제할 이미지 선택:")
    for i, img in enumerate(images, 1):
        print(f"  {i}. {os.path.basename(img)}")

    choice = input("\n번호 입력 (a=전체 삭제): ").strip()

    if choice == "a":
        for img in images:
            os.remove(img)
        print("✅ 모든 이미지 삭제 완료")
    elif choice.isdigit() and 1 <= int(choice) <= len(images):
        os.remove(images[int(choice) - 1])
        print(f"✅ {os.path.basename(images[int(choice) - 1])} 삭제 완료")


def main():
    os.makedirs(IMAGES_DIR, exist_ok=True)

    clear_screen()
    print("🎨 안티그래비티 — 버튼 이미지 캡처 도우미")
    print("═" * 45)
    print()
    print("VS Code Antigravity에서 승인 버튼(Run, Accept 등)이 뜰 때")
    print("해당 버튼 영역을 캡처하여 이미지로 등록합니다.")
    print("등록된 이미지는 오토 어프로버가 자동으로 감지 → 클릭합니다.")
    print()

    while True:
        show_status()

        print("📋 메뉴:")
        print("  [c] 화면에서 직접 캡처 (screencapture)")
        print("  [f] 기존 파일에서 가져오기")
        print("  [d] 등록된 이미지 삭제")
        print("  [q] 종료")
        print()

        choice = input("선택: ").strip().lower()

        if choice == "q":
            print("\n👋 종료합니다.")
            break

        elif choice in ("c", "f"):
            print("\n어떤 버튼을 등록할까요?")
            for key, (fname, desc) in BUTTON_PRESETS.items():
                exists = "✅" if os.path.exists(os.path.join(IMAGES_DIR, fname)) else "  "
                print(f"  {exists} {key}. {desc} ({fname})")
            print(f"     0. 커스텀 이름으로 등록")
            print()

            btn_choice = input("번호 선택: ").strip()

            if btn_choice in BUTTON_PRESETS:
                filename, button_name = BUTTON_PRESETS[btn_choice]
            elif btn_choice == "0":
                filename = input("파일명 (예: btn_custom.png): ").strip()
                if not filename.startswith("btn_"):
                    filename = "btn_" + filename
                if not filename.endswith(".png"):
                    filename += ".png"
                button_name = filename
            else:
                print("잘못된 선택입니다.")
                continue

            if choice == "c":
                capture_with_screencapture(button_name, filename)
            else:
                import_from_file(filename)

        elif choice == "d":
            delete_image()

        print()


if __name__ == "__main__":
    main()
