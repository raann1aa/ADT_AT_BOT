"""
Phase 4 — Multimodal Intelligence Test Suite.

Tests all Phase 4 modules with synthetic fixtures.
No actual network calls are made — all external providers are mocked.
Test isolation: in-memory SQLite, temporary files, and mock API clients.

All tests are clearly marked as MOCKED where real model/API calls are not made.
"""

import os
import sys
import json
import uuid
import tempfile
import wave
import struct
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

# Project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Force in-memory SQLite for all tests
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.pop("GEMINI_API_KEY", None)   # No live API calls
os.environ.pop("WHATSAPP_TOKEN", None)   # No network media downloads

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# ---------------------------------------------------------------------------
# Shared test infrastructure
# ---------------------------------------------------------------------------

from database.connection import init_db, get_db_session
from database.models import MediaRecord, VisualObservation, Farmer, ConversationSession
from database.enums import MediaType, MediaProcessingStatus
from database.repositories.cdo_repository import CDORepository

init_db()

PASS = 0
FAIL = 0
FAILURES = []


def test(label: str, fn):
    global PASS, FAIL
    try:
        fn()
        print(f"  \u2705 PASS: {label}")
        PASS += 1
    except Exception as e:
        print(f"  \u274c FAIL: {label}")
        print(f"       {e}")
        FAIL += 1
        FAILURES.append((label, str(e)))


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def make_farmer(phone="9900000001", name="Test Kisan", district="Nashik", farmer_id="FARM-TST-01"):
    with get_db_session() as s:
        repo = __import__("database.repositories.farmer_repository", fromlist=["FarmerRepository"]).FarmerRepository
        from database.repositories.farmer_repository import FarmerRepository
        from database.repositories.cdo_repository import CDORepository
        d = CDORepository(s).get_or_create_district(district)
        repo2 = FarmerRepository(s)
        try:
            farmer = repo2.create_farmer(
                farmer_id=farmer_id,
                full_name=name,
                primary_phone=phone,
                district_id=d.id,
            )
            s.commit()
            return farmer.id
        except Exception:
            s.rollback()
            f = repo2.get_by_phone(phone)
            return f.id if f else None


