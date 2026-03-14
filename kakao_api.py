#!/usr/bin/env python3
"""
안티그래비티 모바일 에이전트 — 카카오톡 REST API 모듈
카카오 디벨로퍼스 REST API를 통해 메시지를 전송합니다.

기능:
- 나에게 보내기 (무료)
- 친구에게 보내기 (동의한 친구 한정)
- Access/Refresh Token 자동 관리

설정:
  .env에 KAKAO_REST_API_KEY 설정 필요
  최초 1회 authorize() 실행하여 토큰 발급 필요
"""

import json
import os
import time
import logging
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(BASE_DIR, "kakao_tokens.json")

logger = logging.getLogger("kakao_api")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    logger.propagate = False

# 카카오 API 상수
KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "")
KAKAO_CLIENT_SECRET = os.getenv("KAKAO_CLIENT_SECRET", "")
KAKAO_REDIRECT_URI = os.getenv("KAKAO_REDIRECT_URI", "http://localhost:9250/oauth")
KAKAO_AUTH_URL = "https://kauth.kakao.com"
KAKAO_API_URL = "https://kapi.kakao.com"
KAKAO_OAUTH_PORT = 9250


class KakaoTokenManager:
    """카카오 Access/Refresh Token 자동 관리"""

    def __init__(self):
        self.tokens = self._load_tokens()

    def _load_tokens(self) -> dict:
        """토큰 파일에서 로드"""
        try:
            if os.path.exists(TOKEN_FILE):
                with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"토큰 파일 로드 실패: {e}")
        return {"access_token": "", "refresh_token": "", "expires_at": 0}

    def _save_tokens(self):
        """토큰 파일에 저장"""
        try:
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                json.dump(self.tokens, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"토큰 저장 실패: {e}")

    @property
    def access_token(self) -> str:
        return self.tokens.get("access_token", "")

    @property
    def is_configured(self) -> bool:
        """카카오 API가 설정되어 있는지 확인"""
        return bool(KAKAO_REST_API_KEY)

    @property
    def is_authorized(self) -> bool:
        """유효한 토큰이 있는지 확인"""
        return bool(self.tokens.get("access_token"))

    @property
    def is_expired(self) -> bool:
        """Access Token이 만료되었는지 확인"""
        expires_at = self.tokens.get("expires_at", 0)
        return time.time() >= expires_at

    def get_valid_token(self) -> str:
        """유효한 Access Token 반환 (필요 시 자동 갱신)"""
        if not self.is_authorized:
            return ""

        if self.is_expired:
            if not self.refresh():
                return ""

        return self.access_token

    def authorize(self, code: str) -> bool:
        """인가 코드로 토큰 발급"""
        try:
            data = {
                "grant_type": "authorization_code",
                "client_id": KAKAO_REST_API_KEY,
                "redirect_uri": KAKAO_REDIRECT_URI,
                "code": code,
            }
            if KAKAO_CLIENT_SECRET:
                data["client_secret"] = KAKAO_CLIENT_SECRET
            resp = requests.post(
                f"{KAKAO_AUTH_URL}/oauth/token",
                data=data,
                timeout=10,
            )

            if resp.status_code == 200:
                data = resp.json()
                self.tokens = {
                    "access_token": data["access_token"],
                    "refresh_token": data.get("refresh_token", ""),
                    "expires_at": time.time() + data.get("expires_in", 21599),
                }
                self._save_tokens()
                logger.info("✅ 카카오 토큰 발급 완료")
                return True
            else:
                logger.error(f"토큰 발급 실패: {resp.text}")
                return False
        except Exception as e:
            logger.error(f"토큰 발급 오류: {e}")
            return False

    def refresh(self) -> bool:
        """Refresh Token으로 Access Token 갱신"""
        refresh_token = self.tokens.get("refresh_token", "")
        if not refresh_token:
            logger.warning("Refresh Token 없음 — 재인증 필요")
            return False

        try:
            data = {
                "grant_type": "refresh_token",
                "client_id": KAKAO_REST_API_KEY,
                "refresh_token": refresh_token,
            }
            if KAKAO_CLIENT_SECRET:
                data["client_secret"] = KAKAO_CLIENT_SECRET
            resp = requests.post(
                f"{KAKAO_AUTH_URL}/oauth/token",
                data=data,
                timeout=10,
            )

            if resp.status_code == 200:
                data = resp.json()
                self.tokens["access_token"] = data["access_token"]
                self.tokens["expires_at"] = time.time() + data.get("expires_in", 21599)
                # Refresh Token이 갱신된 경우 업데이트
                if "refresh_token" in data:
                    self.tokens["refresh_token"] = data["refresh_token"]
                self._save_tokens()
                logger.info("🔄 카카오 토큰 갱신 완료")
                return True
            else:
                logger.error(f"토큰 갱신 실패: {resp.text}")
                return False
        except Exception as e:
            logger.error(f"토큰 갱신 오류: {e}")
            return False


