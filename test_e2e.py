#!/usr/bin/env python3
"""
안티그래비티 모바일 에이전트 — E2E 테스트
서버 API, 메시지 플로우, 히스토리 등을 통합 테스트합니다.

사용법: python test_e2e.py
"""

import sys
import time
import json
import subprocess
import requests
import os

BASE_URL = "http://localhost:9150"
PASSWORD = "antigravity2026"
PASSED = 0
FAILED = 0
TOTAL = 0


def test(name, func):
    """테스트 실행"""
    global PASSED, FAILED, TOTAL
    TOTAL += 1
    try:
        result = func()
        if result:
            PASSED += 1
            print(f"  ✅ {name}")
        else:
            FAILED += 1
            print(f"  ❌ {name}")
    except Exception as e:
        FAILED += 1
        print(f"  ❌ {name} — 오류: {e}")


def wait_for_server(timeout=10):
    """서버가 시작될 때까지 대기"""
    for _ in range(timeout * 2):
        try:
            r = requests.get(f"{BASE_URL}/api/sync", timeout=2)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


# ─── 테스트 케이스 ───

def test_server_health():
    r = requests.get(f"{BASE_URL}/api/sync", timeout=5)
    return r.status_code == 200


def test_send_message():
    r = requests.post(
        f"{BASE_URL}/api/msg",
        json={"text": "E2E 테스트 메시지", "password": PASSWORD},
        timeout=5,
    )
    return r.status_code == 200 and r.json().get("status") == "ok"


def test_auth_failure():
    r = requests.post(
        f"{BASE_URL}/api/msg",
        json={"text": "인증 실패 테스트", "password": "wrong_password"},
        timeout=5,
    )
    return r.status_code == 401


def test_empty_message():
    r = requests.post(
        f"{BASE_URL}/api/msg",
        json={"text": "", "password": PASSWORD},
        timeout=5,
    )
    return r.status_code == 400


def test_agent_poll():
    # 메시지 전송
    requests.post(
        f"{BASE_URL}/api/msg",
        json={"text": "폴링 테스트", "password": PASSWORD},
        timeout=5,
    )
    # 폴링
    r = requests.get(f"{BASE_URL}/api/agent/poll", timeout=5)
    data = r.json()
    return data.get("has_message") and data.get("text") == "폴링 테스트"


def test_poll_clears_message():
    r = requests.get(f"{BASE_URL}/api/agent/poll", timeout=5)
    return not r.json().get("has_message")


def test_post_reply():
    r = requests.post(
        f"{BASE_URL}/api/reply",
        json={"text": "AI 응답 테스트"},
        timeout=5,
    )
    return r.status_code == 200


def test_sync_has_reply():
    r = requests.get(f"{BASE_URL}/api/sync", timeout=5)
    data = r.json()
    return data.get("outbound", {}).get("text") == "AI 응답 테스트"


def test_screenshot_update():
    r = requests.post(
        f"{BASE_URL}/api/screenshot/update",
        json={"data": "dGVzdA=="},
        timeout=5,
    )
    if r.status_code != 200:
        return False
    r2 = requests.get(f"{BASE_URL}/api/screenshot", timeout=5)
    return r2.json().get("data") == "dGVzdA=="


def test_history():
    r = requests.get(f"{BASE_URL}/api/history?limit=10", timeout=5)
    data = r.json()
    return isinstance(data.get("messages"), list) and len(data["messages"]) > 0


def test_history_clear():
    r = requests.post(
        f"{BASE_URL}/api/history/clear",
        json={"password": PASSWORD},
        timeout=5,
    )
    if r.status_code != 200:
        return False
    r2 = requests.get(f"{BASE_URL}/api/history", timeout=5)
    return len(r2.json().get("messages", [])) == 0


def test_status():
    r = requests.get(f"{BASE_URL}/api/status", timeout=5)
    data = r.json()
    return "components" in data and "server" in data["components"]


def test_component_status_update():
    r = requests.post(
        f"{BASE_URL}/api/component/status",
        json={"component": "brain", "status": "running"},
        timeout=5,
    )
    if r.status_code != 200:
        return False
    r2 = requests.get(f"{BASE_URL}/api/status", timeout=5)
    return r2.json()["components"]["brain"]["status"] == "running"


def test_quick_commands():
    r = requests.get(f"{BASE_URL}/api/commands", timeout=5)
    data = r.json()
    return isinstance(data.get("commands"), list) and len(data["commands"]) > 0


def test_approval_respond():
    r = requests.post(
        f"{BASE_URL}/api/approval/respond",
        json={"approved": True, "password": PASSWORD},
        timeout=5,
    )
    return r.status_code == 200


def test_dashboard_html():
    r = requests.get(f"{BASE_URL}/", timeout=5)
    return r.status_code == 200 and "Antigravity" in r.text


def test_notify_endpoint():
    r = requests.post(
        f"{BASE_URL}/api/notify",
        json={"title": "E2E 테스트", "body": "범용 알림 테스트", "type": "custom"},
        timeout=5,
    )
    return r.status_code == 200 and r.json().get("status") == "ok"


def test_notify_empty_body():
    r = requests.post(
        f"{BASE_URL}/api/notify",
        json={"title": "빈 내용", "body": "", "type": "custom"},
        timeout=5,
    )
    return r.status_code == 400


