"""Focused Phase 4 stabilization tests; external providers and HTTP are mocked."""

import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import uuid
import wave

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("WHATSAPP_TOKEN", None)

from database.connection import get_db_session, init_db
from database.enums import MediaProcessingStatus, MediaType
from database.models import Farmer, MediaRecord
from database.repositories.cdo_repository import CDORepository
from database.repositories.farmer_repository import FarmerRepository
from media.ingestion import (
    MediaIngestionService,
    MediaRetryableError,
    MediaValidationError,
)
from media.orchestrator import (
    MediaAttachment,
    MultimodalOrchestrator,
    MultimodalRequest,
    MultimodalResponse,
)
from media.stt import SpeechToTextService
from media.video import VideoAnalysisService
from media.vision import AgriculturalVisionService

init_db()


def _create_farmer():
    phone = "990" + uuid.uuid4().hex[:7]
    with get_db_session() as session:
        district = CDORepository(session).get_or_create_district("Stabilization Test")
        farmer = FarmerRepository(session).create_farmer(
            farmer_id=f"FARM-STAB-{uuid.uuid4().hex[:8]}",
            full_name="Stabilization Test Farmer",
            primary_phone=phone,
            district_id=district.id,
        )
        session.commit()
        return farmer.id, phone


def _create_media_record(media_type=MediaType.IMAGE, max_retries=3):
    farmer_id, _ = _create_farmer()
    media_id = f"STAB-{uuid.uuid4().hex}"
    ingestion = MediaIngestionService()
    record = ingestion.register_synthetic_media(
        wa_media_id=media_id,
        farmer_db_id=farmer_id,
        session_id=None,
        media_type=media_type,
        mime_type="image/png" if media_type == MediaType.IMAGE else "audio/ogg",
        file_path="synthetic-media.bin",
        file_size_bytes=1,
    )
    with get_db_session() as session:
        stored = session.query(MediaRecord).filter_by(media_id=media_id).one()
        stored.max_retries = max_retries
        session.commit()
    return ingestion, record, farmer_id


