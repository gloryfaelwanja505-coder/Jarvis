from array import array
import math


class VoiceActivityDetector:
    def __init__(
        self,
        sample_rate: int = 16_000,
        threshold: float = 0.018,
        silence_seconds: float = 0.8,
        minimum_speech_seconds: float = 0.25,
        maximum_speech_seconds: float = 30,
    ) -> None:
        if (
            sample_rate <= 0
            or threshold <= 0
            or silence_seconds <= 0
            or maximum_speech_seconds <= 0
        ):
            raise ValueError("Voice activity settings must be positive.")
        self.sample_rate = sample_rate
        self.threshold = threshold
        self.silence_samples = int(sample_rate * silence_seconds)
        self.minimum_speech_samples = int(sample_rate * minimum_speech_seconds)
        self.maximum_speech_samples = int(sample_rate * maximum_speech_seconds)
        self._speech = bytearray()
        self._quiet_samples = 0

    def process(self, pcm_s16le: bytes) -> bytes | None:
        if len(pcm_s16le) % 2:
            raise ValueError("PCM audio must contain complete 16-bit samples.")
        samples = array("h")
        samples.frombytes(pcm_s16le)
        if not samples:
            return None
        if samples.itemsize != 2:
            raise RuntimeError("The host does not support 16-bit PCM samples.")
        rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples)) / 32768
        if rms >= self.threshold:
            self._speech.extend(pcm_s16le)
            self._quiet_samples = 0
            if len(self._speech) // 2 >= self.maximum_speech_samples:
                speech = bytes(self._speech)
                self._speech.clear()
                return speech
        elif self._speech:
            self._speech.extend(pcm_s16le)
            self._quiet_samples += len(samples)
            if self._quiet_samples >= self.silence_samples:
                speech = bytes(self._speech)
                self._speech.clear()
                self._quiet_samples = 0
                if len(speech) // 2 >= self.minimum_speech_samples:
                    return speech
        return None

    def flush(self) -> bytes | None:
        speech = bytes(self._speech)
        self._speech.clear()
        self._quiet_samples = 0
        if len(speech) // 2 >= self.minimum_speech_samples:
            return speech
        return None