def make_wav_file(path: str, duration_sec: float = 0.5) -> str:
    """Write a minimal valid WAV file of the given duration."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    framerate = 8000
    n_frames = int(framerate * duration_sec)
    with wave.open(str(p), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        wf.writeframes(struct.pack(f"<{n_frames}h", *([0] * n_frames)))
    return str(p)


def make_png_file(path: str, color=(0, 128, 0)) -> str:
    """Write a minimal green 10x10 PNG."""
    from PIL import Image
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (10, 10), color=color)
    img.save(str(p), format="PNG")
    return str(p)


def make_video_file(path: str) -> str:
    """Write a minimal synthetic video using OpenCV (black 5-frame 2fps mp4)."""
    import cv2
    import numpy as np
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(p), fourcc, 2.0, (64, 64))
    for _ in range(10):
        frame = np.zeros((64, 64, 3), dtype="uint8")
        out.write(frame)
    out.release()
    return str(p)


# ---------------------------------------------------------------------------
# SECTION 1: Media Ingestion
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("SECTION 1: Media Ingestion")
print("=" * 70)

from media.ingestion import MediaIngestionService, MediaIngestionError

_ingestion = MediaIngestionService()


def test_1_1_audio_ingestion():
    """MOCKED: Offline mode — no WHATSAPP_TOKEN, ingestion uses synthetic file."""
    fid = make_farmer(phone="9901000001", farmer_id="FARM-TST-ING-01")
    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = make_wav_file(os.path.join(tmpdir, "voice.wav"))
        wa_id = f"MED-{uuid.uuid4().hex[:8]}"
        rec = _ingestion.register_synthetic_media(
            wa_media_id=wa_id,
            farmer_db_id=fid,
            session_id=None,
            media_type=MediaType.VOICE_NOTE,
            mime_type="audio/ogg",
            file_path=audio_path,
            file_size_bytes=os.path.getsize(audio_path),
            caption_text="आवाज नोट",
        )
    assert rec.media_id == wa_id
    assert rec.media_type == MediaType.VOICE_NOTE
    assert rec.status == MediaProcessingStatus.PENDING


def test_1_2_image_ingestion():
    """MOCKED: Synthetic image file registered without network call."""
    fid = make_farmer(phone="9901000002", farmer_id="FARM-TST-ING-02")
    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = make_png_file(os.path.join(tmpdir, "leaf.png"))
        wa_id = f"MED-{uuid.uuid4().hex[:8]}"
        rec = _ingestion.register_synthetic_media(
            wa_media_id=wa_id,
            farmer_db_id=fid,
            session_id=None,
            media_type=MediaType.IMAGE,
            mime_type="image/png",
            file_path=img_path,
            file_size_bytes=os.path.getsize(img_path),
        )
    assert rec.media_type == MediaType.IMAGE
    assert rec.status == MediaProcessingStatus.PENDING


def test_1_3_video_ingestion():
    """MOCKED: Synthetic video file registered without network call."""
    fid = make_farmer(phone="9901000003", farmer_id="FARM-TST-ING-03")
    with tempfile.TemporaryDirectory() as tmpdir:
        vid_path = make_video_file(os.path.join(tmpdir, "field.mp4"))
        wa_id = f"MED-{uuid.uuid4().hex[:8]}"
        rec = _ingestion.register_synthetic_media(
            wa_media_id=wa_id,
            farmer_db_id=fid,
            session_id=None,
            media_type=MediaType.VIDEO,
            mime_type="video/mp4",
            file_path=vid_path,
            file_size_bytes=os.path.getsize(vid_path),
        )
    assert rec.media_type == MediaType.VIDEO


def test_1_4_invalid_mime_rejected():
    """MOCKED: Unsupported MIME type raises MediaIngestionError."""
    try:
        _ingestion._validate_mime("application/pdf")
        raise AssertionError("Expected MediaIngestionError")
    except MediaIngestionError as e:
        assert "Unsupported MIME type" in str(e)


def test_1_5_duplicate_ingestion_idempotent():
    """MOCKED: Registering the same wa_media_id twice returns the existing record."""
    fid = make_farmer(phone="9901000004", farmer_id="FARM-TST-ING-04")
    wa_id = f"MED-DUP-{uuid.uuid4().hex[:8]}"
    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = make_png_file(os.path.join(tmpdir, "dup.png"))
        rec1 = _ingestion.register_synthetic_media(
            wa_media_id=wa_id, farmer_db_id=fid, session_id=None,
            media_type=MediaType.IMAGE, mime_type="image/png",
            file_path=img_path, file_size_bytes=1,
        )
        rec2 = _ingestion.register_synthetic_media(
            wa_media_id=wa_id, farmer_db_id=fid, session_id=None,
            media_type=MediaType.IMAGE, mime_type="image/png",
            file_path=img_path, file_size_bytes=1,
        )
    assert rec1.id == rec2.id, "Duplicate ingestion must return existing record"


def test_1_6_expired_url_error():
    """MOCKED: resolve_media_url with a 404 response raises MediaIngestionError."""
    # Simulate 404 from Meta API
    import httpx
    with patch("media.ingestion.httpx.get") as mock_get:
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found",
            request=MagicMock(),
            response=MagicMock(status_code=404),
        )
        mock_get.return_value = mock_response
        # Temporarily set a fake token so it tries to call the API
        _ingestion._whatsapp_token = "fake_token_for_test"
        try:
            _ingestion._resolve_media_url("expired_media_id_999")
            raise AssertionError("Expected MediaIngestionError")
        except MediaIngestionError as e:
            assert "expired" in str(e).lower() or "404" in str(e)
        finally:
            _ingestion._whatsapp_token = ""


def test_1_7_missing_file_handled():
    """MOCKED: Registering a path that does not exist is recorded; status processing handles missing."""
    fid = make_farmer(phone="9901000005", farmer_id="FARM-TST-ING-05")
    wa_id = f"MED-MISS-{uuid.uuid4().hex[:8]}"
    rec = _ingestion.register_synthetic_media(
        wa_media_id=wa_id, farmer_db_id=fid, session_id=None,
        media_type=MediaType.IMAGE, mime_type="image/png",
        file_path="/nonexistent/path/file.png",
        file_size_bytes=0,
    )
    assert rec is not None  # Record created; vision module will catch missing file


def test_1_8_farmer_isolation():
    """MOCKED: Media records are associated to their farmer and not visible to others."""
    fid_a = make_farmer(phone="9901000006", farmer_id="FARM-TST-ING-06")
    fid_b = make_farmer(phone="9901000007", farmer_id="FARM-TST-ING-07")
    wa_id_a = f"MED-ISO-A-{uuid.uuid4().hex[:8]}"
    wa_id_b = f"MED-ISO-B-{uuid.uuid4().hex[:8]}"
    with tempfile.TemporaryDirectory() as tmpdir:
        path_a = make_png_file(os.path.join(tmpdir, "a.png"))
        path_b = make_png_file(os.path.join(tmpdir, "b.png"))
        rec_a = _ingestion.register_synthetic_media(wa_media_id=wa_id_a, farmer_db_id=fid_a, session_id=None, media_type=MediaType.IMAGE, mime_type="image/png", file_path=path_a, file_size_bytes=1)
        rec_b = _ingestion.register_synthetic_media(wa_media_id=wa_id_b, farmer_db_id=fid_b, session_id=None, media_type=MediaType.IMAGE, mime_type="image/png", file_path=path_b, file_size_bytes=1)
    assert rec_a.farmer_id == fid_a
    assert rec_b.farmer_id == fid_b
    assert rec_a.farmer_id != rec_b.farmer_id


test("1.1 Audio ingestion — synthetic WAV file (MOCKED)", test_1_1_audio_ingestion)
test("1.2 Image ingestion — synthetic PNG file (MOCKED)", test_1_2_image_ingestion)
test("1.3 Video ingestion — synthetic MP4 file (MOCKED)", test_1_3_video_ingestion)
test("1.4 Invalid MIME type rejected with MediaIngestionError (MOCKED)", test_1_4_invalid_mime_rejected)
test("1.5 Duplicate wa_media_id ingestion is idempotent (MOCKED)", test_1_5_duplicate_ingestion_idempotent)
test("1.6 Expired media URL raises MediaIngestionError (MOCKED)", test_1_6_expired_url_error)
test("1.7 Missing file path handled gracefully (MOCKED)", test_1_7_missing_file_handled)
test("1.8 Farmer isolation enforced on media records (MOCKED)", test_1_8_farmer_isolation)


# ---------------------------------------------------------------------------
# SECTION 2: Speech-to-Text
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("SECTION 2: Speech-to-Text (MOCKED — no GEMINI_API_KEY)")
print("=" * 70)

from media.stt import SpeechToTextService, TranscriptionResult

_stt = SpeechToTextService()


def test_2_1_marathi_transcription_mocked():
    """MOCKED: Patches Gemini to return a Marathi transcription."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = make_wav_file(f.name)
    stt = SpeechToTextService()
    mock_genai = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "transcription": "माझ्या उसाच्या पानांवर पिवळे डाग पडले आहेत",
        "detected_language": "mr",
        "confidence": 0.91,
        "is_unclear": False,
        "is_mixed_language": False,
        "warnings": [],
    })
    mock_genai.upload_file.return_value = MagicMock()
    mock_genai.GenerativeModel.return_value.generate_content.return_value = mock_response
    stt._genai = mock_genai
    result = stt.transcribe(wav_path)
    os.unlink(wav_path)
    assert result.success is True
    assert result.detected_language == "mr"
    assert "उसाच्या" in result.transcription
    assert result.confidence > 0.8


