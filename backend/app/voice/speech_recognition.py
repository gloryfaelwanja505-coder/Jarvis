import json
from pathlib import Path

from app.config import Settings
from app.calling.audio.speech_input import SpeechInputUnavailable, WhisperSpeechInput


class SpeechRecognition:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._vosk_model = None
        self._whisper = WhisperSpeechInput(settings)

    @property
    def available(self) -> bool:
        try:
            from importlib.util import find_spec

            if self.settings.speech_recognition_provider == "vosk":
                return (
                    find_spec("vosk") is not None
                    and self.settings.vosk_model_path is not None
                    and self.settings.vosk_model_path.is_dir()
                )
            if self.settings.speech_recognition_provider == "whisper":
                return (
                    find_spec("faster_whisper") is not None
                    and find_spec("numpy") is not None
                )
        except (ImportError, ValueError):
            return False
        return False

    def transcribe(self, pcm_s16le: bytes, sample_rate: int = 16_000) -> str:
        if not pcm_s16le or len(pcm_s16le) % 2:
            raise ValueError("Provide non-empty 16-bit PCM audio.")
        if not 8_000 <= sample_rate <= 48_000:
            raise ValueError("Sample rate must be between 8000 and 48000 Hz.")
        if self.settings.speech_recognition_provider == "whisper":
            if sample_rate != 16_000:
                raise ValueError("Whisper voice capture requires 16 kHz PCM.")
            return self._whisper.transcribe(pcm_s16le)
        if self.settings.speech_recognition_provider != "vosk":
            raise SpeechInputUnavailable("The configured speech recognizer is unsupported.")
        model_path: Path | None = self.settings.vosk_model_path
        if model_path is None or not model_path.is_dir():
            raise SpeechInputUnavailable("Configure a local Vosk model directory.")
        try:
            from vosk import KaldiRecognizer, Model, SetLogLevel  # pyright: ignore[reportMissingImports]
        except ImportError as exc:
            raise SpeechInputUnavailable("Install the optional Vosk voice dependencies.") from exc
        if self._vosk_model is None:
            SetLogLevel(-1)
            self._vosk_model = Model(str(model_path))
        recognizer = KaldiRecognizer(self._vosk_model, sample_rate)
        recognizer.AcceptWaveform(pcm_s16le)
        result = json.loads(recognizer.FinalResult())
        text = result.get("text", "") if isinstance(result, dict) else ""
        if not isinstance(text, str):
            raise SpeechInputUnavailable("Vosk returned an invalid transcript.")
        return text.strip()
