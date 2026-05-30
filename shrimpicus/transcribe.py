from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class Transcriber:
    def __init__(self, enabled: bool, model_name: str):
        self.enabled = enabled
        self.model_name = model_name
        self._model = None
        self._load_failed = False

    def _ensure_model(self) -> bool:
        if self._model is not None:
            return True
        if self._load_failed:
            return False
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            logger.warning("faster-whisper not installed; voice transcription disabled. Install with `pip install -e .[voice]`.")
            self._load_failed = True
            return False
        try:
            self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
        except Exception:
            logger.exception("Failed to load whisper model %r", self.model_name)
            self._load_failed = True
            return False
        return True

    async def transcribe_bytes(self, audio: bytes, suffix: str = ".ogg") -> str | None:
        if not self.enabled:
            return None
        return await asyncio.to_thread(self._transcribe_sync, audio, suffix)

    def _transcribe_sync(self, audio: bytes, suffix: str) -> str | None:
        if not self._ensure_model():
            return None
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
            tmp.write(audio)
            tmp.flush()
            segments, _ = self._model.transcribe(tmp.name, beam_size=1)
            return "".join(seg.text for seg in segments).strip() or None
