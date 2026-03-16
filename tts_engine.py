#!/usr/bin/env python3
"""
안티그래비티 AI 음성 비서 — TTS 엔진 모듈

3개 TTS 엔진을 지원하는 통합 모듈:
  1. edge-tts (기본) — 무료, 설치 간편, 품질 양호
  2. Google Cloud TTS — 고품질, API 키 필요
  3. Qwen3-TTS (프리미엄) — 음성 복제, 로컬 GPU 필요

Usage:
    from tts_engine import get_tts_engine
    engine = get_tts_engine()  # 사용 가능한 최적 엔진 자동 선택
    audio_bytes = engine.synthesize("안녕하세요, 안티그래비티입니다.")
"""

import io
import os
import json
import logging
import tempfile
import asyncio
from abc import ABC, abstractmethod

logger = logging.getLogger("tts_engine")


class TTSEngine(ABC):
    """TTS 엔진 추상 클래스"""

    @abstractmethod
    def synthesize(self, text: str, voice: str = None) -> bytes | None:
        """텍스트를 음성으로 변환, OGG/MP3 바이트 반환"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """이 엔진이 사용 가능한지 확인"""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass


class EdgeTTSEngine(TTSEngine):
    """Microsoft Edge TTS — 무료, 설치 간편"""

    # 한국어 기본 음성
    DEFAULT_VOICE = "ko-KR-SunHiNeural"
    ALTERNATIVE_VOICES = {
        "female": "ko-KR-SunHiNeural",
        "male": "ko-KR-InJoonNeural",
    }

    @property
    def name(self) -> str:
        return "edge-tts"

    def is_available(self) -> bool:
        try:
            import edge_tts
            return True
        except ImportError:
            return False

    def synthesize(self, text: str, voice: str = None) -> bytes | None:
        """edge-tts로 음성 합성"""
        try:
            import edge_tts

            voice = voice or self.DEFAULT_VOICE
            # edge_tts는 async이므로 동기 래핑
            return asyncio.get_event_loop().run_until_complete(
                self._async_synthesize(text, voice)
            )
        except RuntimeError:
            # 이벤트 루프가 이미 실행 중인 경우
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(self._async_synthesize(text, voice))
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"edge-tts 합성 실패: {e}")
            return None

    async def _async_synthesize(self, text: str, voice: str) -> bytes | None:
        """비동기 edge-tts 합성"""
        import edge_tts

        communicate = edge_tts.Communicate(text, voice)
        audio_data = io.BytesIO()

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data.write(chunk["data"])

        result = audio_data.getvalue()
        if not result:
            return None
        return result


class GoogleCloudTTSEngine(TTSEngine):
    """Google Cloud Text-to-Speech — 고품질"""

    DEFAULT_VOICE = "ko-KR-Neural2-A"  # 여성 Neural2 (고품질)
    ALTERNATIVE_VOICES = {
        "female": "ko-KR-Neural2-A",
        "male": "ko-KR-Neural2-C",
        "standard_female": "ko-KR-Standard-A",
        "standard_male": "ko-KR-Standard-C",
    }

    def __init__(self):
        self.api_key = os.getenv("GOOGLE_CLOUD_API_KEY", "")

    @property
    def name(self) -> str:
        return "google-cloud-tts"

    def is_available(self) -> bool:
        return bool(self.api_key)

    def synthesize(self, text: str, voice: str = None) -> bytes | None:
        """Google Cloud TTS REST API로 음성 합성"""
        import requests

        voice_name = voice or self.DEFAULT_VOICE

        url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={self.api_key}"

        payload = {
            "input": {"text": text},
            "voice": {
                "languageCode": "ko-KR",
                "name": voice_name,
            },
            "audioConfig": {
                "audioEncoding": "OGG_OPUS",  # 텔레그램 호환
                "speakingRate": 1.0,
                "pitch": 0.0,
            },
        }

        try:
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                audio_content = data.get("audioContent", "")
                if audio_content:
                    import base64
                    return base64.b64decode(audio_content)
                logger.error("Google TTS: audioContent 비어있음")
                return None
            else:
                logger.error(f"Google TTS API 오류 {resp.status_code}: {resp.text[:200]}")
                return None
        except Exception as e:
            logger.error(f"Google TTS 합성 실패: {e}")
            return None


# ─── 엔진 팩토리 ──────────────────────────────────────

# 엔진 우선순위: Google Cloud > edge-tts
_ENGINE_CLASSES = [GoogleCloudTTSEngine, EdgeTTSEngine]


def get_tts_engine(preferred: str = None) -> TTSEngine | None:
    """사용 가능한 TTS 엔진 반환

    Args:
        preferred: 선호 엔진 이름 ("google-cloud-tts", "edge-tts")

    Returns:
        TTSEngine 인스턴스 또는 None
    """
    # 선호 엔진이 지정된 경우
    if preferred:
        for cls in _ENGINE_CLASSES:
            engine = cls()
            if engine.name == preferred and engine.is_available():
                logger.info(f"🔊 TTS 엔진 선택: {engine.name}")
                return engine

    # 자동 선택: 우선순위 순
    for cls in _ENGINE_CLASSES:
        engine = cls()
        if engine.is_available():
            logger.info(f"🔊 TTS 엔진 자동 선택: {engine.name}")
            return engine

    logger.warning("⚠️ 사용 가능한 TTS 엔진이 없습니다.")
    return None


def list_available_engines() -> list[dict]:
    """사용 가능한 TTS 엔진 목록 반환"""
    result = []
    for cls in _ENGINE_CLASSES:
        engine = cls()
        result.append({
            "name": engine.name,
            "available": engine.is_available(),
        })
    return result


# ─── CLI 테스트 ───────────────────────────────────────

if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

    logging.basicConfig(level=logging.INFO)

    text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "안녕하세요, 안티그래비티입니다."

    print(f"🔍 사용 가능한 엔진: {list_available_engines()}")

    engine = get_tts_engine()
    if not engine:
        print("❌ 사용 가능한 TTS 엔진이 없습니다. edge-tts를 설치하세요: pip install edge-tts")
        sys.exit(1)

    print(f"🔊 엔진: {engine.name}")
    print(f"📝 텍스트: {text}")

    audio = engine.synthesize(text)
    if audio:
        out_file = "/tmp/tts_test_output.ogg"
        with open(out_file, "wb") as f:
            f.write(audio)
        print(f"✅ 음성 파일 생성: {out_file} ({len(audio)} bytes)")
        print(f"🎧 재생: open {out_file}")
    else:
        print("❌ 음성 합성 실패")
