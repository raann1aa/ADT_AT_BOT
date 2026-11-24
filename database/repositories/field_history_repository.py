"""
Field History Audit Repository.
Tracks all modifications to farmer profiles, plots, crops, and soil health records,
preserving chronological audit trails with actor attribution and source metadata.
"""

import logging
from typing import List, Optional, Any
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import select

from database.models import FieldHistory

logger = logging.getLogger("FieldHistoryRepository")


class FieldHistoryRepository:
    """Manages creation and retrieval of field-level change history entries."""

    def __init__(self, session: Session):
        self.session = session

    def record_change(
        self,
        entity_type: str,
        entity_id: int,
        field_name: str,
        old_value: Any,
        new_value: Any,
        changed_by: str = "SYSTEM",
        change_source: str = "WHATSAPP_CHAT"
    ) -> Optional[FieldHistory]:
        """
        Records a historical modification entry if old_value != new_value.
        Values are serialized as strings for durable audit logging.
        """
        old_str = str(old_value) if old_value is not None else None
        new_str = str(new_value) if new_value is not None else None

        if old_str == new_str:
            # Value unchanged; skip creating empty audit record
            return None

        entry = FieldHistory(
            entity_type=entity_type,
            entity_id=entity_id,
            field_name=field_name,
            old_value=old_str,
            new_value=new_str,
            changed_by=changed_by,
            change_source=change_source,
            changed_at=datetime.now()
        )
        self.session.add(entry)
        self.session.flush()
        logger.info(f"Recorded change on {entity_type}#{entity_id}.{field_name}: '{old_str}' -> '{new_str}' by {changed_by}")
        return entry

    def get_history(
        self,
        entity_type: str,
        entity_id: int,
        field_name: Optional[str] = None
    ) -> List[FieldHistory]:
        """Retrieves chronological change history for a specific entity."""
        stmt = (
            select(FieldHistory)
            .where(
                FieldHistory.entity_type == entity_type,
                FieldHistory.entity_id == entity_id
            )
        )
        if field_name:
            stmt = stmt.where(FieldHistory.field_name == field_name)

        stmt = stmt.order_by(FieldHistory.changed_at.desc(), FieldHistory.id.desc())
        return list(self.session.scalars(stmt).all())
