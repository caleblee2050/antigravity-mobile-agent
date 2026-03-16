#!/usr/bin/env python3
"""
안티그래비티 모바일 에이전트 — 음성 인식 모듈 (Whisper 기반)
로컬 Whisper 모델로 텔레그램 음성 메시지를 텍스트로 변환합니다.
완전 무료 — API 키 불필요.

사용법:
  from voice_transcriber import transcribe_audio, download_telegram_voice
  audio_bytes = download_telegram_voice(file_id, bot_token)
  text = transcribe_audio(audio_bytes)
"""

import os
import io
import tempfile
import logging
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

logger = logging.getLogger("voice_transcriber")

# Whisper 모델 설정
# tiny: 가장 빠름 (39M), base: 균형 (74M), small: 정확 (244M)
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")
_whisper_model = None


def _get_model():
    """Whisper 모델 싱글턴 로드 (첫 호출 시 다운로드)"""
    global _whisper_model
    if _whisper_model is None:
        try:
            from faster_whisper import WhisperModel
            logger.info(f"🔄 Whisper '{WHISPER_MODEL_SIZE}' 모델 로딩 중...")
            _whisper_model = WhisperModel(
                WHISPER_MODEL_SIZE,
                device="cpu",         # M4에서 CPU가 안정적
                compute_type="int8",  # 메모리 절약 + 빠른 추론
            )
            logger.info(f"✅ Whisper '{WHISPER_MODEL_SIZE}' 모델 로드 완료")
        except Exception as e:
            logger.error(f"Whisper 모델 로드 실패: {e}")
    return _whisper_model


def transcribe_audio(audio_bytes: bytes, language: str = "ko") -> str:
    """음성 데이터를 텍스트로 변환 (Whisper 로컬)

    Args:
        audio_bytes: OGG/OGA 형식의 오디오 바이트 데이터
        language: 인식 언어 코드 (기본: "ko" 한국어)

    Returns:
        인식된 텍스트. 실패 시 빈 문자열.
    """
    if not audio_bytes:
        logger.error("빈 오디오 데이터입니다.")
        return ""

    model = _get_model()
    if model is None:
        logger.error("Whisper 모델을 사용할 수 없습니다.")
        return ""

    try:
        # 임시 파일에 오디오 저장 (faster-whisper는 파일 경로 필요)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        # Whisper 음성 인식 실행
        segments, info = model.transcribe(
            tmp_path,
            language=language,
            beam_size=5,
            vad_filter=True,  # 묵음 자동 제거
        )

        # 세그먼트를 텍스트로 합치기
        transcripts = [segment.text.strip() for segment in segments]
        full_text = " ".join(transcripts).strip()

        # 임시 파일 삭제
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

        if full_text:
            logger.info(f"🎤 음성 인식 완료 ({info.language}, {info.duration:.1f}초): {full_text[:80]}...")
        else:
            logger.warning("음성 인식 결과가 없습니다 (묵음이거나 인식 불가).")

        return full_text

    except Exception as e:
        logger.error(f"STT 처리 오류: {e}")
        # 임시 파일 정리
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
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


# ─── CLI 테스트 ───────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) > 1:
        # 파일 경로로 테스트
        audio_path = sys.argv[1]
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()
        print(f"📂 파일: {audio_path} ({len(audio_bytes):,} bytes)")
        result = transcribe_audio(audio_bytes)
        if result:
            print(f"✅ 인식 결과: {result}")
        else:
            print("❌ 인식 실패")
    else:
        print("사용법: python voice_transcriber.py <오디오파일.ogg>")
        print("Whisper 모델 로드 테스트...")
        model = _get_model()
        if model:
            print(f"✅ Whisper '{WHISPER_MODEL_SIZE}' 모델 준비 완료")
        else:
            print("❌ 모델 로드 실패")
