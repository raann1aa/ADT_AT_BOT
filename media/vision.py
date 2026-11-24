"""
Module C — Agricultural Image Intelligence Service.

Responsibilities:
- Accept a local image file path.
- Use Google Gemini Vision to identify crop, visible symptoms, and image quality.
- Return a structured VisualObservation with strict uncertainty flagging.
- Persist VisualObservation records linked to their MediaRecord.
- Never present a visual inference as a confirmed agronomic diagnosis.
- Handle blurry, non-agricultural, and ambiguous images gracefully.

Provider: Google Gemini (gemini-2.0-flash multimodal vision).
"""

import os
import json
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List

from database.connection import get_db_session
from database.models import MediaRecord, VisualObservation
from database.enums import MediaProcessingStatus

logger = logging.getLogger("AgriculturalVisionService")

SUPPORTED_IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024

VISION_PROMPT = """You are an agricultural image analysis assistant for Indian smallholder farmers.
Analyse this crop photograph and report ONLY what is visually observable.

STRICT RULES:
1. Report ONLY what you can clearly SEE in the image. Do NOT diagnose diseases from images alone.
2. If the image is blurry, poorly lit, or the crop is unidentifiable, say so explicitly.
3. Any possible disease or pest cause must be listed as UNCONFIRMED and requires physical verification.
4. Do NOT use the word "diagnosed" or "confirmed" for disease identification from an image.

Respond ONLY in this exact JSON format (no markdown):
{
  "identified_crop": "crop name or null if unknown",
  "leaf_discoloration": true/false,
  "yellowing": true/false,
  "spots_lesions": true/false,
  "wilting": true/false,
  "visible_pest_damage": true/false,
  "physical_damage": true/false,
  "general_condition": "NORMAL|STRESSED|SEVERE|POOR_VISIBILITY|UNIDENTIFIABLE",
  "observed_symptoms": ["list of visually observed symptom descriptions"],
  "image_quality": "GOOD|BLURRY|POOR_LIGHTING|LOW_RESOLUTION|NON_AGRICULTURAL",
  "confidence": 0.0 to 1.0,
  "uncertainty_notes": "explanation of what is uncertain",
  "additional_info_required": "what additional info is needed for a proper assessment",
  "recommended_action": "ANSWER|ESCALATE_AGRONOMIST|REQUEST_BETTER_IMAGE|NON_AGRICULTURAL",
  "possible_diagnoses": [
    {"cause": "UNCONFIRMED: possible cause name", "caveat": "requires field verification"}
  ]
}"""


@dataclass
class VisionResult:
    """Structured vision analysis result."""
    success: bool
    media_id: str
    farmer_id: int
    identified_crop: Optional[str]
    symptoms: List[str]
    image_quality: str
    general_condition: str
    confidence: float
    uncertainty_notes: Optional[str]
    additional_info_required: Optional[str]
    recommended_action: str
    possible_diagnoses: List[dict]
    raw_flags: dict = field(default_factory=dict)
    provider: str = "gemini"
    model_used: Optional[str] = None
    error_message: Optional[str] = None
    observation_id: Optional[str] = None


