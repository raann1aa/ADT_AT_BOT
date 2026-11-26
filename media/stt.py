"""
Module B — Multilingual Speech-to-Text Service.

Responsibilities:
- Accept a local audio file path.
- Transcribe Marathi, Hindi, English, or mixed-language voice notes.
- Use Google Gemini (gemini-2.0-flash) as the primary transcription provider.
- When no API key is configured, return a clearly-flagged UNAVAILABLE result.
- Preserve the original audio reference and language metadata.
- Never fabricate words when speech is unclear.
- Flag low-confidence or partial transcriptions explicitly.

Provider Strategy:
  Primary:  Google Gemini multimodal (audio inline upload via Gemini File API)
  Fallback: SoundFile + heuristic "audio received but no model configured" message.
"""

import os
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("SpeechToTextService")

SUPPORTED_AUDIO_MIME = {
    ".ogg": "audio/ogg",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".wav": "audio/wav",
    ".aac": "audio/aac",
    ".amr": "audio/amr",
    ".webm": "audio/webm",
}

MAX_AUDIO_DURATION_SEC = 300  # 5 minutes limit for transcription


@dataclass
class TranscriptionResult:
    """Structured transcription output with metadata and provenance flags."""
    success: bool
    transcription: Optional[str]
    detected_language: Optional[str]       # e.g. 'mr' (Marathi), 'hi', 'en', 'mixed'
    confidence: Optional[float]            # 0.0–1.0 if available, else None
    provider: str                          # 'gemini' | 'offline' | 'unavailable'
    is_unclear: bool = False               # True if speech was noisy/incomplete
    is_mixed_language: bool = False        # True if Marathi+Hindi mix detected
    error_message: Optional[str] = None
    model_used: Optional[str] = None
    audio_duration_sec: Optional[float] = None
    warnings: list = field(default_factory=list)
    retryable: bool = False


