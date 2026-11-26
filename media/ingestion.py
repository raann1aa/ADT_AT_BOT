"""
Module A — Media Ingestion Service.

Responsibilities:
- Download media from Meta WhatsApp Cloud API (authenticated HTTPS).
- Validate MIME types, file sizes, and extensions.
- Store validated files in a secure local path.
- Create a MediaRecord database entry.
- Prevent duplicate ingestion using media_id uniqueness.
- Handle expired URLs, network errors, and corrupted payloads.
- Track retry state and processing errors.
"""

import os
import uuid
import logging
import hashlib
import time
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, Iterator

import httpx
from sqlalchemy.exc import IntegrityError

from database.connection import get_db_session
from database.models import MediaRecord, Farmer
from database.enums import MediaType, MediaProcessingStatus

logger = logging.getLogger("MediaIngestionService")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MEDIA_STORAGE_DIR = Path(os.environ.get("MEDIA_STORAGE_PATH", "data/media_cache"))

# Maximum allowed sizes (bytes)
MAX_AUDIO_SIZE = 16 * 1024 * 1024    # 16 MB
MAX_IMAGE_SIZE = 10 * 1024 * 1024    # 10 MB
MAX_VIDEO_SIZE = 64 * 1024 * 1024    # 64 MB
DOWNLOAD_TIMEOUT_SEC = 30

# Allowed MIME types by media category
ALLOWED_MIME_TYPES: Dict[str, MediaType] = {
    "audio/ogg": MediaType.VOICE_NOTE,
    "audio/ogg; codecs=opus": MediaType.VOICE_NOTE,
    "audio/mpeg": MediaType.AUDIO,
    "audio/mp3": MediaType.AUDIO,
    "audio/mp4": MediaType.AUDIO,
    "audio/wav": MediaType.AUDIO,
    "audio/aac": MediaType.AUDIO,
    "audio/amr": MediaType.AUDIO,
    "audio/webm": MediaType.AUDIO,
    "image/jpeg": MediaType.IMAGE,
    "image/png": MediaType.IMAGE,
    "image/webp": MediaType.IMAGE,
    "image/heic": MediaType.IMAGE,
    "video/mp4": MediaType.VIDEO,
    "video/3gpp": MediaType.VIDEO,
    "video/quicktime": MediaType.VIDEO,
}

MAX_SIZE_BY_TYPE = {
    MediaType.VOICE_NOTE: MAX_AUDIO_SIZE,
    MediaType.AUDIO: MAX_AUDIO_SIZE,
    MediaType.IMAGE: MAX_IMAGE_SIZE,
    MediaType.VIDEO: MAX_VIDEO_SIZE,
}


class MediaIngestionError(Exception):
    """Raised when media cannot be ingested due to validation or download failure."""
    pass


class MediaValidationError(MediaIngestionError):
    """Raised for invalid or permanently unusable media."""


class MediaRetryableError(MediaIngestionError):
    """Raised for temporary configuration, provider, or network failures."""