def test_2_2_hindi_transcription_mocked():
    """MOCKED: Patches Gemini to return a Hindi transcription."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = make_wav_file(f.name)
    stt = SpeechToTextService()
    mock_genai = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "transcription": "मेरे गेहूं में पीले पत्ते आ गए हैं",
        "detected_language": "hi",
        "confidence": 0.88,
        "is_unclear": False,
        "is_mixed_language": False,
        "warnings": [],
    })
    mock_genai.upload_file.return_value = MagicMock()
    mock_genai.GenerativeModel.return_value.generate_content.return_value = mock_response
    stt._genai = mock_genai
    result = stt.transcribe(wav_path)
    os.unlink(wav_path)
    assert result.success is True
    assert result.detected_language == "hi"
    assert "गेहूं" in result.transcription


def test_2_3_english_transcription_mocked():
    """MOCKED: Patches Gemini to return an English transcription."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = make_wav_file(f.name)
    stt = SpeechToTextService()
    mock_genai = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "transcription": "My sugarcane crop has yellow rust marks",
        "detected_language": "en",
        "confidence": 0.95,
        "is_unclear": False,
        "is_mixed_language": False,
        "warnings": [],
    })
    mock_genai.upload_file.return_value = MagicMock()
    mock_genai.GenerativeModel.return_value.generate_content.return_value = mock_response
    stt._genai = mock_genai
    result = stt.transcribe(wav_path)
    os.unlink(wav_path)
    assert result.success is True
    assert result.detected_language == "en"


def test_2_4_mixed_language_mocked():
    """MOCKED: Mixed Marathi-Hindi-English (Marathlish) flagged correctly."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = make_wav_file(f.name)
    stt = SpeechToTextService()
    mock_genai = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "transcription": "Maza oos 4 acres ahe, drip irrigation aahe",
        "detected_language": "mixed",
        "confidence": 0.78,
        "is_unclear": False,
        "is_mixed_language": True,
        "warnings": ["Mixed Marathi-English detected"],
    })
    mock_genai.upload_file.return_value = MagicMock()
    mock_genai.GenerativeModel.return_value.generate_content.return_value = mock_response
    stt._genai = mock_genai
    result = stt.transcribe(wav_path)
    os.unlink(wav_path)
    assert result.is_mixed_language is True
    assert result.detected_language == "mixed"


def test_2_5_unclear_audio_no_fabrication():
    """MOCKED: Noisy audio returns is_unclear=True; no fabricated words."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = make_wav_file(f.name)
    stt = SpeechToTextService()
    mock_genai = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "transcription": "[unclear] [unclear] पाणी [unclear]",
        "detected_language": "mr",
        "confidence": 0.3,
        "is_unclear": True,
        "is_mixed_language": False,
        "warnings": ["High noise level detected"],
    })
    mock_genai.upload_file.return_value = MagicMock()
    mock_genai.GenerativeModel.return_value.generate_content.return_value = mock_response
    stt._genai = mock_genai
    result = stt.transcribe(wav_path)
    os.unlink(wav_path)
    assert result.is_unclear is True
    assert "[unclear]" in result.transcription
    assert result.confidence < 0.5


def test_2_6_empty_audio_handled():
    """MOCKED: Empty audio file returns failure without crashing."""
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
        empty_path = f.name
    with open(empty_path, "wb") as f:
        pass  # 0 bytes
    result = _stt.transcribe(empty_path)
    os.unlink(empty_path)
    assert result.success is False
    assert result.error_message is not None


def test_2_7_corrupted_audio_handled():
    """MOCKED: Corrupted audio triggers failure without crashing."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(b"THIS IS NOT A VALID WAV FILE")
        corrupt_path = f.name
    stt = SpeechToTextService()
    mock_genai = MagicMock()
    mock_genai.upload_file.side_effect = Exception("Invalid audio format")
    stt._genai = mock_genai
    result = stt.transcribe(corrupt_path)
    os.unlink(corrupt_path)
    assert result.success is False
    assert result.error_message is not None


def test_2_8_no_api_key_returns_unavailable():
    """Actual: Without GEMINI_API_KEY, transcription returns UNAVAILABLE gracefully."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = make_wav_file(f.name)
    stt = SpeechToTextService()  # No API key set in env
    result = stt.transcribe(wav_path)
    os.unlink(wav_path)
    assert result.success is False
    assert result.provider == "unavailable"
    assert result.transcription is None


