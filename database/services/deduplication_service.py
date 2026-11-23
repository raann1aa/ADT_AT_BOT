"""
Deduplication and Idempotency Service.
Combines sub-millisecond in-memory cache lookup with persistent
database storage to guarantee exactly-once processing across server restarts.
"""

import logging
import threading
from collections import deque
from typing import Optional

from database.connection import get_db_session
from database.repositories import IdempotencyRepository

logger = logging.getLogger("DeduplicationService")


class DeduplicationService:
    """Hybrid in-memory and database-backed idempotency controller."""

    def __init__(self, memory_cache_size: int = 1000):
        self._memory_cache = deque(maxlen=memory_cache_size)
        self._memory_set = set()
        self._lock = threading.Lock()

    def claim_message(
        self,
        message_id: str,
        sender_phone: str,
        event_type: str = "message"
    ) -> bool:
        """
        Attempts to claim an incoming webhook message ID.
        Returns:
            True if message is newly received and successfully acquired for processing.
            False if message is a duplicate (either in recent RAM cache or persistent DB).
        """
        if not message_id:
            return False

        with self._lock:
            # Fast RAM check (<0.1ms)
            if message_id in self._memory_set:
                logger.info(f"RAM Dedup: Message {message_id} dropped at fast ingress.")
                return False

            # Persistent database claim
            try:
                with get_db_session() as session:
                    repo = IdempotencyRepository(session)
                    claimed = repo.claim_message(
                        message_id=message_id,
                        sender_phone=sender_phone,
                        event_type=event_type
                    )
                    if not claimed:
                        self._add_to_ram_cache_locked(message_id)
                        return False

                    self._add_to_ram_cache_locked(message_id)
                    return True
            except Exception as e:
                logger.error(f"Error during persistent message claim: {e}")
                if message_id in self._memory_set:
                    return False
                self._add_to_ram_cache_locked(message_id)
                return True

    def complete_message(self, message_id: str) -> None:
        """Marks message execution as successfully completed in database."""
        try:
            with get_db_session() as session:
                repo = IdempotencyRepository(session)
                repo.complete_message(message_id)
        except Exception as e:
            logger.error(f"Error completing message {message_id}: {e}")

    def fail_message(self, message_id: str, error_message: str) -> None:
        """Records processing failure in persistent ledger."""
        try:
            with get_db_session() as session:
                repo = IdempotencyRepository(session)
                repo.fail_message(message_id, error_message)
        except Exception as e:
            logger.error(f"Error marking message failure {message_id}: {e}")

    def is_duplicate(self, message_id: str) -> bool:
        """Checks if a message ID is already recorded in RAM or DB."""
        if not message_id:
            return False
        with self._lock:
            if message_id in self._memory_set:
                return True
        try:
            with get_db_session() as session:
                repo = IdempotencyRepository(session)
                is_dup = repo.is_duplicate(message_id)
                if is_dup:
                    with self._lock:
                        self._add_to_ram_cache_locked(message_id)
                return is_dup
        except Exception as e:
            logger.error(f"Error checking duplicate status: {e}")
            return False

    def _add_to_ram_cache_locked(self, message_id: str):
        """Maintains bounded in-memory set and deque (must be called with lock held)."""
        if len(self._memory_cache) >= self._memory_cache.maxlen:
            oldest = self._memory_cache.popleft()
            self._memory_set.discard(oldest)
        self._memory_cache.append(message_id)
        self._memory_set.add(message_id)
