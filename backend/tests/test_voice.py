from array import array

from app.config import Settings
from app.voice.audio_manager import AudioManager
from app.voice.speech_queue import SpeechQueue
from app.voice.voice_pipeline import VoicePipeline
from app.voice.speech_recognition import SpeechRecognition


def test_voice_pipeline_sends_audio_to_local_recognizer() -> None:
    settings = Settings(_env_file=None)
    manager = AudioManager(settings)
    observed = {}

    def transcribe(audio: bytes, sample_rate: int) -> str:
        observed["audio"] = audio
        observed["sample_rate"] = sample_rate
        return "hello jarvis"

    manager.recognition.transcribe = transcribe
    samples = array("h", [5000] * 6400 + [0] * 12800)
    result = VoicePipeline(manager).transcribe(samples.tobytes(), 16_000)

    assert result == "hello jarvis"
    assert observed["sample_rate"] == 16_000
    assert observed["audio"]


def test_speech_queue_serializes_and_interrupts_speech() -> None:
    import asyncio

    async def verify() -> None:
        queue = SpeechQueue()
        started = asyncio.Event()

        async def speak() -> None:
            started.set()
            await asyncio.sleep(10)

        task = asyncio.create_task(queue.play(speak))
        await started.wait()
        assert await queue.interrupt() is True
        assert task.cancelled()

    asyncio.run(verify())


def test_vosk_is_optional_without_a_local_model() -> None:
    recognizer = SpeechRecognition(Settings(_env_file=None))
    assert recognizer.available is False


def test_default_wake_word_phrase_is_configured() -> None:
    manager = AudioManager(Settings(_env_file=None))
    assert manager.status()["wake_word_phrase"] == "Hello JARVIS Scott here"
    assert manager.status()["wake_word_listening"] is False
