from pathlib import Path


class WakeWordUnavailable(RuntimeError):
    pass


class WakeWordDetector:
    def __init__(self, model_path: Path | None, phrase: str = "JARVIS") -> None:
        self.model_path = model_path
        self.phrase = phrase
        self._model = None

    @property
    def available(self) -> bool:
        if self.model_path is None or not self.model_path.is_file():
            return False
        try:
            from importlib.util import find_spec

            return find_spec("openwakeword") is not None
        except (ImportError, ValueError):
            return False

    def detect(self, pcm_s16le: bytes) -> bool:
        if not self.available or self.model_path is None:
            raise WakeWordUnavailable(
                "Install openWakeWord and configure a local wake-word model."
            )
        if self._model is None:
            from openwakeword.model import Model

            self._model = Model(wakeword_models=[str(self.model_path)])
        import numpy as np

        scores = self._model.predict(np.frombuffer(pcm_s16le, dtype=np.int16))
        return any(float(score) >= 0.5 for score in scores.values())