def test_notify_task_complete():
    r = requests.post(
        f"{BASE_URL}/api/notify",
        json={"title": "빌드 완료", "body": "성공적으로 배포됨", "type": "task_complete"},
        timeout=5,
    )
    return r.status_code == 200


def test_voice_transcriber_import():
    try:
        import voice_transcriber
        return hasattr(voice_transcriber, "transcribe_audio") and hasattr(voice_transcriber, "download_telegram_voice")
    except ImportError:
        return False


def test_voice_transcriber_api_key():
    try:
        import voice_transcriber
        return bool(voice_transcriber.GOOGLE_CLOUD_API_KEY)
    except Exception:
        return False


# ─── 카카오톡 테스트 케이스 ───


def test_kakao_module_import():
    try:
        import kakao_api
        return (
            hasattr(kakao_api, "send_to_me")
            and hasattr(kakao_api, "get_friends")
            and hasattr(kakao_api, "get_status")
        )
    except ImportError:
        return False


def test_kakao_token_file():
    import json, tempfile
    test_data = {"access_token": "test", "refresh_token": "test", "expires_at": 0}
    tmp_path = os.path.join(tempfile.gettempdir(), "kakao_test_tokens.json")
    try:
        with open(tmp_path, "w") as f:
            json.dump(test_data, f)
        with open(tmp_path, "r") as f:
            loaded = json.load(f)
        os.remove(tmp_path)
        return loaded == test_data
    except Exception:
        return False


def test_kakao_send_endpoint():
    r = requests.post(
        f"{BASE_URL}/api/kakao/send",
        json={"text": "E2E 테스트", "type": "me"},
        timeout=5,
    )
    # API 키 미설정이면 400 (인증 필요 메시지), 설정되면 200
    return r.status_code in (200, 400)


def test_kakao_friends_endpoint():
    r = requests.get(f"{BASE_URL}/api/kakao/friends", timeout=5)
    return r.status_code in (200, 400)


def test_kakao_status_endpoint():
    r = requests.get(f"{BASE_URL}/api/kakao/status", timeout=5)
    data = r.json()
    return r.status_code == 200 and "configured" in data


def test_kakao_no_key_graceful():
    """API 키 미설정 시 에러가 아닌 적절한 메시지 반환 확인"""
    r = requests.get(f"{BASE_URL}/api/kakao/status", timeout=5)
    return r.status_code == 200


def main():
    global PASSED, FAILED, TOTAL

    print("🧪 안티그래비티 모바일 에이전트 — E2E 테스트")
    print("═" * 45)
    print("")

    # 서버가 이미 실행 중인지 확인
    server_proc = None
    if not wait_for_server(2):
        print("📡 서버 시작 중...")
        server_proc = subprocess.Popen(
            [sys.executable, "antigravity_host.py"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not wait_for_server(10):
            print("❌ 서버 시작 실패!")
            server_proc.kill()
            sys.exit(1)
        print("✅ 서버 시작됨\n")

    # 테스트 실행
    print("📋 API 테스트:")
    test("서버 상태 확인", test_server_health)
    test("대시보드 HTML 반환", test_dashboard_html)
    test("메시지 전송", test_send_message)
    test("인증 실패 처리", test_auth_failure)
    test("빈 메시지 거부", test_empty_message)

    print("\n📋 메시지 플로우 테스트:")
    test("브레인 에이전트 폴링", test_agent_poll)
    test("폴링 후 메시지 초기화", test_poll_clears_message)
    test("AI 응답 저장", test_post_reply)
    test("동기화에서 응답 확인", test_sync_has_reply)

    print("\n📋 스크린샷/승인 테스트:")
    test("스크린샷 업데이트 및 조회", test_screenshot_update)
    test("승인 응답", test_approval_respond)

    print("\n📋 신규 기능 테스트:")
    test("대화 히스토리 조회", test_history)
    test("히스토리 초기화", test_history_clear)
    test("시스템 상태 조회", test_status)
    test("컴포넌트 상태 업데이트", test_component_status_update)
    test("빠른 명령어 조회", test_quick_commands)

    print("\n📋 텔레그램 알림 테스트:")
    test("범용 알림 전송 (/api/notify)", test_notify_endpoint)
    test("빈 알림 거부", test_notify_empty_body)
    test("작업완료 알림 타입", test_notify_task_complete)

    print("\n📋 음성 인식 테스트:")
    test("voice_transcriber 모듈 import", test_voice_transcriber_import)
    test("음성 인식 API 키 설정 확인", test_voice_transcriber_api_key)

    print("\n📋 카카오톡 연동 테스트:")
    test("kakao_api 모듈 import", test_kakao_module_import)
    test("카카오 토큰 파일 읽기/쓰기", test_kakao_token_file)
    test("카카오 전송 엔드포인트", test_kakao_send_endpoint)
    test("카카오 친구 엔드포인트", test_kakao_friends_endpoint)
    test("카카오 상태 엔드포인트", test_kakao_status_endpoint)
    test("카카오 미인증 graceful 처리", test_kakao_no_key_graceful)

    # 결과
    print("")
    print("═" * 45)
    print(f"📊 결과: {PASSED}/{TOTAL} 통과, {FAILED} 실패")
    if FAILED == 0:
        print("🎉 모든 테스트 통과!")
    else:
        print(f"⚠️ {FAILED}개 테스트 실패")
    print("")

    # 서버 정리
    if server_proc:
        server_proc.terminate()
        server_proc.wait()

    sys.exit(0 if FAILED == 0 else 1)


if __name__ == "__main__":
    main()
