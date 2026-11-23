"""
Idempotency and Message Deduplication Repository.
Provides database-backed atomic message locking and status tracking
to prevent duplicate webhook processing across application restarts.
"""

import logging
from typing import Optional
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from database.models import WebhookEvent
from database.enums import WebhookEventStatus

logger = logging.getLogger("IdempotencyRepository")


class IdempotencyRepository:
    """Persistent ledger for incoming webhook events."""

    def __init__(self, session: Session):
        self.session = session

    def claim_message(
        self,
        message_id: str,
        sender_phone: str,
        event_type: str = "message",
        payload_hash: Optional[str] = None,
        stale_threshold_seconds: Optional[int] = None,
        allow_failed_retry: bool = False
    ) -> bool:
        """
        Attempts to claim an incoming webhook message ID.
        Returns:
            True if the message is new (or eligible for crash recovery) and claimed for processing.
            False if the message ID already exists and is active/completed (duplicate delivery).
        """
        if not message_id:
            return False

        # Fast select check first
        stmt = select(WebhookEvent).where(WebhookEvent.message_id == message_id)
        existing = self.session.scalars(stmt).first()
        if existing:
            # Recovery Check 1: Worker crashed while in PROCESSING status
            if (
                existing.status == WebhookEventStatus.PROCESSING
                and stale_threshold_seconds is not None
            ):
                age_seconds = (datetime.now() - existing.received_at).total_seconds()
                if age_seconds > stale_threshold_seconds:
                    logger.warning(
                        f"Crash recovery: Reclaiming stale message {message_id} "
                        f"(stuck in PROCESSING for {age_seconds:.1f}s > {stale_threshold_seconds}s)."
                    )
                    existing.received_at = datetime.now()
                    self.session.flush()
                    return True

            # Recovery Check 2: Explicit retry of previously FAILED event
            if existing.status == WebhookEventStatus.FAILED and allow_failed_retry:
                logger.info(f"Retry allowed: Reclaiming FAILED message {message_id} for recovery.")
                existing.status = WebhookEventStatus.PROCESSING
                existing.error_message = None
                existing.received_at = datetime.now()
                self.session.flush()
                return True

            logger.info(f"Persistent dedup: Message ID {message_id} already exists (status: {existing.status.value}).")
            return False

        # Attempt atomic insert
        try:
            event = WebhookEvent(
                message_id=message_id,
                sender_phone=sender_phone,
                event_type=event_type,
                payload_hash=payload_hash,
                status=WebhookEventStatus.PROCESSING
            )
            self.session.add(event)
            self.session.flush()
            return True
        except IntegrityError:
            self.session.rollback()
            logger.info(f"Persistent dedup race condition caught: Message ID {message_id} duplicate rejected.")
            return False

    def complete_message(self, message_id: str) -> None:
        """Marks a claimed webhook event as successfully completed."""
        stmt = select(WebhookEvent).where(WebhookEvent.message_id == message_id)
        event = self.session.scalars(stmt).first()
        if event:
            event.status = WebhookEventStatus.COMPLETED
            event.completed_at = datetime.now()
            self.session.flush()

    def fail_message(self, message_id: str, error_message: str) -> None:
        """Records an execution failure for a claimed webhook event."""
        stmt = select(WebhookEvent).where(WebhookEvent.message_id == message_id)
        event = self.session.scalars(stmt).first()
        if event:
            event.status = WebhookEventStatus.FAILED
            event.error_message = error_message[:2000] if error_message else None
            self.session.flush()

    def is_duplicate(self, message_id: str) -> bool:
        """Checks if a message ID has already been recorded."""
        if not message_id:
            return False
        stmt = select(WebhookEvent.id).where(WebhookEvent.message_id == message_id)
        return self.session.scalar(stmt) is not None
