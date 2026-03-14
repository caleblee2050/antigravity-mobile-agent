#!/usr/bin/env python3
"""
안티그래비티 모바일 에이전트 — 음성 인식 모듈
Google Cloud Speech-to-Text API를 사용하여 텔레그램 음성 메시지를 텍스트로 변환합니다.

사용법:
  from voice_transcriber import transcribe_audio
  text = transcribe_audio(ogg_bytes)
"""

import os
import base64
import logging
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

logger = logging.getLogger("voice_transcriber")

GOOGLE_CLOUD_API_KEY = os.getenv("GOOGLE_CLOUD_API_KEY", "")
STT_API_URL = "https://speech.googleapis.com/v1/speech:recognize"


def transcribe_audio(audio_bytes: bytes, language: str = "ko-KR") -> str:
    """음성 데이터를 텍스트로 변환

    Args:
        audio_bytes: OGG/OGA 형식의 오디오 바이트 데이터
        language: 인식 언어 코드 (기본: 한국어)

    Returns:
        인식된 텍스트. 실패 시 빈 문자열.
    """
    if not GOOGLE_CLOUD_API_KEY:
        logger.error("GOOGLE_CLOUD_API_KEY가 설정되지 않았습니다.")
        return ""

    if not audio_bytes:
        logger.error("빈 오디오 데이터입니다.")
        return ""

    # Base64 인코딩
    audio_content = base64.b64encode(audio_bytes).decode("utf-8")

    # Google Cloud STT API 요청
    payload = {
        "config": {
            "encoding": "OGG_OPUS",
            "sampleRateHertz": 48000,
            "languageCode": language,
            "alternativeLanguageCodes": ["en-US"],
            "model": "default",
            "enableAutomaticPunctuation": True,
        },
        "audio": {
            "content": audio_content,
        },
    }

    try:
        resp = requests.post(
            f"{STT_API_URL}?key={GOOGLE_CLOUD_API_KEY}",
            json=payload,
            timeout=30,
        )

        if resp.status_code != 200:
            error_msg = resp.json().get("error", {}).get("message", resp.text)
            logger.error(f"STT API 오류 ({resp.status_code}): {error_msg}")
            return ""

        data = resp.json()
        results = data.get("results", [])

        if not results:
            logger.warning("음성 인식 결과가 없습니다 (묵음이거나 인식 불가).")
            return ""

        # 모든 결과의 첫 번째 대안을 연결
        transcripts = []
        for result in results:
            alternatives = result.get("alternatives", [])
            if alternatives:
                transcripts.append(alternatives[0].get("transcript", ""))

        full_text = " ".join(transcripts).strip()
        logger.info(f"🎤 음성 인식 완료: {full_text[:80]}...")
        return full_text

    except requests.exceptions.Timeout:
        logger.error("STT API 요청 시간 초과 (30초)")
        return ""
    except Exception as e:
        logger.error(f"STT 처리 오류: {e}")
        return ""


def download_telegram_voice(file_id: str, bot_token: str) -> bytes:
    """텔레그램 서버에서 음성 파일 다운로드

    Args:
        file_id: 텔레그램 파일 ID
        bot_token: 텔레그램 봇 토큰

    Returns:
        오디오 파일의 바이트 데이터. 실패 시 빈 바이트.
    """
    try:
        # 1) getFile로 파일 경로 가져오기
        resp = requests.get(
            f"https://api.telegram.org/bot{bot_token}/getFile",
            params={"file_id": file_id},
            timeout=10,
        )
        if resp.status_code != 200:
            logger.error(f"텔레그램 getFile 실패: {resp.text}")
            return b""

        file_path = resp.json().get("result", {}).get("file_path", "")
        if not file_path:
            logger.error("파일 경로를 가져올 수 없습니다.")
            return b""

        # 2) 파일 다운로드
        download_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
        resp = requests.get(download_url, timeout=30)
        if resp.status_code != 200:
            logger.error(f"파일 다운로드 실패: {resp.status_code}")
            return b""

        logger.info(f"📥 음성 파일 다운로드 완료 ({len(resp.content)} bytes)")
        return resp.content

    except Exception as e:
        logger.error(f"음성 파일 다운로드 오류: {e}")
        return b""
