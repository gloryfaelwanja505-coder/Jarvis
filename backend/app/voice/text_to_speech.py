from app.calling.audio.speech_output import PiperSpeechOutput
from app.config import Settings


class TextToSpeech:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.piper = PiperSpeechOutput(settings)

    @property
    def available(self) -> bool:
        from shutil import which

        model = self.settings.piper_model_path
        return which(self.settings.piper_binary) is not None and model is not None and model.is_file()

    async def synthesize(self, text: str) -> tuple[bytes, int]:
        return await self.piper.synthesize(text)