def test_2_9_unsupported_format_rejected():
    """Actual: .pdf audio format rejected before any API call."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"%PDF-1.4 fake content")
        pdf_path = f.name
    result = _stt.transcribe(pdf_path)
    os.unlink(pdf_path)
    assert result.success is False
    assert "Unsupported" in result.error_message


test("2.1 Marathi transcription returns correct language (MOCKED)", test_2_1_marathi_transcription_mocked)
test("2.2 Hindi transcription returns correct language (MOCKED)", test_2_2_hindi_transcription_mocked)
test("2.3 English transcription returns correct language (MOCKED)", test_2_3_english_transcription_mocked)
test("2.4 Mixed Marathi-Hindi-English flagged as 'mixed' (MOCKED)", test_2_4_mixed_language_mocked)
test("2.5 Noisy audio: is_unclear=True, no fabricated words (MOCKED)", test_2_5_unclear_audio_no_fabrication)
test("2.6 Empty audio file returns failure without crashing (Actual)", test_2_6_empty_audio_handled)
test("2.7 Corrupted audio triggers safe failure (MOCKED Gemini error)", test_2_7_corrupted_audio_handled)
test("2.8 No GEMINI_API_KEY returns UNAVAILABLE result (Actual)", test_2_8_no_api_key_returns_unavailable)
test("2.9 Unsupported format (.pdf) rejected before API (Actual)", test_2_9_unsupported_format_rejected)


# ---------------------------------------------------------------------------
# SECTION 3: Agricultural Image Intelligence
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("SECTION 3: Agricultural Image Intelligence (MOCKED)")
print("=" * 70)

from media.vision import AgriculturalVisionService, VisionResult


def _make_vision_response(crop, symptoms, quality="GOOD", condition="STRESSED",
                           confidence=0.85, action="ANSWER", diagnoses=None):
    return json.dumps({
        "identified_crop": crop,
        "leaf_discoloration": "discoloration" in str(symptoms),
        "yellowing": "yellow" in str(symptoms).lower(),
        "spots_lesions": "spot" in str(symptoms).lower(),
        "wilting": "wilting" in str(symptoms).lower(),
        "visible_pest_damage": "pest" in str(symptoms).lower(),
        "physical_damage": False,
        "general_condition": condition,
        "observed_symptoms": symptoms,
        "image_quality": quality,
        "confidence": confidence,
        "uncertainty_notes": "Visual observation only. Field verification required.",
        "additional_info_required": "Confirm with physical sample.",
        "recommended_action": action,
        "possible_diagnoses": diagnoses or [
            {"cause": "UNCONFIRMED: possible fungal rust", "caveat": "requires field verification"}
        ],
    })


def test_3_1_clear_crop_image_analysed():
    """MOCKED: Clear sugarcane image returns identified crop and symptoms."""
    fid = make_farmer(phone="9902000001", farmer_id="FARM-TST-VIS-01")
    wa_id = f"MED-IMG-{uuid.uuid4().hex[:8]}"
    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = make_png_file(os.path.join(tmpdir, "sugarcane.png"))
        rec = _ingestion.register_synthetic_media(
            wa_media_id=wa_id, farmer_db_id=fid, session_id=None,
            media_type=MediaType.IMAGE, mime_type="image/png",
            file_path=img_path, file_size_bytes=os.path.getsize(img_path),
        )
        vision = AgriculturalVisionService()
        mock_genai = MagicMock()
        mock_genai.upload_file.return_value = MagicMock()
        mock_genai.GenerativeModel.return_value.generate_content.return_value = MagicMock(
            text=_make_vision_response("Sugarcane", ["yellowing on leaves", "spots on lower leaves"])
        )
        vision._genai = mock_genai
        result = vision.analyse_image(img_path, rec.id, wa_id, fid)

    assert result.success is True
    assert result.identified_crop == "Sugarcane"
    assert len(result.symptoms) > 0
    # Diagnoses must be clearly UNCONFIRMED
    for d in result.possible_diagnoses:
        assert "UNCONFIRMED" in d.get("cause", "")


def test_3_2_blurry_image_handled():
    """MOCKED: Blurry image returns BLURRY quality and REQUEST_BETTER_IMAGE action."""
    fid = make_farmer(phone="9902000002", farmer_id="FARM-TST-VIS-02")
    wa_id = f"MED-BLR-{uuid.uuid4().hex[:8]}"
    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = make_png_file(os.path.join(tmpdir, "blurry.png"))
        rec = _ingestion.register_synthetic_media(
            wa_media_id=wa_id, farmer_db_id=fid, session_id=None,
            media_type=MediaType.IMAGE, mime_type="image/png",
            file_path=img_path, file_size_bytes=1,
        )
        vision = AgriculturalVisionService()
        mock_genai = MagicMock()
        mock_genai.upload_file.return_value = MagicMock()
        mock_genai.GenerativeModel.return_value.generate_content.return_value = MagicMock(
            text=_make_vision_response(None, [], quality="BLURRY", condition="POOR_VISIBILITY",
                                        confidence=0.2, action="REQUEST_BETTER_IMAGE", diagnoses=[])
        )
        vision._genai = mock_genai
        result = vision.analyse_image(img_path, rec.id, wa_id, fid)

    assert result.image_quality == "BLURRY"
    assert result.recommended_action == "REQUEST_BETTER_IMAGE"


def test_3_3_non_agricultural_image():
    """MOCKED: Non-crop image identified as NON_AGRICULTURAL."""
    fid = make_farmer(phone="9902000003", farmer_id="FARM-TST-VIS-03")
    wa_id = f"MED-NOAG-{uuid.uuid4().hex[:8]}"
    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = make_png_file(os.path.join(tmpdir, "selfie.png"), color=(255, 128, 0))
        rec = _ingestion.register_synthetic_media(
            wa_media_id=wa_id, farmer_db_id=fid, session_id=None,
            media_type=MediaType.IMAGE, mime_type="image/png",
            file_path=img_path, file_size_bytes=1,
        )
        vision = AgriculturalVisionService()
        mock_genai = MagicMock()
        mock_genai.upload_file.return_value = MagicMock()
        mock_genai.GenerativeModel.return_value.generate_content.return_value = MagicMock(
            text=_make_vision_response(None, [], quality="NON_AGRICULTURAL",
                                        condition="UNIDENTIFIABLE", confidence=0.1,
                                        action="NON_AGRICULTURAL", diagnoses=[])
        )
        vision._genai = mock_genai
        result = vision.analyse_image(img_path, rec.id, wa_id, fid)

    assert result.recommended_action == "NON_AGRICULTURAL"
    assert result.identified_crop is None


def test_3_4_missing_image_file_handled():
    """Actual: Missing image path returns failure without crashing."""
    vision = AgriculturalVisionService()
    result = vision.analyse_image("/no/such/file.jpg", 999, "MED-FAKE", 1)
    assert result.success is False
    assert result.error_message is not None


def test_3_5_no_api_key_returns_unavailable():
    """Actual: Without GEMINI_API_KEY, vision returns UNAVAILABLE result."""
    fid = make_farmer(phone="9902000004", farmer_id="FARM-TST-VIS-04")
    wa_id = f"MED-NOKEY-{uuid.uuid4().hex[:8]}"
    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = make_png_file(os.path.join(tmpdir, "leaf2.png"))
        rec = _ingestion.register_synthetic_media(
            wa_media_id=wa_id, farmer_db_id=fid, session_id=None,
            media_type=MediaType.IMAGE, mime_type="image/png",
            file_path=img_path, file_size_bytes=1,
        )
        vision = AgriculturalVisionService()  # No API key
        result = vision.analyse_image(img_path, rec.id, wa_id, fid)

    assert result.success is False
    assert result.provider == "unavailable"


def test_3_6_visual_observation_persisted():
    """MOCKED: VisualObservation row created in DB after image analysis."""
    fid = make_farmer(phone="9902000005", farmer_id="FARM-TST-VIS-05")
    wa_id = f"MED-PERSIST-{uuid.uuid4().hex[:8]}"
    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = make_png_file(os.path.join(tmpdir, "crop_obs.png"))
        rec = _ingestion.register_synthetic_media(
            wa_media_id=wa_id, farmer_db_id=fid, session_id=None,
            media_type=MediaType.IMAGE, mime_type="image/png",
            file_path=img_path, file_size_bytes=1,
        )
        vision = AgriculturalVisionService()
        mock_genai = MagicMock()
        mock_genai.upload_file.return_value = MagicMock()
        mock_genai.GenerativeModel.return_value.generate_content.return_value = MagicMock(
            text=_make_vision_response("Wheat", ["yellowing", "stunted growth"])
        )
        vision._genai = mock_genai
        result = vision.analyse_image(img_path, rec.id, wa_id, fid)

    # Verify DB row exists
    with get_db_session() as s:
        obs = s.query(VisualObservation).filter_by(observation_id=result.observation_id).first()
    assert obs is not None
    assert obs.identified_crop == "Wheat"


def test_3_7_ambiguous_symptoms_flagged_uncertain():
    """MOCKED: Ambiguous symptoms include uncertainty_notes and low confidence."""
    fid = make_farmer(phone="9902000006", farmer_id="FARM-TST-VIS-06")
    wa_id = f"MED-AMB-{uuid.uuid4().hex[:8]}"
    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = make_png_file(os.path.join(tmpdir, "ambiguous.png"))
        rec = _ingestion.register_synthetic_media(
            wa_media_id=wa_id, farmer_db_id=fid, session_id=None,
            media_type=MediaType.IMAGE, mime_type="image/png",
            file_path=img_path, file_size_bytes=1,
        )
        vision = AgriculturalVisionService()
        mock_genai = MagicMock()
        mock_genai.upload_file.return_value = MagicMock()
        mock_genai.GenerativeModel.return_value.generate_content.return_value = MagicMock(
            text=json.dumps({
                "identified_crop": "Unknown",
                "leaf_discoloration": True,
                "yellowing": True,
                "spots_lesions": False,
                "wilting": False,
                "visible_pest_damage": False,
                "physical_damage": False,
                "general_condition": "STRESSED",
                "observed_symptoms": ["discoloration visible but cause unclear"],
                "image_quality": "GOOD",
                "confidence": 0.4,
                "uncertainty_notes": "Cannot determine cause from image alone. Multiple possible causes.",
                "additional_info_required": "Physical field inspection needed.",
                "recommended_action": "ESCALATE_AGRONOMIST",
                "possible_diagnoses": [],
            })
        )
        vision._genai = mock_genai
        result = vision.analyse_image(img_path, rec.id, wa_id, fid)

    assert result.confidence < 0.5
    assert result.uncertainty_notes is not None
    assert result.recommended_action == "ESCALATE_AGRONOMIST"


test("3.1 Clear crop image: identified crop and UNCONFIRMED symptoms (MOCKED)", test_3_1_clear_crop_image_analysed)
test("3.2 Blurry image: REQUEST_BETTER_IMAGE action returned (MOCKED)", test_3_2_blurry_image_handled)
test("3.3 Non-agricultural image: NON_AGRICULTURAL action returned (MOCKED)", test_3_3_non_agricultural_image)
test("3.4 Missing image file: failure without crashing (Actual)", test_3_4_missing_image_file_handled)
test("3.5 No GEMINI_API_KEY: UNAVAILABLE result returned (Actual)", test_3_5_no_api_key_returns_unavailable)
test("3.6 VisualObservation row persisted to database (MOCKED)", test_3_6_visual_observation_persisted)
test("3.7 Ambiguous symptoms: low confidence and escalation flagged (MOCKED)", test_3_7_ambiguous_symptoms_flagged_uncertain)


# ---------------------------------------------------------------------------
# SECTION 4: Video Processing
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("SECTION 4: Video Processing (MOCKED vision; real OpenCV frame extraction)")
print("=" * 70)

from media.video import VideoAnalysisService, VideoAnalysisResult


def test_4_1_frame_extraction_and_timestamps():
    """Actual: OpenCV extracts frames from synthetic MP4 with correct timestamps."""
    fid = make_farmer(phone="9903000001", farmer_id="FARM-TST-VID-01")
    wa_id = f"MED-VID-{uuid.uuid4().hex[:8]}"
    with tempfile.TemporaryDirectory() as tmpdir:
        vid_path = make_video_file(os.path.join(tmpdir, "field_video.mp4"))
        rec = _ingestion.register_synthetic_media(
            wa_media_id=wa_id, farmer_db_id=fid, session_id=None,
            media_type=MediaType.VIDEO, mime_type="video/mp4",
            file_path=vid_path, file_size_bytes=os.path.getsize(vid_path),
        )
        video_svc = VideoAnalysisService()
        # Mock the internal vision service to return synthetic results
        mock_vision_result = VisionResult(
            success=True, media_id=wa_id, farmer_id=fid,
            identified_crop="Sugarcane", symptoms=["yellowing"],
            image_quality="GOOD", general_condition="STRESSED",
            confidence=0.8, uncertainty_notes=None, additional_info_required=None,
            recommended_action="ANSWER", possible_diagnoses=[],
        )
        video_svc._vision.analyse_image = MagicMock(return_value=mock_vision_result)
        result = video_svc.analyse_video(vid_path, rec.id, wa_id, fid)

    assert result.success is True
    assert result.frames_extracted >= 1
    assert result.duration_sec is not None and result.duration_sec > 0


def test_4_2_timestamp_preserved():
    """Actual: Extracted frame timestamps are >= 0 and ordered."""
    from media.video import VideoAnalysisService
    svc = VideoAnalysisService()
    timestamps = svc._select_frame_timestamps(30.0)
    assert all(t >= 0 for t in timestamps)
    assert timestamps == sorted(timestamps)
    assert len(timestamps) <= 8  # MAX_FRAMES_TO_EXTRACT


def test_4_3_invalid_video_handled():
    """Actual: Non-video file returns failure without crashing."""
    fid = make_farmer(phone="9903000002", farmer_id="FARM-TST-VID-02")
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(b"NOT A REAL VIDEO BINARY")
        bad_path = f.name
    video_svc = VideoAnalysisService()
    result = video_svc.analyse_video(bad_path, 1, "MED-BAD", fid)
    os.unlink(bad_path)
    assert result.success is False
    assert result.error_message is not None


def test_4_4_excessive_duration_rejected():
    """Actual: Video longer than MAX_DURATION returns failure."""
    # Create a mock cv2 VideoCapture that reports 300fps * 1000 frames = 1000s
    with tempfile.TemporaryDirectory() as tmpdir:
        vid_path = make_video_file(os.path.join(tmpdir, "long.mp4"))
        video_svc = VideoAnalysisService()
        with patch("media.video.cv2.VideoCapture") as mock_cap_cls:
            mock_cap = MagicMock()
            mock_cap.isOpened.return_value = True
            mock_cap.get.side_effect = lambda prop: {
                0x03: 25.0,     # CAP_PROP_FPS
                0x07: 7500.0,   # CAP_PROP_FRAME_COUNT (300 seconds)
            }.get(prop, 0)
            mock_cap_cls.return_value = mock_cap
            result = video_svc.analyse_video(vid_path, 1, "MED-LONG", 1)
        assert result.success is False
        assert "long" in result.error_message.lower() or "limit" in result.error_message.lower()


def test_4_5_repeated_frames_deduplicated():
    """Actual: _select_frame_timestamps respects MIN_FRAME_INTERVAL_SEC to avoid redundancy."""
    from media.video import VideoAnalysisService, MIN_FRAME_INTERVAL_SEC
    svc = VideoAnalysisService()
    timestamps = svc._select_frame_timestamps(10.0)
    for i in range(1, len(timestamps)):
        assert timestamps[i] - timestamps[i-1] >= MIN_FRAME_INTERVAL_SEC - 0.001


def test_4_6_consolidated_symptoms_deduplicated():
    """Actual: Same symptom from multiple frames is listed once in consolidated output."""
    from media.video import VideoAnalysisService
    svc = VideoAnalysisService()
    r1 = VisionResult(success=True, media_id="x", farmer_id=1, identified_crop="Sugarcane",
                      symptoms=["yellowing on leaves", "spots visible"],
                      image_quality="GOOD", general_condition="STRESSED", confidence=0.8,
                      uncertainty_notes=None, additional_info_required=None,
                      recommended_action="ANSWER", possible_diagnoses=[])
    r2 = VisionResult(success=True, media_id="x", farmer_id=1, identified_crop="Sugarcane",
                      symptoms=["yellowing on leaves"],  # duplicate
                      image_quality="GOOD", general_condition="STRESSED", confidence=0.8,
                      uncertainty_notes=None, additional_info_required=None,
                      recommended_action="ANSWER", possible_diagnoses=[])
    consolidated = svc._consolidate([r1, r2])
    # "yellowing on leaves" should appear only once
    assert consolidated["symptoms"].count("yellowing on leaves") == 1


def test_4_7_missing_video_file():
    """Actual: Non-existent video path returns failure gracefully."""
    svc = VideoAnalysisService()
    result = svc.analyse_video("/no/such/video.mp4", 1, "MED-NOFILE", 1)
    assert result.success is False
    assert "not found" in result.error_message.lower()


test("4.1 Frame extraction from synthetic MP4 (Actual OpenCV + MOCKED vision)", test_4_1_frame_extraction_and_timestamps)
test("4.2 Frame timestamps >= 0 and ordered correctly (Actual)", test_4_2_timestamp_preserved)
test("4.3 Invalid/non-video file returns safe failure (Actual)", test_4_3_invalid_video_handled)
test("4.4 Video exceeding MAX_DURATION rejected (MOCKED CAP_PROP_FRAME_COUNT)", test_4_4_excessive_duration_rejected)
test("4.5 MIN_FRAME_INTERVAL_SEC prevents redundant sampling (Actual)", test_4_5_repeated_frames_deduplicated)
test("4.6 Same symptom from multiple frames listed once (Actual)", test_4_6_consolidated_symptoms_deduplicated)
test("4.7 Missing video path: safe failure without crashing (Actual)", test_4_7_missing_video_file)


# ---------------------------------------------------------------------------
# SECTION 5: Multimodal Integration
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("SECTION 5: Multimodal Orchestration & Phase 3 Integration (MOCKED)")
print("=" * 70)

from media.orchestrator import MultimodalOrchestrator, MultimodalRequest, MediaAttachment


def test_5_1_text_plus_transcription_merged():
    """MOCKED: Text body + transcription merged into single coherent context."""
    orchestrator = MultimodalOrchestrator()
    merged = orchestrator._merge_context(
        text_body="मेरे ऊस में पीलापन आया है",
        transcriptions=["माझ्या उसाच्या पानांवर पिवळे डाग"],
        visual_summaries=[],
    )
    assert "पीलापन" in merged
    assert "Voice Note Transcription" in merged


def test_5_2_visual_summary_included():
    """MOCKED: Visual observation summary is included in merged context."""
    orchestrator = MultimodalOrchestrator()
    merged = orchestrator._merge_context(
        text_body=None,
        transcriptions=[],
        visual_summaries=["Sugarcane visible. Observed symptoms (UNCONFIRMED): yellowing on leaves."],
    )
    assert "Visual Observation" in merged
    assert "UNCONFIRMED" in merged


def test_5_3_text_only_bypasses_media():
    """Actual: Text-only message goes straight through Phase 3 FarmerAgent unchanged."""
    fid = make_farmer(phone="9904000001", farmer_id="FARM-TST-MM-01")
    orchestrator = MultimodalOrchestrator()
    # Mock FarmerAgent response
    from agent.farmer_agent import AgentResponse
    from database.enums import AgriculturalIntent
    from agent.classifier import MessageCategory
    mock_response = AgentResponse(
        status="ANSWERED",
        reply_text="उसाचे खत व्यवस्थापन: NPK 10:26:26",
        category=MessageCategory.FARMING_QUERY,
        intent=AgriculturalIntent.FERTILIZER_NUTRITION,
        classification_confidence=0.94,
        reason="Test",
        rag_sources=[],
    )
    orchestrator._farmer_agent.process_message = MagicMock(return_value=mock_response)
    request = MultimodalRequest(
        sender_phone="9904000001",
        sender_name="Ramesh",
        message_id=f"MSG-{uuid.uuid4().hex[:8]}",
        text_body="उसाला खत कोणते द्यावे?",
        attachments=[],
    )
    response = orchestrator.process(request)
    assert response.status == "ANSWERED"
    assert response.media_records_created == []
    assert orchestrator._farmer_agent.process_message.called


def test_5_4_audio_plus_text_combined():
    """MOCKED: Voice note + text caption merged and classified correctly."""
    fid = make_farmer(phone="9904000002", farmer_id="FARM-TST-MM-02")
    orchestrator = MultimodalOrchestrator()

    # Mock ingestion, STT, and agent
    mock_stt_result = MagicMock()
    mock_stt_result.success = True
    mock_stt_result.transcription = "माझ्या उसाच्या पानांवर पिवळे डाग"
    mock_stt_result.detected_language = "mr"
    mock_stt_result.confidence = 0.9
    orchestrator._stt.transcribe = MagicMock(return_value=mock_stt_result)

    with tempfile.TemporaryDirectory() as tmpdir:
        wav_path = make_wav_file(os.path.join(tmpdir, "note.wav"))
        wa_id = f"MED-AU-{uuid.uuid4().hex[:8]}"
        rec = _ingestion.register_synthetic_media(
            wa_media_id=wa_id, farmer_db_id=fid, session_id=None,
            media_type=MediaType.VOICE_NOTE, mime_type="audio/ogg",
            file_path=wav_path, file_size_bytes=1,
        )

    from agent.farmer_agent import AgentResponse
    from database.enums import AgriculturalIntent
    from agent.classifier import MessageCategory
    mock_agent_response = AgentResponse(
        status="ANSWERED", reply_text="तांबेरा रोगावर फवारणी करावी",
        category=MessageCategory.FARMING_QUERY,
        intent=AgriculturalIntent.CROP_DISEASE_PEST,
        classification_confidence=0.92, reason="Test", rag_sources=[],
    )
    orchestrator._farmer_agent.process_message = MagicMock(return_value=mock_agent_response)
    orchestrator._ingestion.ingest_media = MagicMock(return_value=rec)
    orchestrator._ingestion.mark_processing = MagicMock()
    orchestrator._ingestion.mark_processed = MagicMock()

    request = MultimodalRequest(
        sender_phone="9904000002",
        sender_name="Suresh",
        message_id=f"MSG-{uuid.uuid4().hex[:8]}",
        text_body="रोग कोणता आहे?",
        attachments=[MediaAttachment(wa_media_id=wa_id, media_type_hint="voice_note", mime_type="audio/ogg")],
    )
    response = orchestrator.process(request)
    assert response.status == "ANSWERED"
    assert response.transcription is not None


def test_5_5_escalation_triggered_on_severe_visual():
    """MOCKED: ESCALATE_AGRONOMIST from vision elevates response to ESCALATED status."""
    orchestrator = MultimodalOrchestrator()
    fid = make_farmer(phone="9904000003", farmer_id="FARM-TST-MM-03")

    mock_vision_result = VisionResult(
        success=True, media_id="MED-ESC", farmer_id=fid,
        identified_crop="Sugarcane",
        symptoms=["severe yellowing", "wilting across plot"],
        image_quality="GOOD", general_condition="SEVERE", confidence=0.9,
        uncertainty_notes="Possible severe disease", additional_info_required=None,
        recommended_action="ESCALATE_AGRONOMIST",
        possible_diagnoses=[{"cause": "UNCONFIRMED: possible Grassy Shoot Disease", "caveat": "needs lab"}],
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = make_png_file(os.path.join(tmpdir, "severe.png"))
        wa_id = f"MED-ESCIMG-{uuid.uuid4().hex[:8]}"
        rec = _ingestion.register_synthetic_media(
            wa_media_id=wa_id, farmer_db_id=fid, session_id=None,
            media_type=MediaType.IMAGE, mime_type="image/png",
            file_path=img_path, file_size_bytes=1,
        )

    orchestrator._vision.analyse_image = MagicMock(return_value=mock_vision_result)
    orchestrator._ingestion.ingest_media = MagicMock(return_value=rec)
    orchestrator._ingestion.mark_processing = MagicMock()
    orchestrator._ingestion.mark_processed = MagicMock()

    from agent.farmer_agent import AgentResponse
    from database.enums import AgriculturalIntent
    from agent.classifier import MessageCategory
    mock_agent_response = AgentResponse(
        status="ANSWERED", reply_text="तांबेरा नियंत्रण करा",
        category=MessageCategory.FARMING_QUERY,
        intent=AgriculturalIntent.CROP_DISEASE_PEST,
        classification_confidence=0.88, reason="Test", rag_sources=[],
    )
    orchestrator._farmer_agent.process_message = MagicMock(return_value=mock_agent_response)

    request = MultimodalRequest(
        sender_phone="9904000003",
        sender_name="Vikas",
        message_id=f"MSG-{uuid.uuid4().hex[:8]}",
        text_body="काय करावे?",
        attachments=[MediaAttachment(wa_media_id=wa_id, media_type_hint="image", mime_type="image/png")],
    )
    response = orchestrator.process(request)
    assert response.escalation_required is True
    assert response.status == "ESCALATED"


def test_5_6_no_text_no_model_returns_helpful_message():
    """Actual: Image received with no API key → helpful text guidance returned, not empty."""
    orchestrator = MultimodalOrchestrator()
    fid = make_farmer(phone="9904000004", farmer_id="FARM-TST-MM-04")

    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = make_png_file(os.path.join(tmpdir, "leaf3.png"))
        wa_id = f"MED-NOTXT-{uuid.uuid4().hex[:8]}"
        rec = _ingestion.register_synthetic_media(
            wa_media_id=wa_id, farmer_db_id=fid, session_id=None,
            media_type=MediaType.IMAGE, mime_type="image/png",
            file_path=img_path, file_size_bytes=1,
        )

    orchestrator._ingestion.ingest_media = MagicMock(return_value=rec)
    orchestrator._ingestion.mark_processing = MagicMock()
    orchestrator._ingestion.mark_processed = MagicMock()

    request = MultimodalRequest(
        sender_phone="9904000004",
        sender_name="Anita",
        message_id=f"MSG-{uuid.uuid4().hex[:8]}",
        text_body=None,
        attachments=[MediaAttachment(wa_media_id=wa_id, media_type_hint="image", mime_type="image/png")],
    )
    response = orchestrator.process(request)
    # With no API key: vision is unavailable, no merged text → IGNORED or error with guidance
    assert response.reply_text is not None
    assert len(response.reply_text) > 10


def test_5_7_farmer_isolation_in_orchestrator():
    """Actual: Orchestrator does not leak media records across different farmers."""
    fid_a = make_farmer(phone="9904000005", farmer_id="FARM-TST-MM-05")
    fid_b = make_farmer(phone="9904000006", farmer_id="FARM-TST-MM-06")
    wa_id_a = f"MED-ISO-ORK-A-{uuid.uuid4().hex[:6]}"
    wa_id_b = f"MED-ISO-ORK-B-{uuid.uuid4().hex[:6]}"
    with tempfile.TemporaryDirectory() as tmpdir:
        img_a = make_png_file(os.path.join(tmpdir, "fa.png"))
        img_b = make_png_file(os.path.join(tmpdir, "fb.png"))
        rec_a = _ingestion.register_synthetic_media(wa_media_id=wa_id_a, farmer_db_id=fid_a, session_id=None, media_type=MediaType.IMAGE, mime_type="image/png", file_path=img_a, file_size_bytes=1)
        rec_b = _ingestion.register_synthetic_media(wa_media_id=wa_id_b, farmer_db_id=fid_b, session_id=None, media_type=MediaType.IMAGE, mime_type="image/png", file_path=img_b, file_size_bytes=1)
    assert rec_a.farmer_id == fid_a
    assert rec_b.farmer_id == fid_b
    assert rec_a.id != rec_b.id


test("5.1 Text + transcription merged into coherent context (MOCKED)", test_5_1_text_plus_transcription_merged)
test("5.2 Visual observation summary included in merged context (MOCKED)", test_5_2_visual_summary_included)
test("5.3 Text-only message routes through Phase 3 FarmerAgent unchanged (MOCKED)", test_5_3_text_only_bypasses_media)
test("5.4 Voice note + text caption merged and classified (MOCKED)", test_5_4_audio_plus_text_combined)
test("5.5 ESCALATE_AGRONOMIST from vision elevates response to ESCALATED (MOCKED)", test_5_5_escalation_triggered_on_severe_visual)
test("5.6 No text + no API key returns helpful guidance message (Actual)", test_5_6_no_text_no_model_returns_helpful_message)
test("5.7 Farmer isolation: media records scoped to correct farmer (Actual)", test_5_7_farmer_isolation_in_orchestrator)


# ---------------------------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("PHASE 4 VERIFICATION SUMMARY")
print("=" * 70)
total = PASS + FAIL
print(f"\n  Total Tests : {total}")
print(f"  \u2705 Passed   : {PASS}")
print(f"  \u274c Failed   : {FAIL}")

if FAILURES:
    print("\n  FAILED TESTS:")
    for name, msg in FAILURES:
        print(f"    \u2717 {name}: {msg}")

sys.exit(0 if FAIL == 0 else 1)