# 싱글톤 토큰 매니저
_token_manager = KakaoTokenManager()


def get_auth_url() -> str:
    """카카오 로그인 인가 URL 생성"""
    return (
        f"{KAKAO_AUTH_URL}/oauth/authorize"
        f"?client_id={KAKAO_REST_API_KEY}"
        f"&redirect_uri={KAKAO_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=talk_message,friends"
    )


def start_auth_flow():
    """브라우저를 열어 OAuth 인증 플로우 시작 (최초 1회)"""
    if not KAKAO_REST_API_KEY:
        logger.error("❌ KAKAO_REST_API_KEY가 .env에 설정되지 않았습니다.")
        return False

    auth_url = get_auth_url()
    logger.info(f"🌐 브라우저에서 카카오 로그인 중...")
    webbrowser.open(auth_url)

    # 로컬 서버에서 콜백 대기
    auth_code = _wait_for_auth_code()
    if auth_code:
        return _token_manager.authorize(auth_code)
    return False


def _wait_for_auth_code(timeout: int = 120) -> str:
    """OAuth 콜백 서버를 시작하여 인가 코드 수신 대기"""
    auth_code_holder = {"code": ""}

    class OAuthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            code = params.get("code", [None])[0]

            if code:
                auth_code_holder["code"] = code
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    "<!DOCTYPE html><html><body style='text-align:center;font-family:sans-serif;padding:40px'>"
                    "<h1>✅ 카카오톡 인증 완료!</h1>"
                    "<p>이 창을 닫아도 됩니다.</p>"
                    "<script>setTimeout(()=>window.close(),3000)</script>"
                    "</body></html>".encode("utf-8")
                )
            else:
                error = params.get("error_description", ["인증 실패"])[0]
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(f"<h1>❌ 인증 실패: {error}</h1>".encode("utf-8"))

        def log_message(self, format, *args):
            pass  # 로그 출력 억제

    server = HTTPServer(("localhost", KAKAO_OAUTH_PORT), OAuthHandler)
    server.timeout = timeout

    logger.info(f"📡 OAuth 콜백 서버 대기 중 (localhost:{KAKAO_OAUTH_PORT})...")
    server.handle_request()
    server.server_close()

    return auth_code_holder.get("code", "")


# ─── 메시지 전송 API ────────────────────────────────────


def send_to_me(text: str, link: dict = None) -> dict:
    """
    나에게 카카오톡 메시지 보내기 (무료)

    Args:
        text: 전송할 텍스트
        link: 선택 — {"web_url": "...", "mobile_web_url": "..."} 형태의 링크

    Returns:
        {"success": bool, "message": str}
    """
    token = _token_manager.get_valid_token()
    if not token:
        return {"success": False, "message": "카카오 인증이 필요합니다. /카톡인증 을 실행해주세요."}

    template = {
        "object_type": "text",
        "text": text,
        "link": link or {"web_url": "https://a4k.ai", "mobile_web_url": "https://a4k.ai"},
    }

    try:
        resp = requests.post(
            f"{KAKAO_API_URL}/v2/api/talk/memo/default/send",
            headers={"Authorization": f"Bearer {token}"},
            data={"template_object": json.dumps(template)},
            timeout=10,
        )

        if resp.status_code == 200:
            logger.info(f"📨 카카오톡 나에게 보내기 완료: {text[:50]}...")
            return {"success": True, "message": "카카오톡 전송 완료"}
        else:
            error_msg = resp.json().get("msg", resp.text)
            logger.error(f"카카오톡 전송 실패: {error_msg}")
            return {"success": False, "message": f"전송 실패: {error_msg}"}
    except Exception as e:
        logger.error(f"카카오톡 전송 오류: {e}")
        return {"success": False, "message": f"전송 오류: {e}"}


