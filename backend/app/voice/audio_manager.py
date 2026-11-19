import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.config import Settings
from app.voice.microphone import MicrophoneStatus
from app.voice.speech_recognition import SpeechRecognition
from app.voice.wake_word import WakeWordDetector

Result = TypeVar("Result")


class AudioManager:
    def __init__(self, settings: Settings) -> None:
        self.microphone = MicrophoneStatus()
        self.recognition = SpeechRecognition(settings)
        self.wake_word = WakeWordDetector(
            settings.wake_word_model_path,
            settings.wake_word_phrase,
        )
        self._speech_lock = asyncio.Lock()
        self._speech_task: asyncio.Task[None] | None = None
        self.wake_word_listening = False

    def status(self) -> dict[str, object]:
        missing_voice_features = []
        if not self.recognition.available:
            missing_voice_features.append("local speech recognition model")
        if not self.wake_word.available:
            missing_voice_features.append("openWakeWord model and runtime")
        return {
            "microphone_active": self.microphone.active,
            "capture_requires_user_activation": True,
            "speech_recognition_provider": self.recognition.settings.speech_recognition_provider,
            "speech_recognition_available": self.recognition.available,
            "wake_word_phrase": self.wake_word.phrase,
            "wake_word_available": self.wake_word.available,
            "wake_word_listening": self.wake_word_listening,
            "background_listening_available": not missing_voice_features,
            "background_listening_reason": (
                "Ready"
                if not missing_voice_features
                else f"Configure {', '.join(missing_voice_features)}."
            ),
        }

    async def speak(self, callback: Callable[[], Awaitable[Result]]) -> Result:
        async with self._speech_lock:
            self._speech_task = asyncio.current_task()
            try:
                return await callback()
            finally:
                self._speech_task = None

    async def interrupt_speech(self) -> bool:
        task = self._speech_task
        if task is None or task is asyncio.current_task():
            return False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return True
        return False
