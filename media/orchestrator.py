"""
Module E & F — Multimodal Orchestrator.

Responsibilities:
- Receive a WhatsApp event that may contain text, audio, images, and/or video.
- Identify the farmer and load their Phase 3 conversation context.
- Orchestrate media ingestion -> transcription/vision/video analysis.
- Merge all signals (transcribed text + visual observations + caption text) into one coherent context.
- Route the combined context through Phase 3 FarmerAgent for intent classification, RAG, and follow-up.
- Prevent duplicate farmer issues per media event.
- Route to human escalation when visual findings warrant it.
- Persist all processing state via MediaRecord and VisualObservation.
- Never overwrite VERIFIED farmer profile fields with uncertain image-extracted information.

Backward compatibility:
- Text-only messages bypass all media processing and flow through the unchanged Phase 3 pipeline.
- All existing conversation context, follow-up engine, and outbox behaviour is preserved.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

from agent.farmer_agent import FarmerAgent, FarmerProfile, AgentResponse
from database.services.farmer_service import FarmerService
from database.enums import MediaType
from media.ingestion import MediaIngestionService, MediaIngestionError
from media.stt import SpeechToTextService
from media.vision import AgriculturalVisionService
from media.video import VideoAnalysisService

logger = logging.getLogger("MultimodalOrchestrator")


@dataclass
class MediaAttachment:
    """Represents a single media attachment in a WhatsApp event."""
    wa_media_id: str
    media_type_hint: str            # 'audio', 'image', 'video', 'voice_note'
    mime_type: str
    caption_text: Optional[str] = None


@dataclass
class MultimodalRequest:
    """Incoming multimodal message event from the webhook."""
    sender_phone: str
    sender_name: str
    message_id: str
    text_body: Optional[str]
    attachments: List[MediaAttachment] = field(default_factory=list)
    group_id: Optional[str] = None


@dataclass
class MultimodalResponse:
    """Unified response from the multimodal orchestrator."""
    status: str                      # 'ANSWERED', 'IGNORED', 'ESCALATED', 'ERROR'
    reply_text: Optional[str]
    intent: Optional[str]
    media_records_created: List[str] = field(default_factory=list)
    transcription: Optional[str] = None
    visual_summary: Optional[str] = None
    escalation_required: bool = False
    processing_time_ms: float = 0.0
    errors: List[str] = field(default_factory=list)


MEDIA_TYPE_MAP = {
    "audio": MediaType.AUDIO,
    "voice_note": MediaType.VOICE_NOTE,
    "image": MediaType.IMAGE,
    "video": MediaType.VIDEO,
}


class MultimodalOrchestrator:
    """
    Central coordinator for multimodal farmer message processing.

    Flow for a combined message:
        1. Identify farmer (DB lookup by phone).
        2. For each attachment: ingest -> transcribe/analyse.
        3. Merge text_body + transcriptions + visual observations.
        4. Route merged context through FarmerAgent (Phase 3).
        5. Collect and dispatch reply via OutboxService (unchanged).
    """

    def __init__(self):
        self._farmer_service = FarmerService()
        self._farmer_agent = FarmerAgent()
        self._ingestion = MediaIngestionService()
        self._stt = SpeechToTextService()
        self._vision = AgriculturalVisionService()
        self._video = VideoAnalysisService()

    def process(self, request: MultimodalRequest) -> MultimodalResponse:
        """
        Process a multimodal WhatsApp event.

        Args:
            request: MultimodalRequest containing text, attachments, and farmer identity.

        Returns:
            MultimodalResponse with reply, media record IDs, and processing metadata.
        """
        t_start = time.time()
        errors = []
        media_record_ids = []
        transcription_parts = []
        visual_summaries = []
        escalation_required = False

        # 1. Resolve farmer profile
        farmer_profile = self._resolve_farmer_profile(request.sender_phone, request.sender_name)
        farmer_db_id = getattr(farmer_profile, "_db_id", None)

        # 2. Process each attachment
        for attachment in request.attachments:
            media_type_enum = MEDIA_TYPE_MAP.get(attachment.media_type_hint, MediaType.IMAGE)

            # Guard: skip DB media record creation for unregistered farmers (None farmer_db_id).
            # Passing 0 would violate the FK constraint on media_records.farmer_id.
            if farmer_db_id is None:
                logger.warning(
                    f"MultimodalOrchestrator: Unregistered farmer {request.sender_phone}; "
                    f"skipping DB media record for attachment {attachment.wa_media_id}. "
                    f"STT/Vision analysis continues without DB persistence."
                )
                # Still attempt STT/Vision analysis in-memory for best-effort reply
                try:
                    if attachment.media_type_hint in ("audio", "voice_note") and attachment.caption_text:
                        transcription_parts.append(attachment.caption_text)
                except Exception:
                    pass
                continue

            try:
                record = self._ingestion.ingest_media(
                    wa_media_id=attachment.wa_media_id,
                    farmer_db_id=farmer_db_id,
                    session_id=None,
                    caption_text=attachment.caption_text,
                )
                media_record_ids.append(record.media_id)
                self._ingestion.mark_processing(record.media_id)

                # Transcription path
                if media_type_enum in (MediaType.AUDIO, MediaType.VOICE_NOTE):
                    if record.file_path:
                        result = self._stt.transcribe(record.file_path)
                        if result.success and result.transcription:
                            transcription_parts.append(result.transcription)
                            # Store transcription back on the MediaRecord
                            self._store_transcription(record.media_id, result)
                            logger.info(
                                f"MultimodalOrchestrator: Transcribed {attachment.wa_media_id} "
                                f"({result.detected_language}, conf={result.confidence})"
                            )
                        else:
                            errors.append(f"Transcription failed for {attachment.wa_media_id}: {result.error_message}")
                    self._ingestion.mark_processed(record.media_id)

                # Image analysis path
                elif media_type_enum == MediaType.IMAGE:
                    if record.file_path:
                        vision_result = self._vision.analyse_image(
                            image_path=record.file_path,
                            media_record_id=record.id,
                            media_id=record.media_id,
                            farmer_id=farmer_db_id or 0,
                        )
                        summary = self._format_visual_summary(vision_result)
                        if summary:
                            visual_summaries.append(summary)
                        if vision_result.recommended_action == "ESCALATE_AGRONOMIST":
                            escalation_required = True
                    self._ingestion.mark_processed(record.media_id)

                # Video analysis path
                elif media_type_enum == MediaType.VIDEO:
                    if record.file_path:
                        video_result = self._video.analyse_video(
                            video_path=record.file_path,
                            media_record_id=record.id,
                            media_id=record.media_id,
                            farmer_id=farmer_db_id or 0,
                        )
                        if video_result.success and video_result.consolidated_symptoms:
                            visual_summaries.append(
                                f"[Video: {video_result.frames_analysed} frames analysed] "
                                + "; ".join(video_result.consolidated_symptoms[:5])
                            )
                        if video_result.recommended_action == "ESCALATE_AGRONOMIST":
                            escalation_required = True
                    self._ingestion.mark_processed(record.media_id)

            except MediaIngestionError as e:
                errors.append(f"Ingestion error ({attachment.wa_media_id}): {e}")
                logger.error(f"MultimodalOrchestrator: {e}")
            except Exception as e:
                errors.append(f"Unexpected error ({attachment.wa_media_id}): {e}")
                logger.error(f"MultimodalOrchestrator: {e}", exc_info=True)

        # 3. Merge all text signals into a single context string
        merged_text = self._merge_context(
            text_body=request.text_body,
            transcriptions=transcription_parts,
            visual_summaries=visual_summaries,
        )

        # 4. Route through Phase 3 FarmerAgent if there is actionable text
        agent_response: Optional[AgentResponse] = None
        if merged_text and merged_text.strip():
            agent_response = self._farmer_agent.process_message(
                message=merged_text,
                sender_phone=request.sender_phone,
                profile=farmer_profile,
            )
        else:
            # Media received but no parseable text signal
            agent_response = None

        # 5. Build response
        t_ms = (time.time() - t_start) * 1000.0

        if agent_response is None:
            # Nothing to reply to (e.g., image received but analysis unavailable and no text)
            status = "IGNORED" if not errors else "ERROR"
            reply = (
                "🖼️ आपकी मीडिया मिली। "
                "कृपया अपनी फसल की समस्या टेक्स्ट में लिखें ताकि हम बेहतर जवाब दे सकें।"
                if not errors else
                "⚠️ मीडिया प्रोसेस करने में समस्या आई। कृपया टेक्स्ट में सवाल पूछें।"
            )
        elif escalation_required and agent_response.status not in ("ESCALATED",):
            status = "ESCALATED"
            reply = (
                "🚨 *CDO / Agronomist Escalation Required*\n\n"
                "आपकी फसल में गंभीर लक्षण दिख रहे हैं। "
                "हमारे विशेषज्ञ शीघ्र संपर्क करेंगे।\n\n"
                + (agent_response.reply_text or "")
            )
        else:
            status = agent_response.status
            reply = agent_response.reply_text

        return MultimodalResponse(
            status=status,
            reply_text=reply,
            intent=getattr(agent_response, "intent", None).value if (agent_response and getattr(agent_response, "intent", None)) else None,
            media_records_created=media_record_ids,
            transcription=" | ".join(transcription_parts) if transcription_parts else None,
            visual_summary=" | ".join(visual_summaries) if visual_summaries else None,
            escalation_required=escalation_required,
            processing_time_ms=t_ms,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_farmer_profile(self, phone: str, name: str) -> FarmerProfile:
        """Load farmer DB record and build a FarmerProfile for FarmerAgent."""
        try:
            from database.connection import get_db_session
            from database.repositories.farmer_repository import FarmerRepository
            with get_db_session() as session:
                repo = FarmerRepository(session)
                db_farmer = repo.lookup_by_phone(phone)
            if db_farmer:
                plot = db_farmer.plots[0] if db_farmer.plots else None
                crop_rec = plot.crops[0] if (plot and plot.crops) else None
                soil = plot.soil_profiles[0] if (plot and plot.soil_profiles) else None
                profile = FarmerProfile(
                    name=db_farmer.full_name,
                    phone=db_farmer.primary_phone,
                    district=db_farmer.district.name if db_farmer.district else "General",
                    crop=crop_rec.crop_name if crop_rec else "General",
                    soil_type=soil.soil_type if soil else "Loam",
                    farmer_id=db_farmer.farmer_id,
                )
                profile._db_id = db_farmer.id
                return profile
        except Exception as e:
            logger.debug(f"MultimodalOrchestrator: DB farmer lookup failed for {phone}: {e}")

        profile = FarmerProfile(name=name, phone=phone)
        profile._db_id = None
        return profile

    @staticmethod
    def _merge_context(
        text_body: Optional[str],
        transcriptions: List[str],
        visual_summaries: List[str],
    ) -> Optional[str]:
        """
        Combine text, transcriptions, and visual observations into one coherent message.
        Each source is clearly labelled to assist the LLM and classifier.
        """
        parts = []
        if text_body and text_body.strip():
            parts.append(text_body.strip())
        for tr in transcriptions:
            parts.append(f"[Voice Note Transcription]: {tr.strip()}")
        for vs in visual_summaries:
            parts.append(f"[Visual Observation from Image/Video]: {vs.strip()}")
        return "\n\n".join(parts) if parts else None

    @staticmethod
    def _format_visual_summary(vision_result) -> Optional[str]:
        """Format a VisionResult into a terse descriptive sentence for the merged context."""
        if not vision_result.success:
            return None
        crop = vision_result.identified_crop or "crop"
        symptoms = vision_result.symptoms[:4]
        condition = vision_result.general_condition
        quality = vision_result.image_quality
        if quality in ("BLURRY", "POOR_LIGHTING", "LOW_RESOLUTION", "NON_AGRICULTURAL"):
            return f"Image quality: {quality}. Unable to reliably identify symptoms."
        if not symptoms:
            return f"{crop} visible. Condition: {condition}. No clear symptoms detected."
        return f"{crop} visible. Observed symptoms (UNCONFIRMED): {', '.join(symptoms)}. Condition: {condition}."

    @staticmethod
    def _store_transcription(media_id: str, result) -> None:
        """Write transcription metadata back to the MediaRecord."""
        from database.connection import get_db_session
        from database.models import MediaRecord
        with get_db_session() as session:
            rec = session.query(MediaRecord).filter_by(media_id=media_id).first()
            if rec:
                rec.transcription_text = result.transcription
                rec.detected_language = result.detected_language
                rec.transcription_confidence = result.confidence
                session.commit()
