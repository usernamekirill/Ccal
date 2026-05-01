from pathlib import Path

from openai import AsyncOpenAI

from calorie_bot.app.config import Settings


class SpeechToTextService:
    """Transcribe Telegram voice messages through an external speech-to-text API."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=settings.openai_timeout_seconds,
        )

    async def transcribe(self, audio_path: Path) -> str:
        """Return transcript text for a local audio file."""
        try:
            with audio_path.open("rb") as audio_file:
                transcript = await self._client.audio.transcriptions.create(
                    model=self._settings.openai_speech_model,
                    file=audio_file,
                )
        except Exception as exc:
            from calorie_bot.app.utils.openai_errors import translate_openai_exception

            raise translate_openai_exception(exc) from None
        return transcript.text