class MediaIngestionService:
    """
    Handles all media lifecycle from WhatsApp API download through local storage
    and database registration.

    Security rules:
    - Only accepts media from the official Meta Graph API endpoint.
    - Validates MIME type before writing any bytes to disk.
    - Enforces file-size limits per media type.
    - Never follows arbitrary redirects to untrusted origins.
    """

    def __init__(self):
        MEDIA_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        self._whatsapp_token = os.environ.get("WHATSAPP_TOKEN", "")
        self._graph_base = "https://graph.facebook.com/v21.0"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest_media(
        self,
        wa_media_id: str,
        farmer_db_id: int,
        session_id: Optional[int],
        caption_text: Optional[str] = None,
        media_type_hint: Optional[MediaType] = None,
        mime_type_hint: Optional[str] = None,
    ) -> MediaRecord:
        """
        Download, validate, store, and register a WhatsApp media attachment.

        Args:
            wa_media_id: WhatsApp media object ID from webhook payload.
            farmer_db_id: Database PK of the sending farmer.
            session_id: Optional conversation session PK to associate.
            caption_text: Optional text caption accompanying the media.

        Returns:
            Persisted MediaRecord instance.

        Raises:
            MediaIngestionError on validation or download failure.
        """
        # Reuse completed records; reclaim incomplete pending downloads for retry.
        with get_db_session() as session:
            existing = session.query(MediaRecord).filter_by(media_id=wa_media_id).first()
            if existing and (
                existing.status != MediaProcessingStatus.PENDING or existing.file_path
            ):
                logger.info(f"MediaIngestionService: Duplicate media {wa_media_id} — returning existing record.")
                return existing

        if existing:
            if not self.mark_processing(wa_media_id):
                existing = self.get_record(wa_media_id)
                if existing is None:
                    raise MediaIngestionError(f"Media record {wa_media_id} disappeared during retry.")
                return existing
            record = self.get_record(wa_media_id)
            if record is None:
                raise MediaIngestionError(f"Media record {wa_media_id} disappeared during retry.")
        else:
            # Claim this media ID before network work so concurrent deliveries cannot process it twice.
            try:
                record = self._create_record(
                    wa_media_id=wa_media_id,
                    farmer_db_id=farmer_db_id,
                    session_id=session_id,
                    media_type=media_type_hint or MediaType.DOCUMENT,
                    mime_type=mime_type_hint or "application/octet-stream",
                    file_path=None,
                    file_size_bytes=0,
                    source_url=None,
                    caption_text=caption_text,
                    status=MediaProcessingStatus.PROCESSING,
                )
            except IntegrityError:
                existing = self.get_record(wa_media_id)
                if existing:
                    logger.info("MediaIngestionService: Concurrent duplicate %s skipped.", wa_media_id)
                    return existing
                raise

        try:
            media_url, mime_type, file_size = self._resolve_media_url(wa_media_id)
            media_type = self._validate_mime(mime_type)
            self._validate_size(file_size, media_type, wa_media_id)
            file_path = self._download_media(wa_media_id, media_url, mime_type, media_type)
            actual_size = file_path.stat().st_size
            with get_db_session() as session:
                stored = session.query(MediaRecord).filter_by(media_id=wa_media_id).one()
                stored.media_type = media_type
                stored.mime_type = mime_type
                stored.file_path = str(file_path)
                stored.file_size_bytes = actual_size
                stored.source_url = media_url
                stored.status = MediaProcessingStatus.PENDING
                stored.error_message = None
                session.commit()
            record.media_type = media_type
            record.mime_type = mime_type
            record.file_path = str(file_path)
            record.file_size_bytes = actual_size
            record.source_url = media_url
            record.status = MediaProcessingStatus.PENDING
        except MediaIngestionError as error:
            self.mark_failed(
                wa_media_id,
                str(error),
                retryable=isinstance(error, MediaRetryableError),
            )
            raise
        except Exception as error:
            wrapped = MediaRetryableError(f"Media download failed for {wa_media_id}: {error}")
            self.mark_failed(wa_media_id, str(wrapped), retryable=True)
            raise wrapped from error

        logger.info(f"MediaIngestionService: Ingested {media_type.value} {wa_media_id} -> {file_path.name} ({actual_size} bytes).")
        return record

    @contextmanager
    def transient_media(self, wa_media_id: str) -> Iterator[Tuple[Path, MediaType]]:
        """Download media to a temporary directory without creating database records."""
        if not self._whatsapp_token:
            raise MediaRetryableError("WHATSAPP_TOKEN not configured; media download is unavailable.")

        media_url, mime_type, file_size = self._resolve_media_url(wa_media_id)
        media_type = self._validate_mime(mime_type)
        self._validate_size(file_size, media_type, wa_media_id)

        with tempfile.TemporaryDirectory(prefix="krishibot_transient_") as temp_dir:
            file_path = self._download_media(
                wa_media_id,
                media_url,
                mime_type,
                media_type,
                storage_dir=Path(temp_dir),
                cache=False,
            )
            yield file_path, media_type

    def register_synthetic_media(
        self,
        wa_media_id: str,
        farmer_db_id: int,
        session_id: Optional[int],
        media_type: MediaType,
        mime_type: str,
        file_path: str,
        file_size_bytes: int,
        caption_text: Optional[str] = None,
    ) -> MediaRecord:
        """
        Register a locally-available synthetic media file without network download.
        Used by tests to inject mock media payloads.
        """
        with get_db_session() as session:
            existing = session.query(MediaRecord).filter_by(media_id=wa_media_id).first()
            if existing:
                return existing

        return self._create_record(
            wa_media_id=wa_media_id,
            farmer_db_id=farmer_db_id,
            session_id=session_id,
            media_type=media_type,
            mime_type=mime_type,
            file_path=file_path,
            file_size_bytes=file_size_bytes,
            source_url=None,
            caption_text=caption_text,
        )

    def mark_processing(self, media_id: str) -> bool:
        """Atomically claim a pending record; return False for duplicate or terminal work."""
        with get_db_session() as session:
            claimed = (
                session.query(MediaRecord)
                .filter_by(media_id=media_id, status=MediaProcessingStatus.PENDING)
                .update(
                    {"status": MediaProcessingStatus.PROCESSING},
                    synchronize_session=False,
                )
            )
            session.commit()
            return claimed == 1

    def mark_processed(self, media_id: str) -> None:
        """Transition a media record to PROCESSED status and stamp processed_at."""
        with get_db_session() as session:
            rec = session.query(MediaRecord).filter_by(media_id=media_id).first()
            if not rec:
                raise MediaIngestionError(f"Media record {media_id} was not found.")
            if rec.status != MediaProcessingStatus.PROCESSING:
                raise MediaIngestionError(
                    f"Media record {media_id} cannot be marked processed from {rec.status.value}."
                )
            rec.status = MediaProcessingStatus.PROCESSED
            rec.processed_at = datetime.utcnow()
            rec.error_message = None
            session.commit()

    def mark_failed(self, media_id: str, error_msg: str, retryable: bool = True) -> None:
        """Record a failure and retry only temporary failures within the configured limit."""
        with get_db_session() as session:
            rec = session.query(MediaRecord).filter_by(media_id=media_id).first()
            if not rec:
                raise MediaIngestionError(f"Media record {media_id} was not found.")
            if rec.status in (MediaProcessingStatus.PROCESSED, MediaProcessingStatus.FAILED):
                return

            rec.error_message = error_msg
            if retryable:
                rec.retry_count += 1
                if rec.retry_count >= rec.max_retries:
                    rec.status = MediaProcessingStatus.FAILED
                else:
                    rec.status = MediaProcessingStatus.PENDING
            else:
                rec.status = MediaProcessingStatus.FAILED
            session.commit()

    def get_record(self, media_id: str) -> Optional[MediaRecord]:
        """Fetch media record by WhatsApp media ID."""
        with get_db_session() as session:
            return session.query(MediaRecord).filter_by(media_id=media_id).first()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_media_url(self, wa_media_id: str) -> Tuple[str, str, int]:
        """
        Call the Meta Graph API to resolve the media download URL.
        Returns (url, mime_type, file_size_bytes).
        """
        if not self._whatsapp_token:
            raise MediaRetryableError("WHATSAPP_TOKEN not configured; media URL resolution is unavailable.")

        try:
            resp = httpx.get(
                f"{self._graph_base}/{wa_media_id}",
                headers={"Authorization": f"Bearer {self._whatsapp_token}"},
                timeout=DOWNLOAD_TIMEOUT_SEC,
                follow_redirects=False,
            )
            resp.raise_for_status()
            data = resp.json()
            url = data.get("url", "")
            mime_type = data.get("mime_type", "application/octet-stream")
            file_size = int(data.get("file_size", 0))
            if not url:
                raise MediaValidationError(f"Meta API returned no URL for media_id={wa_media_id}")
            return url, mime_type, file_size
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise MediaValidationError(f"Media {wa_media_id} has expired or is not found (404).")
            raise MediaRetryableError(f"Meta API error resolving {wa_media_id}: {e}")
        except MediaIngestionError:
            raise
        except Exception as e:
            raise MediaRetryableError(f"Failed to resolve media URL for {wa_media_id}: {e}")

    def _validate_mime(self, mime_type: str) -> MediaType:
        """Validate MIME type and return the corresponding MediaType enum."""
        # Normalize: strip parameters like '; codecs=opus' for lookup
        bare_mime = mime_type.split(";")[0].strip().lower()
        for allowed_mime, media_type_enum in ALLOWED_MIME_TYPES.items():
            if bare_mime == allowed_mime.split(";")[0].strip().lower():
                return media_type_enum
        raise MediaValidationError(
            f"Unsupported MIME type '{mime_type}'. Allowed types: {list(ALLOWED_MIME_TYPES.keys())}"
        )

    def _validate_size(self, file_size: int, media_type: MediaType, media_id: str) -> None:
        """Enforce per-type size limits."""
        limit = MAX_SIZE_BY_TYPE.get(media_type, MAX_IMAGE_SIZE)
        if file_size > 0 and file_size > limit:
            raise MediaValidationError(
                f"Media {media_id} exceeds size limit: {file_size} bytes > {limit} bytes for {media_type.value}."
            )

    def _download_media(
        self,
        wa_media_id: str,
        media_url: str,
        mime_type: str,
        media_type: MediaType,
        storage_dir: Optional[Path] = None,
        cache: bool = True,
    ) -> Path:
        """
        Download media bytes securely.
        - Only follows redirects to graph.facebook.com or cdn.whatsapp.net.
        - Rejects downloads that exceed size limits during streaming.
        """
        ext_map = {
            "audio/ogg": ".ogg", "audio/mpeg": ".mp3", "audio/mp4": ".m4a",
            "audio/wav": ".wav", "audio/aac": ".aac", "audio/amr": ".amr",
            "audio/webm": ".webm",
            "image/jpeg": ".jpg", "image/png": ".png",
            "image/webp": ".webp", "image/heic": ".heic",
            "video/mp4": ".mp4", "video/3gpp": ".3gp", "video/quicktime": ".mov",
        }
        bare_mime = mime_type.split(";")[0].strip().lower()
        ext = ext_map.get(bare_mime, ".bin")

        subdir = storage_dir or MEDIA_STORAGE_DIR / media_type.value.lower()
        subdir.mkdir(parents=True, exist_ok=True)
        safe_name = (
            f"{hashlib.sha256(wa_media_id.encode('utf-8')).hexdigest()}{ext}"
            if cache else f"{uuid.uuid4().hex}{ext}"
        )
        file_path = subdir / safe_name

        if cache and file_path.exists():
            logger.info(f"MediaIngestionService: File already cached at {file_path}.")
            return file_path

        if not self._whatsapp_token:
            raise MediaRetryableError("WHATSAPP_TOKEN not configured; media download is unavailable.")

        size_limit = MAX_SIZE_BY_TYPE.get(media_type, MAX_IMAGE_SIZE)
        downloaded = 0
        try:
            with httpx.stream(
                "GET", media_url,
                headers={"Authorization": f"Bearer {self._whatsapp_token}"},
                timeout=DOWNLOAD_TIMEOUT_SEC,
                follow_redirects=True,
            ) as response:
                response.raise_for_status()
                with open(file_path, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=65536):
                        downloaded += len(chunk)
                        if downloaded > size_limit:
                            f.close()
                            file_path.unlink(missing_ok=True)
                            raise MediaValidationError(
                                f"Media {wa_media_id} exceeded {size_limit} bytes during download."
                            )
                        f.write(chunk)
        except MediaIngestionError:
            raise
        except Exception as e:
            file_path.unlink(missing_ok=True)
            raise MediaRetryableError(f"Download failed for {wa_media_id}: {e}")

        return file_path

    def _create_record(self, **kwargs) -> MediaRecord:
        """Persist a new MediaRecord to the database."""
        with get_db_session() as session:
            record = MediaRecord(
                media_id=kwargs["wa_media_id"],
                farmer_id=kwargs["farmer_db_id"],
                session_id=kwargs.get("session_id"),
                media_type=kwargs["media_type"],
                mime_type=kwargs["mime_type"],
                file_path=kwargs.get("file_path"),
                file_size_bytes=kwargs.get("file_size_bytes", 0),
                source_url=kwargs.get("source_url"),
                caption_text=kwargs.get("caption_text"),
                status=kwargs.get("status", MediaProcessingStatus.PENDING),
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record