class AgriculturalVisionService:
    """
    Analyses crop images using Gemini Vision to surface observable symptoms
    without overstepping into unconfirmed disease diagnosis.

    When GEMINI_API_KEY is not configured, returns a graceful UNAVAILABLE result.
    """

    def __init__(self):
        self._api_key = os.environ.get("GEMINI_API_KEY", "")
        self._model_name = "gemini-2.0-flash"
        self._genai = None
        if self._api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self._api_key)
                self._genai = genai
                logger.info("AgriculturalVisionService: Gemini Vision API configured.")
            except Exception as e:
                logger.warning(f"AgriculturalVisionService: Gemini SDK init failed: {e}")
        else:
            logger.warning(
                "AgriculturalVisionService: GEMINI_API_KEY not set. Vision analysis unavailable."
            )

    def analyse_image(
        self,
        image_path: str,
        media_record_id: int,
        media_id: str,
        farmer_id: int,
        frame_index: int = 0,
        frame_timestamp_sec: Optional[float] = None,
    ) -> VisionResult:
        """
        Analyse a crop image and persist a VisualObservation.

        Args:
            image_path: Local filesystem path to the image.
            media_record_id: DB PK of the parent MediaRecord.
            media_id: WhatsApp media ID for reference.
            farmer_id: DB PK of the farmer.
            frame_index: 0 for standalone images; >0 for video frames.
            frame_timestamp_sec: Original timestamp in source video (video frames only).

        Returns:
            VisionResult structured analysis.
        """
        path = Path(image_path)

        # Validation
        if not path.exists():
            return self._failed(media_id, farmer_id, f"Image file not found: {image_path}")

        if path.stat().st_size == 0:
            return self._failed(media_id, farmer_id, "Image file is empty.")

        if path.suffix.lower() not in SUPPORTED_IMAGE_TYPES:
            return self._failed(
                media_id, farmer_id,
                f"Unsupported image format '{path.suffix}'. Supported: {SUPPORTED_IMAGE_TYPES}"
            )

        if path.stat().st_size > MAX_IMAGE_BYTES:
            return self._failed(
                media_id, farmer_id,
                f"Image exceeds 10 MB limit: {path.stat().st_size} bytes."
            )

        if self._genai:
            result = self._analyse_with_gemini(path, media_id, farmer_id)
        else:
            result = VisionResult(
                success=False,
                media_id=media_id,
                farmer_id=farmer_id,
                identified_crop=None,
                symptoms=[],
                image_quality="UNKNOWN",
                general_condition="UNKNOWN",
                confidence=0.0,
                uncertainty_notes=None,
                additional_info_required=None,
                recommended_action="UNAVAILABLE",
                possible_diagnoses=[],
                provider="unavailable",
                error_message=(
                    "GEMINI_API_KEY not configured. Image received but analysis is unavailable. "
                    "Please describe your crop issue in text."
                ),
            )

        # Persist VisualObservation if analysis succeeded or even failed (for audit)
        obs_id = self._persist_observation(
            result=result,
            media_record_id=media_record_id,
            frame_index=frame_index,
            frame_timestamp_sec=frame_timestamp_sec,
        )
        result.observation_id = obs_id
        return result

    # ------------------------------------------------------------------
    # Provider
    # ------------------------------------------------------------------

    def _analyse_with_gemini(self, path: Path, media_id: str, farmer_id: int) -> VisionResult:
        """Call Gemini Vision with the image and parse structured output."""
        try:
            uploaded = self._genai.upload_file(str(path), mime_type=f"image/{path.suffix.lstrip('.').lower()}")
            model = self._genai.GenerativeModel(self._model_name)
            response = model.generate_content([VISION_PROMPT, uploaded])
            raw = response.text.strip()

            # Strip markdown fences
            if raw.startswith("```"):
                raw = raw.split("```")[-2].strip()
                if raw.startswith("json"):
                    raw = raw[4:].strip()

            data = json.loads(raw)

            symptoms = data.get("observed_symptoms", [])
            if not isinstance(symptoms, list):
                symptoms = []

            diagnoses = data.get("possible_diagnoses", [])
            if not isinstance(diagnoses, list):
                diagnoses = []

            result = VisionResult(
                success=True,
                media_id=media_id,
                farmer_id=farmer_id,
                identified_crop=data.get("identified_crop"),
                symptoms=symptoms,
                image_quality=data.get("image_quality", "GOOD"),
                general_condition=data.get("general_condition", "NORMAL"),
                confidence=float(data.get("confidence", 0.0)),
                uncertainty_notes=data.get("uncertainty_notes"),
                additional_info_required=data.get("additional_info_required"),
                recommended_action=data.get("recommended_action", "ANSWER"),
                possible_diagnoses=diagnoses,
                raw_flags={
                    "leaf_discoloration": data.get("leaf_discoloration", False),
                    "yellowing": data.get("yellowing", False),
                    "spots_lesions": data.get("spots_lesions", False),
                    "wilting": data.get("wilting", False),
                    "visible_pest_damage": data.get("visible_pest_damage", False),
                    "physical_damage": data.get("physical_damage", False),
                },
                provider="gemini",
                model_used=self._model_name,
            )
            logger.info(
                f"AgriculturalVisionService: Analysed {path.name} -> crop={result.identified_crop}, "
                f"quality={result.image_quality}, confidence={result.confidence:.2f}"
            )
            return result

        except Exception as e:
            logger.error(f"AgriculturalVisionService: Gemini Vision failed for {path.name}: {e}")
            return self._failed(media_id, farmer_id, f"Gemini Vision error: {e}", provider="gemini")

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist_observation(
        self,
        result: VisionResult,
        media_record_id: int,
        frame_index: int,
        frame_timestamp_sec: Optional[float],
    ) -> str:
        """Write a VisualObservation row to the database and return observation_id."""
        import json as _json
        obs_id = f"OBS-{uuid.uuid4().hex[:12].upper()}"
        with get_db_session() as session:
            obs = VisualObservation(
                observation_id=obs_id,
                media_record_id=media_record_id,
                frame_timestamp_sec=frame_timestamp_sec,
                frame_index=frame_index,
                identified_crop=result.identified_crop,
                leaf_discoloration=result.raw_flags.get("leaf_discoloration", False),
                yellowing=result.raw_flags.get("yellowing", False),
                spots_lesions=result.raw_flags.get("spots_lesions", False),
                wilting=result.raw_flags.get("wilting", False),
                visible_pest_damage=result.raw_flags.get("visible_pest_damage", False),
                physical_damage=result.raw_flags.get("physical_damage", False),
                general_condition=result.general_condition,
                observed_symptoms_json=_json.dumps(result.symptoms, ensure_ascii=False),
                image_quality=result.image_quality,
                confidence=result.confidence,
                uncertainty_notes=result.uncertainty_notes,
                additional_info_required=result.additional_info_required,
                recommended_action=result.recommended_action,
                possible_diagnoses_json=_json.dumps(result.possible_diagnoses, ensure_ascii=False),
            )
            session.add(obs)
            session.commit()
        logger.info(f"AgriculturalVisionService: Persisted observation {obs_id}.")
        return obs_id

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _failed(media_id: str, farmer_id: int, msg: str, provider: str = "offline") -> VisionResult:
        return VisionResult(
            success=False,
            media_id=media_id,
            farmer_id=farmer_id,
            identified_crop=None,
            symptoms=[],
            image_quality="UNKNOWN",
            general_condition="UNKNOWN",
            confidence=0.0,
            uncertainty_notes=None,
            additional_info_required=None,
            recommended_action="REQUEST_BETTER_IMAGE",
            possible_diagnoses=[],
            provider=provider,
            error_message=msg,
        )
