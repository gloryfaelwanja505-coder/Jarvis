import asyncio
from pathlib import Path
import tempfile
import wave

from app.config import Settings


class SpeechOutputUnavailable(RuntimeError):
    pass


class PiperSpeechOutput:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def synthesize(self, text: str) -> tuple[bytes, int]:
        if not text.strip():
            raise ValueError("Speech text cannot be empty.")
        model = self.settings.piper_model_path
        if model is None or not model.is_file():
            raise SpeechOutputUnavailable("Configure a Piper voice model to enable speech output.")

        with tempfile.TemporaryDirectory(prefix="jarvis-piper-") as directory:
            output_path = Path(directory) / "speech.wav"
            try:
                process = await asyncio.create_subprocess_exec(
                    self.settings.piper_binary,
                    "--model",
                    str(model),
                    "--length_scale",
                    str(self.settings.piper_length_scale),
                    "--output_file",
                    str(output_path),
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    _, stderr = await asyncio.wait_for(
                        process.communicate(text.strip().encode("utf-8")),
                        timeout=30,
                    )
                except TimeoutError as exc:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                    await process.wait()
                    raise SpeechOutputUnavailable("Piper speech synthesis timed out.") from exc
                except asyncio.CancelledError:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                    await process.wait()
                    raise
            except OSError as exc:
                raise SpeechOutputUnavailable("Piper could not synthesize speech.") from exc
            if process.returncode != 0:
                raise SpeechOutputUnavailable(
                    f"Piper exited with status {process.returncode}: "
                    f"{stderr.decode('utf-8', errors='replace')[:300]}"
                )
            try:
                with wave.open(str(output_path), "rb") as audio:
                    if audio.getnchannels() != 1 or audio.getsampwidth() != 2:
                        raise SpeechOutputUnavailable("Piper must return mono 16-bit PCM.")
                    return audio.readframes(audio.getnframes()), audio.getframerate()
            except (OSError, wave.Error) as exc:
                raise SpeechOutputUnavailable("Piper returned invalid WAV data.") from exc