def _wav(path):
    with wave.open(str(path), "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(8000)
        file.writeframes(b"\0\0" * 800)
    return str(path)


def _orchestrator(profile):
    orchestrator = MultimodalOrchestrator()
    orchestrator._resolve_farmer_profile = lambda phone, name: profile
    orchestrator._farmer_agent.process_message = MagicMock(
        return_value=SimpleNamespace(status="ANSWERED", reply_text="Mocked answer", intent=None)
    )
    return orchestrator


def _stored_media_status(media_id):
    with get_db_session() as session:
        record = session.query(MediaRecord).filter_by(media_id=media_id).one()
        return record.status, record.retry_count, record.error_message, record.transcription_text


class MediaTransientProcessingTests(unittest.TestCase):
    def test_unregistered_audio_image_and_video_are_analyzed_transiently(self):
        profile = SimpleNamespace(_db_id=None)
        profile.name = "Unregistered sender"
        profile.phone = "9900000000"
        orchestrator = _orchestrator(profile)
        media_types = {
            "audio": MediaType.AUDIO,
            "image": MediaType.IMAGE,
            "video": MediaType.VIDEO,
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = {
                kind: Path(temp_dir) / f"payload.{suffix}"
                for kind, suffix in (("audio", "ogg"), ("image", "png"), ("video", "mp4"))
            }
            for path in paths.values():
                path.write_bytes(b"synthetic")

            @contextmanager
            def transient_media(media_id):
                kind = next(kind for kind in paths if kind in media_id)
                yield paths[kind], media_types[kind]

            orchestrator._ingestion.transient_media = MagicMock(side_effect=transient_media)
            orchestrator._stt.transcribe = MagicMock(return_value=SimpleNamespace(
                success=True, transcription="voice words", detected_language="en", confidence=0.9,
            ))
            orchestrator._vision.analyse_image = MagicMock(return_value=SimpleNamespace(
                success=True, identified_crop="Sugarcane", symptoms=["yellowing"],
                general_condition="STRESSED", image_quality="GOOD",
                recommended_action="ANSWER", retryable=False,
            ))
            orchestrator._video.analyse_video = MagicMock(return_value=SimpleNamespace(
                success=True, frames_analysed=1, consolidated_symptoms=["wilting"],
                recommended_action="ANSWER", retryable=False,
            ))

            response = orchestrator.process(MultimodalRequest(
                sender_phone=profile.phone,
                sender_name=profile.name,
                message_id="unregistered-media",
                text_body=None,
                attachments=[
                    MediaAttachment("audio-item", "audio", "audio/ogg"),
                    MediaAttachment("image-item", "image", "image/png"),
                    MediaAttachment("video-item", "video", "video/mp4"),
                ],
            ))

        self.assertEqual(response.analysis_persistence, "TRANSIENT")
        self.assertEqual(response.media_records_created, [])
        self.assertEqual(response.transcription, "voice words")
        self.assertIn("yellowing", response.visual_summary)
        self.assertIn("wilting", response.visual_summary)
        orchestrator._vision.analyse_image.assert_called_once()
        vision_kwargs = orchestrator._vision.analyse_image.call_args.kwargs
        self.assertIsNone(vision_kwargs["media_record_id"])
        self.assertIsNone(vision_kwargs["farmer_id"])
        self.assertFalse(vision_kwargs["persist_observation"])
        video_kwargs = orchestrator._video.analyse_video.call_args.kwargs
        self.assertIsNone(video_kwargs["media_record_id"])
        self.assertIsNone(video_kwargs["farmer_id"])
        self.assertFalse(video_kwargs["persist_observations"])

    def test_transient_download_without_whatsapp_credentials_is_retryable(self):
        ingestion = MediaIngestionService()
        with self.assertRaises(MediaRetryableError):
            with ingestion.transient_media("no-token-media"):
                self.fail("unavailable media download must not produce a file")

    def test_transient_download_files_are_removed_after_analysis(self):
        ingestion = MediaIngestionService()
        ingestion._whatsapp_token = "test-token"
        ingestion._resolve_media_url = MagicMock(return_value=(
            "https://cdn.whatsapp.net/example", "image/png", 4,
        ))
        observed_paths = []

        def download(media_id, url, mime, media_type, storage_dir=None, cache=True):
            path = storage_dir / "transient.png"
            path.write_bytes(b"data")
            observed_paths.append(path)
            return path

        ingestion._download_media = MagicMock(side_effect=download)
        with ingestion.transient_media("transient-id") as (path, media_type):
            self.assertTrue(path.exists())
            self.assertEqual(media_type, MediaType.IMAGE)
        self.assertFalse(observed_paths[0].exists())


class MediaLifecycleTests(unittest.TestCase):
    def test_processing_claim_is_atomic_and_terminal_status_is_not_reclaimed(self):
        ingestion, record, _ = _create_media_record()
        self.assertTrue(ingestion.mark_processing(record.media_id))
        self.assertFalse(ingestion.mark_processing(record.media_id))
        ingestion.mark_processed(record.media_id)
        self.assertFalse(ingestion.mark_processing(record.media_id))
        self.assertEqual(_stored_media_status(record.media_id)[0], MediaProcessingStatus.PROCESSED)

    def test_retry_exhaustion_and_permanent_validation_failure_are_recorded(self):
        ingestion, record, _ = _create_media_record(max_retries=2)
        ingestion.mark_processing(record.media_id)
        ingestion.mark_failed(record.media_id, "temporary provider error", retryable=True)
        self.assertEqual(_stored_media_status(record.media_id)[:2], (MediaProcessingStatus.PENDING, 1))
        ingestion.mark_processing(record.media_id)
        ingestion.mark_failed(record.media_id, "provider still unavailable", retryable=True)
        self.assertEqual(_stored_media_status(record.media_id)[:2], (MediaProcessingStatus.FAILED, 2))

        permanent_ingestion, permanent_record, _ = _create_media_record()
        permanent_ingestion.mark_processing(permanent_record.media_id)
        permanent_ingestion.mark_failed(
            permanent_record.media_id,
            "Unsupported MIME type",
            retryable=False,
        )
        status, retries, error, _ = _stored_media_status(permanent_record.media_id)
        self.assertEqual(status, MediaProcessingStatus.FAILED)
        self.assertEqual(retries, 0)
        self.assertEqual(error, "Unsupported MIME type")

    def test_ingestion_validation_failure_creates_a_terminal_record(self):
        farmer_id, _ = _create_farmer()
        ingestion = MediaIngestionService()
        ingestion._resolve_media_url = MagicMock(return_value=(
            "https://cdn.whatsapp.net/document", "application/pdf", 100,
        ))
        media_id = f"invalid-{uuid.uuid4().hex}"
        with self.assertRaises(MediaValidationError):
            ingestion.ingest_media(
                wa_media_id=media_id,
                farmer_db_id=farmer_id,
                session_id=None,
                media_type_hint=MediaType.IMAGE,
                mime_type_hint="image/png",
            )
        status, retries, error, _ = _stored_media_status(media_id)
        self.assertEqual(status, MediaProcessingStatus.FAILED)
        self.assertEqual(retries, 0)
        self.assertIn("Unsupported MIME type", error)

    def test_retryable_download_failure_can_resume_without_duplicate_record(self):
        farmer_id, _ = _create_farmer()
        ingestion = MediaIngestionService()
        ingestion._whatsapp_token = "test-token"
        ingestion._resolve_media_url = MagicMock(side_effect=[
            MediaRetryableError("temporary Meta API failure"),
            ("https://cdn.whatsapp.net/retry", "image/png", 4),
        ])
        media_id = f"retry-download-{uuid.uuid4().hex}"
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "download.png"

            def download(*args, **kwargs):
                file_path.write_bytes(b"data")
                return file_path

            ingestion._download_media = MagicMock(side_effect=download)
            arguments = {
                "wa_media_id": media_id,
                "farmer_db_id": farmer_id,
                "session_id": None,
                "media_type_hint": MediaType.IMAGE,
                "mime_type_hint": "image/png",
            }
            with self.assertRaises(MediaRetryableError):
                ingestion.ingest_media(**arguments)

            status, retries, _, _ = _stored_media_status(media_id)
            self.assertEqual(status, MediaProcessingStatus.PENDING)
            self.assertEqual(retries, 1)

            record = ingestion.ingest_media(**arguments)
            self.assertEqual(record.media_id, media_id)
            self.assertEqual(record.file_path, str(file_path))
            self.assertEqual(_stored_media_status(media_id)[1], 1)
            ingestion.mark_processing(media_id)
            ingestion.mark_processed(media_id)

    def test_successful_transcription_survives_retryable_failure(self):
        ingestion, record, _ = _create_media_record(MediaType.AUDIO)
        with get_db_session() as session:
            stored = session.query(MediaRecord).filter_by(media_id=record.media_id).one()
            stored.transcription_text = "previous successful transcription"
            session.commit()
        ingestion.mark_processing(record.media_id)
        ingestion.mark_failed(record.media_id, "later transient error", retryable=True)
        status, retries, _, transcript = _stored_media_status(record.media_id)
        self.assertEqual(status, MediaProcessingStatus.PENDING)
        self.assertEqual(retries, 1)
        self.assertEqual(transcript, "previous successful transcription")

    def test_unexpected_processing_exception_does_not_leave_record_processing(self):
        ingestion, record, farmer_id = _create_media_record(MediaType.AUDIO)
        profile = SimpleNamespace(_db_id=farmer_id, name="Registered", phone="9900000001")
        orchestrator = _orchestrator(profile)
        orchestrator._ingestion.ingest_media = MagicMock(return_value=record)
        orchestrator._stt.transcribe = MagicMock(side_effect=RuntimeError("provider transport failure"))
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "audio.ogg"
            file_path.write_bytes(b"audio")
            with get_db_session() as session:
                session.query(MediaRecord).filter_by(media_id=record.media_id).update(
                    {"file_path": str(file_path)}
                )
                session.commit()
            record.file_path = str(file_path)
            response = orchestrator.process(MultimodalRequest(
                sender_phone=profile.phone,
                sender_name=profile.name,
                message_id="exception-media",
                text_body=None,
                attachments=[MediaAttachment(record.media_id, "audio", "audio/ogg")],
            ))
        status, retries, error, _ = _stored_media_status(record.media_id)
        self.assertEqual(status, MediaProcessingStatus.PENDING)
        self.assertEqual(retries, 1)
        self.assertIn("provider transport failure", error)
        self.assertTrue(response.errors)

    def test_duplicate_processed_media_is_not_analyzed_again(self):
        ingestion, record, farmer_id = _create_media_record(MediaType.AUDIO)
        ingestion.mark_processing(record.media_id)
        ingestion.mark_processed(record.media_id)
        profile = SimpleNamespace(_db_id=farmer_id, name="Registered", phone="9900000002")
        orchestrator = _orchestrator(profile)
        orchestrator._ingestion.ingest_media = MagicMock(return_value=record)
        orchestrator._stt.transcribe = MagicMock()
        orchestrator.process(MultimodalRequest(
            sender_phone=profile.phone,
            sender_name=profile.name,
            message_id="duplicate-media",
            text_body=None,
            attachments=[MediaAttachment(record.media_id, "audio", "audio/ogg")],
        ))
        orchestrator._stt.transcribe.assert_not_called()

    def test_missing_credentials_and_malformed_provider_responses_are_not_success(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            wav_path = _wav(Path(temp_dir) / "audio.wav")
            stt = SpeechToTextService()
            unavailable = stt.transcribe(wav_path)
            self.assertFalse(unavailable.success)
            self.assertEqual(unavailable.provider, "unavailable")
            self.assertTrue(unavailable.retryable)

            stt._genai = MagicMock()
            stt._genai.upload_file.return_value = object()
            stt._genai.GenerativeModel.return_value.generate_content.return_value = SimpleNamespace(
                text="not valid JSON",
            )
            malformed_audio = stt.transcribe(wav_path)
            self.assertFalse(malformed_audio.success)
            self.assertTrue(malformed_audio.retryable)

            image_path = Path(temp_dir) / "image.png"
            image_path.write_bytes(b"synthetic image")
            vision = AgriculturalVisionService()
            vision._genai = MagicMock()
            vision._genai.upload_file.return_value = object()
            vision._genai.GenerativeModel.return_value.generate_content.return_value = SimpleNamespace(
                text="not valid JSON",
            )
            malformed_image = vision.analyse_image(
                str(image_path), None, "malformed-image", None, persist_observation=False,
            )
            self.assertFalse(malformed_image.success)
            self.assertTrue(malformed_image.retryable)

    def test_all_failed_video_frames_do_not_report_success(self):
        video = VideoAnalysisService()
        video._vision.analyse_image = MagicMock(return_value=SimpleNamespace(
            success=False,
            retryable=True,
            error_message="vision unavailable",
        ))
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "video.mp4"
            video_path.write_bytes(b"synthetic placeholder")
            with patch("media.video.cv2.VideoCapture") as capture_cls:
                capture = MagicMock()
                capture.isOpened.return_value = True
                capture.get.side_effect = lambda prop: {
                    5: 2.0,
                    7: 10.0,
                }.get(prop, 0)
                capture.read.return_value = (True, __import__("numpy").zeros((64, 64, 3), dtype="uint8"))
                capture_cls.return_value = capture
                result = video.analyse_video(
                    str(video_path),
                    None,
                    "failed-video",
                    None,
                    persist_observations=False,
                )
        self.assertFalse(result.success)
        self.assertTrue(result.retryable)
        self.assertIn("analysed successfully", result.error_message)


class WebhookFallbackDispatchTests(unittest.TestCase):
    def _assert_queued(self, status, reply):
        from gateway import webhook_server

        request = MultimodalRequest(
            sender_phone="9900000012",
            sender_name="Test",
            message_id=f"webhook-{uuid.uuid4().hex}",
            text_body=None,
        )
        dedup = MagicMock()
        dedup.claim_message.return_value = True
        orchestrator = MagicMock()
        orchestrator.process.return_value = MultimodalResponse(
            status=status,
            reply_text=reply,
            intent=None,
        )
        outbox = MagicMock()
        with (
            patch.object(webhook_server, "dedup_service", dedup),
            patch.object(webhook_server, "multimodal_orchestrator", orchestrator),
            patch.object(webhook_server, "outbox_service", outbox),
        ):
            webhook_server.process_multimodal_background(request)
        outbox.enqueue.assert_called_once_with(
            recipient_phone=request.sender_phone,
            message_text=reply,
            idempotency_key=f"mm_out_{request.message_id}",
        )
        outbox.process_pending.assert_called_once()
        dedup.complete_message.assert_called_once_with(request.message_id)

    def test_image_provider_unavailable_reply_is_queued(self):
        self._assert_queued("IGNORED", "Image received; vision is unavailable.")

    def test_audio_provider_unavailable_reply_is_queued(self):
        self._assert_queued("IGNORED", "Audio received; transcription is unavailable.")

    def test_media_processing_failure_reply_is_queued(self):
        self._assert_queued("ERROR", "Media processing failed.")

    def test_media_without_text_reply_is_queued(self):
        self._assert_queued("IGNORED", "Media received; please describe the crop issue.")

    def test_successful_multimodal_reply_is_queued(self):
        self._assert_queued("ANSWERED", "Mocked multimodal answer.")

    def test_duplicate_delivery_is_not_enqueued(self):
        from gateway import webhook_server

        request = MultimodalRequest(
            sender_phone="9900000012",
            sender_name="Test",
            message_id="duplicate-webhook-id",
            text_body=None,
        )
        dedup = MagicMock()
        dedup.claim_message.return_value = False
        outbox = MagicMock()
        with (
            patch.object(webhook_server, "dedup_service", dedup),
            patch.object(webhook_server, "outbox_service", outbox),
        ):
            webhook_server.process_multimodal_background(request)
        outbox.enqueue.assert_not_called()
        outbox.process_pending.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
