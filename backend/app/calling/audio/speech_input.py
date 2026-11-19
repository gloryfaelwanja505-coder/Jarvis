from collections.abc import Callable

from app.config import Settings


class SpeechInputUnavailable(RuntimeError):
    pass


class WhisperSpeechInput:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model: object | None = None

    def transcribe(self, pcm_s16le: bytes) -> str:
        if not pcm_s16le:
            return ""
        if self._model is None:
            try:
                import numpy as np
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise SpeechInputUnavailable(
                    "Install faster-whisper and numpy to enable local Whisper speech input."
                ) from exc
            self._model = WhisperModel(
                self.settings.whisper_model_size,
                device="cpu",
                compute_type="int8",
            )
        import numpy as np

        audio = np.frombuffer(pcm_s16le, dtype=np.int16).astype(np.float32) / 32768.0
        transcribe: Callable[..., tuple[object, object]] = getattr(self._model, "transcribe")
        segments, _ = transcribe(audio, language="en", vad_filter=True)
        return " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
