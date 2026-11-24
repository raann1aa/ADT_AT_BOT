"""
Transactional Outbox Service.
Handles durable queuing and asynchronous dispatch of outbound WhatsApp messages.
Ensures database state transitions are committed before external network requests,
preventing duplicate dispatch loops and lost messages across application crashes.
"""

import logging
from typing import Dict, Any, Optional

from database.connection import get_db_session
from database.repositories.outbox_repository import OutboxRepository

logger = logging.getLogger("OutboxService")


class OutboxService:
    """Manages transactional message queuing and reliable external delivery."""

    def __init__(self, whatsapp_client=None):
        self.whatsapp_client = whatsapp_client

    def enqueue(
        self,
        recipient_phone: str,
        message_text: str,
        idempotency_key: Optional[str] = None,
        max_retries: int = 3
    ) -> str:
        """
        Atomically queues an outbound message in the database.
        Returns the unique outbox_id.
        """
        with get_db_session() as session:
            repo = OutboxRepository(session)
            msg = repo.enqueue_message(
                recipient_phone=recipient_phone,
                message_text=message_text,
                idempotency_key=idempotency_key,
                max_retries=max_retries
            )
            session.commit()
            return msg.outbox_id

    def process_pending(self, client=None, limit: int = 20) -> Dict[str, Any]:
        """
        Dispatches pending outbox messages to the external WhatsApp API client.
        Note: Official WhatsApp Cloud API guarantees at-least-once transport;
        this dispatcher prevents local database failure from causing message loss.
        """
        active_client = client or self.whatsapp_client
        if not active_client:
            logger.warning("No WhatsApp client configured for outbox dispatch.")
            return {"dispatched": 0, "failed": 0, "total": 0}

        dispatched_count = 0
        failed_count = 0

        with get_db_session() as session:
            repo = OutboxRepository(session)
            pending_messages = repo.fetch_pending(limit=limit)

            for msg in pending_messages:
                try:
                    active_client.send_message(to=msg.recipient_phone, message_text=msg.message_text)
                    repo.mark_dispatched(msg.outbox_id)
                    dispatched_count += 1
                except Exception as ex:
                    logger.error(f"Failed to dispatch outbox message {msg.outbox_id}: {ex}")
                    repo.mark_failed(msg.outbox_id, str(ex))
                    failed_count += 1

            session.commit()

        return {
            "dispatched": dispatched_count,
            "failed": failed_count,
            "total": dispatched_count + failed_count
        }

    def get_status(self, outbox_id: str) -> Optional[str]:
        """Returns the current status of an outbox message."""
        with get_db_session() as session:
            repo = OutboxRepository(session)
            msg = repo.get_by_outbox_id(outbox_id)
            return msg.status.value if msg else None