def get_friends() -> dict:
    """
    메시지 수신 동의한 친구 목록 조회

    Returns:
        {"success": bool, "friends": [{"uuid": str, "profile_nickname": str}], "message": str}
    """
    token = _token_manager.get_valid_token()
    if not token:
        return {"success": False, "friends": [], "message": "카카오 인증이 필요합니다."}

    try:
        resp = requests.get(
            f"{KAKAO_API_URL}/v1/api/talk/friends",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )

        if resp.status_code == 200:
            data = resp.json()
            friends = [
                {
                    "uuid": f.get("uuid", ""),
                    "profile_nickname": f.get("profile_nickname", "알 수 없음"),
                    "profile_thumbnail_image": f.get("profile_thumbnail_image", ""),
                }
                for f in data.get("elements", [])
            ]
            logger.info(f"👥 카카오 친구 목록 조회: {len(friends)}명")
            return {"success": True, "friends": friends, "message": f"{len(friends)}명의 친구"}
        else:
            error_msg = resp.json().get("msg", resp.text)
            return {"success": False, "friends": [], "message": f"조회 실패: {error_msg}"}
    except Exception as e:
        return {"success": False, "friends": [], "message": f"조회 오류: {e}"}


def send_to_friend(receiver_uuids: list, text: str, link: dict = None) -> dict:
    """
    친구에게 카카오톡 메시지 보내기 (동의한 친구 한정)

    Args:
        receiver_uuids: 수신자 UUID 리스트
        text: 전송할 텍스트
        link: 선택 — 링크 정보

    Returns:
        {"success": bool, "message": str}
    """
    token = _token_manager.get_valid_token()
    if not token:
        return {"success": False, "message": "카카오 인증이 필요합니다."}

    template = {
        "object_type": "text",
        "text": text,
        "link": link or {"web_url": "https://a4k.ai", "mobile_web_url": "https://a4k.ai"},
    }

    try:
        resp = requests.post(
            f"{KAKAO_API_URL}/v1/api/talk/friends/message/default/send",
            headers={"Authorization": f"Bearer {token}"},
            data={
                "receiver_uuids": json.dumps(receiver_uuids),
                "template_object": json.dumps(template),
            },
            timeout=10,
        )

        if resp.status_code == 200:
            logger.info(f"📨 카카오톡 친구에게 보내기 완료: {len(receiver_uuids)}명")
            return {"success": True, "message": f"{len(receiver_uuids)}명에게 전송 완료"}
        else:
            error_msg = resp.json().get("msg", resp.text)
            return {"success": False, "message": f"전송 실패: {error_msg}"}
    except Exception as e:
        return {"success": False, "message": f"전송 오류: {e}"}


def get_status() -> dict:
    """카카오톡 연동 상태 확인"""
    return {
        "configured": _token_manager.is_configured,
        "authorized": _token_manager.is_authorized,
        "expired": _token_manager.is_expired if _token_manager.is_authorized else None,
        "api_key_set": bool(KAKAO_REST_API_KEY),
    }


# ─── 직접 실행 시 인증 플로우 ──────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "auth":
        print("🔐 카카오 OAuth 인증을 시작합니다...")
        if start_auth_flow():
            print("✅ 인증 완료! 토큰이 저장되었습니다.")
            # 테스트 메시지 전송
            result = send_to_me("🚀 안티그래비티 에이전트에서 보낸 카카오톡 테스트 메시지입니다!")
            print(f"테스트 전송: {result}")
        else:
            print("❌ 인증 실패")
    elif len(sys.argv) > 1 and sys.argv[1] == "status":
        status = get_status()
        print(f"📊 카카오 상태: {json.dumps(status, indent=2, ensure_ascii=False)}")
    elif len(sys.argv) > 1 and sys.argv[1] == "send":
        msg = " ".join(sys.argv[2:]) or "안티그래비티 테스트 메시지"
        result = send_to_me(msg)
        print(f"📨 전송 결과: {result}")
    elif len(sys.argv) > 1 and sys.argv[1] == "friends":
        result = get_friends()
        if result.get("success"):
            friends_list = result.get("friends", [])
            if friends_list:
                print(f"👥 친구 {len(friends_list)}명:")
                for f in friends_list:
                    print(f"  • {f.get('profile_nickname', '?')} (UUID: {f.get('uuid', '?')})")
            else:
                print("📭 메시지 수신 동의한 친구가 없습니다.")
        else:
            print(f"❌ 조회 실패: {result.get('message', '알 수 없는 오류')}")
    elif len(sys.argv) > 2 and sys.argv[1] == "send_friend":
        uuid = sys.argv[2]
        msg = " ".join(sys.argv[3:]) or "안티그래비티 테스트 메시지"
        result = send_to_friend([uuid], msg)
        print(f"📨 전송 결과: {result}")
    else:
        print("사용법:")
        print("  python kakao_api.py auth           — OAuth 인증 (최초 1회)")
        print("  python kakao_api.py status         — 연동 상태 확인")
        print("  python kakao_api.py send [메시지]   — 나에게 카톡 보내기")
        print("  python kakao_api.py friends        — 친구 목록 조회")
        print("  python kakao_api.py send_friend <UUID> [메시지] — 친구에게 보내기")
