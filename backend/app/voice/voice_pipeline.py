from app.calling.audio.voice_activity import VoiceActivityDetector
from app.voice.audio_manager import AudioManager


class VoicePipeline:
    def __init__(self, audio: AudioManager) -> None:
        self.audio = audio

    def transcribe(self, pcm_s16le: bytes, sample_rate: int) -> str:
        detector = VoiceActivityDetector(sample_rate=sample_rate)
        speech = detector.process(pcm_s16le)
        if speech is None:
            speech = detector.flush()
        if speech is None:
            return ""
        return self.audio.recognition.transcribe(speech, sample_rate)