class SpeechToTextService:
    """
    Multilingual Speech-to-Text using Google Gemini.

    When GEMINI_API_KEY is configured, uses Gemini's multimodal capability to
    transcribe audio inline and detect language. When the key is absent (offline /
    development), returns a graceful UNAVAILABLE result with no fabricated words.

    Design rules:
      - Never invent words when audio is unclear.
      - Always mark low-quality / partial transcriptions explicitly.
      - Return structured TranscriptionResult, never bare strings.
      - Mixed Marathi-Hindi-English (Marathlish / Hinglish) is handled as 'mixed'.
    """

    SUPPORTED_LANGUAGES = ["mr", "hi", "en", "mixed"]

    # Gemini prompt used for transcription — explicitly asks for no fabrication
    TRANSCRIPTION_PROMPT = """You are a multilingual agricultural transcription assistant.
Transcribe this audio recording from a WhatsApp farmer voice note exactly as spoken.

IMPORTANT RULES:
1. Transcribe word-for-word without paraphrasing or summarizing.
2. If the recording is in Marathi (mr), Hindi (hi), English (en), or a mix of these (mixed), transcribe faithfully in that language using the original script.
3. If a word is unclear or inaudible, write [unclear] in its place. NEVER guess or invent words.
4. If the entire audio is silent, too noisy, or unintelligible, respond: TRANSCRIPTION_FAILED: reason
5. Identify the primary language of the audio.

Respond ONLY in this exact JSON format (no markdown, no extra text):
{
  "transcription": "exact text here",
  "detected_language": "mr|hi|en|mixed",
  "confidence": 0.0 to 1.0,
  "is_unclear": true/false,
  "is_mixed_language": true/false,
  "warnings": []
}"""

    def __init__(self):
        self._api_key = os.environ.get("GEMINI_API_KEY", "")
        self._model_name = "gemini-2.0-flash"
        self._genai = None
        if self._api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self._api_key)
                self._genai = genai
                logger.info("SpeechToTextService: Gemini API configured for live transcription.")
            except Exception as e:
                logger.warning(f"SpeechToTextService: Gemini SDK init failed: {e}")
        else:
            logger.warning(
                "SpeechToTextService: GEMINI_API_KEY not set. "
                "Transcription will return UNAVAILABLE result."
            )

    def transcribe(self, audio_path: str) -> TranscriptionResult:
        """
        Transcribe an audio file.

        Args:
            audio_path: Absolute or relative path to the audio file.

        Returns:
            TranscriptionResult — always populated, never raises.
        """
        path = Path(audio_path)
        if not path.exists():
            return TranscriptionResult(
                success=False,
                transcription=None,
                detected_language=None,
                confidence=None,
                provider="offline",
                error_message=f"Audio file not found: {audio_path}",
            )

        file_size = path.stat().st_size
        if file_size == 0:
            return TranscriptionResult(
                success=False,
                transcription=None,
                detected_language=None,
                confidence=None,
                provider="offline",
                is_unclear=True,
                error_message="Audio file is empty (0 bytes).",
            )

        ext = path.suffix.lower()
        if ext not in SUPPORTED_AUDIO_MIME:
            return TranscriptionResult(
                success=False,
                transcription=None,
                detected_language=None,
                confidence=None,
                provider="offline",
                error_message=f"Unsupported audio format '{ext}'. Supported: {list(SUPPORTED_AUDIO_MIME.keys())}",
            )

        # Duration estimate for validation (requires soundfile for WAV)
        duration_sec = self._estimate_duration(path)
        if duration_sec is not None and duration_sec > MAX_AUDIO_DURATION_SEC:
            return TranscriptionResult(
                success=False,
                transcription=None,
                detected_language=None,
                confidence=None,
                provider="offline",
                audio_duration_sec=duration_sec,
                error_message=f"Audio too long: {duration_sec:.1f}s > {MAX_AUDIO_DURATION_SEC}s limit.",
            )

        # Live Gemini transcription
        if self._genai:
            return self._transcribe_with_gemini(path, duration_sec)

        # Fallback: no model configured
        return TranscriptionResult(
            success=False,
            transcription=None,
            detected_language=None,
            confidence=None,
            provider="unavailable",
            audio_duration_sec=duration_sec,
            error_message=(
                "GEMINI_API_KEY not configured. Voice note received but transcription is unavailable. "
                "Please send your query as a text message."
            ),
            retryable=True,
        )

    # ------------------------------------------------------------------
    # Provider Implementations
    # ------------------------------------------------------------------

    def _transcribe_with_gemini(self, path: Path, duration_sec: Optional[float]) -> TranscriptionResult:
        """Upload audio to Gemini and request structured transcription."""
        import json

        mime_type = SUPPORTED_AUDIO_MIME.get(path.suffix.lower(), "audio/ogg")
        try:
            # Upload via Gemini File API
            uploaded_file = self._genai.upload_file(str(path), mime_type=mime_type)
            model = self._genai.GenerativeModel(self._model_name)
            response = model.generate_content([self.TRANSCRIPTION_PROMPT, uploaded_file])
            raw_text = response.text.strip()

            # Remove markdown fences if present
            if raw_text.startswith("```"):
                raw_text = raw_text.split("```")[-2].strip()
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:].strip()

            if raw_text.startswith("TRANSCRIPTION_FAILED"):
                reason = raw_text.replace("TRANSCRIPTION_FAILED:", "").strip()
                return TranscriptionResult(
                    success=False,
                    transcription=None,
                    detected_language=None,
                    confidence=None,
                    provider="gemini",
                    model_used=self._model_name,
                    is_unclear=True,
                    audio_duration_sec=duration_sec,
                    error_message=f"Gemini could not transcribe: {reason}",
                )

            data = json.loads(raw_text)
            if not isinstance(data, dict):
                raise ValueError("Gemini returned a non-object transcription response.")
            required_fields = {
                "transcription",
                "detected_language",
                "confidence",
                "is_unclear",
                "is_mixed_language",
                "warnings",
            }
            if not required_fields.issubset(data):
                raise ValueError("Gemini returned an incomplete transcription response.")
            if not isinstance(data["transcription"], str):
                raise ValueError("Gemini returned malformed transcription text.")
            transcription = data["transcription"].strip()
            confidence_value = data["confidence"]
            if isinstance(confidence_value, bool) or not isinstance(confidence_value, (int, float)):
                raise ValueError("Gemini returned malformed transcription confidence.")
            confidence = float(confidence_value)
            detected_lang = data["detected_language"]
            if not transcription or detected_lang not in self.SUPPORTED_LANGUAGES:
                raise ValueError("Gemini returned an incomplete transcription response.")
            if not 0.0 <= confidence <= 1.0:
                raise ValueError("Gemini returned confidence outside the 0.0-1.0 range.")
            if not isinstance(data["is_unclear"], bool) or not isinstance(data["is_mixed_language"], bool):
                raise ValueError("Gemini returned malformed transcription flags.")
            is_unclear = data["is_unclear"] or "[unclear]" in transcription
            is_mixed = data["is_mixed_language"]
            warnings = data["warnings"]
            if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
                raise ValueError("Gemini returned malformed transcription warnings.")

            logger.info(
                f"SpeechToTextService: Transcribed {path.name} -> lang={detected_lang}, "
                f"confidence={confidence:.2f}, unclear={is_unclear}"
            )

            return TranscriptionResult(
                success=True,
                transcription=transcription,
                detected_language=detected_lang,
                confidence=confidence,
                provider="gemini",
                model_used=self._model_name,
                is_unclear=is_unclear,
                is_mixed_language=is_mixed,
                audio_duration_sec=duration_sec,
                warnings=warnings,
            )

        except Exception as e:
            logger.error(f"SpeechToTextService: Gemini transcription failed for {path.name}: {e}")
            return TranscriptionResult(
                success=False,
                transcription=None,
                detected_language=None,
                confidence=None,
                provider="gemini",
                model_used=self._model_name,
                audio_duration_sec=duration_sec,
                error_message=f"Gemini API error: {e}",
                retryable=True,
            )

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_duration(path: Path) -> Optional[float]:
        """Return duration in seconds for WAV files using soundfile; None otherwise."""
        if path.suffix.lower() == ".wav":
            try:
                import soundfile as sf
                info = sf.info(str(path))
                return info.duration
            except Exception:
                pass
        return None
