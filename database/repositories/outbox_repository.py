"""
Transactional Outbox Repository.
Provides atomic persistence of outbound messages within the primary database transaction,
decoupling local state updates from external Meta WhatsApp HTTP transport.
"""

import uuid
import logging
from typing import List, Optional
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import select

from database.models import OutboxMessage
from database.enums import OutboxMessageStatus

logger = logging.getLogger("OutboxRepository")


class OutboxRepository:
    """Manages persistence, retrieval, and status transitions for transactional outbox."""

    def __init__(self, session: Session):
        self.session = session

    def enqueue_message(
        self,
        recipient_phone: str,
        message_text: str,
        idempotency_key: Optional[str] = None,
        max_retries: int = 3
    ) -> OutboxMessage:
        """
        Enqueues an outbound WhatsApp message within the caller's active database transaction.
        Guarantees that outbound messages are never lost if external dispatch fails.
        """
        # Idempotency check if key provided
        if idempotency_key:
            stmt = select(OutboxMessage).where(OutboxMessage.idempotency_key == idempotency_key)
            existing = self.session.scalars(stmt).first()
            if existing:
                logger.info(f"Outbox idempotency hit: message with key '{idempotency_key}' already queued.")
                return existing

        outbox_id = f"OUT-{uuid.uuid4().hex[:12].upper()}"
        outbox_msg = OutboxMessage(
            outbox_id=outbox_id,
            recipient_phone=recipient_phone.strip(),
            message_text=message_text,
            status=OutboxMessageStatus.PENDING,
            max_retries=max_retries,
            idempotency_key=idempotency_key,
            created_at=datetime.now()
        )
        self.session.add(outbox_msg)
        self.session.flush()
        logger.info(f"Enqueued outbound message {outbox_id} to {recipient_phone}")
        return outbox_msg

    def fetch_pending(self, limit: int = 20) -> List[OutboxMessage]:
        """Fetches pending and retry-eligible outbound messages."""
        stmt = (
            select(OutboxMessage)
            .where(
                OutboxMessage.status.in_([OutboxMessageStatus.PENDING, OutboxMessageStatus.RETRYING]),
                OutboxMessage.retry_count < OutboxMessage.max_retries
            )
            .order_by(OutboxMessage.id.asc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())

    def mark_dispatched(self, outbox_id: str) -> bool:
        """Marks an outbox message as successfully dispatched to the external provider."""
        stmt = select(OutboxMessage).where(OutboxMessage.outbox_id == outbox_id)
        msg = self.session.scalars(stmt).first()
        if not msg:
            return False
        msg.status = OutboxMessageStatus.DISPATCHED
        msg.dispatched_at = datetime.now()
        self.session.flush()
        logger.info(f"Outbox message {outbox_id} marked as DISPATCHED.")
        return True

    def mark_failed(self, outbox_id: str, error_message: str) -> bool:
        """
        Records dispatch failure, increments retry count, and transitions to
        RETRYING or FAILED depending on retry limit.
        """
        stmt = select(OutboxMessage).where(OutboxMessage.outbox_id == outbox_id)
        msg = self.session.scalars(stmt).first()
        if not msg:
            return False

        msg.retry_count += 1
        msg.last_error = error_message[:2000] if error_message else None

        if msg.retry_count >= msg.max_retries:
            msg.status = OutboxMessageStatus.FAILED
            logger.warning(f"Outbox message {outbox_id} reached max retries ({msg.max_retries}). Marked FAILED.")
        else:
            msg.status = OutboxMessageStatus.RETRYING
            logger.info(f"Outbox message {outbox_id} failed attempt {msg.retry_count}/{msg.max_retries}. Queued for retry.")

        self.session.flush()
        return True

    def get_by_outbox_id(self, outbox_id: str) -> Optional[OutboxMessage]:
        """Retrieves an outbox message by its business identifier."""
        stmt = select(OutboxMessage).where(OutboxMessage.outbox_id == outbox_id)
        return self.session.scalars(stmt).first()
