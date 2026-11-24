"""
Conversation Session and Message History Repository.
Provides multi-turn dialog tracking, farmer-isolated context retrieval,
and persistent state machine transitions across server restarts.
"""

import uuid
import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import select

from database.models import ConversationSession, ConversationMessage
from database.enums import ConversationState

logger = logging.getLogger("ConversationRepository")


class ConversationRepository:
    """Manages active conversation sessions and sequential message history."""

    def __init__(self, session: Session):
        self.session = session

    def get_or_create_session(
        self,
        phone_number: str,
        farmer_id: Optional[int] = None
    ) -> ConversationSession:
        """
        Retrieves active conversation session for a phone number or creates a new one.
        Ensures farmer isolation and resumes existing context across application restarts.
        """
        clean_phone = phone_number.strip()
        stmt = (
            select(ConversationSession)
            .where(ConversationSession.phone_number == clean_phone)
            .order_by(ConversationSession.last_interaction_at.desc())
        )
        existing = self.session.scalars(stmt).first()

        if existing:
            # Update farmer_id link if provided and not yet set
            if farmer_id and not existing.farmer_id:
                existing.farmer_id = farmer_id
                self.session.flush()
            return existing

        session_id = f"SESS-{uuid.uuid4().hex[:12].upper()}"
        new_session = ConversationSession(
            session_id=session_id,
            farmer_id=farmer_id,
            phone_number=clean_phone,
            current_state=ConversationState.IDLE.value,
            pending_fields=json.dumps([]),
            context_data=json.dumps({}),
            created_at=datetime.now(),
            last_interaction_at=datetime.now()
        )
        self.session.add(new_session)
        self.session.flush()
        logger.info(f"Created new conversation session {session_id} for phone {clean_phone}")
        return new_session

    def add_message(
        self,
        session_id: int,
        sender_role: str,
        message_text: str,
        intent: Optional[str] = None,
        entities: Optional[Dict[str, Any]] = None
    ) -> ConversationMessage:
        """Appends a turn to the conversation history and updates last_interaction_at."""
        entities_json = json.dumps(entities) if entities else None
        msg = ConversationMessage(
            session_id=session_id,
            sender_role=sender_role,
            message_text=message_text,
            intent=intent,
            entities=entities_json,
            created_at=datetime.now()
        )
        self.session.add(msg)

        # Update session touch timestamp
        stmt = select(ConversationSession).where(ConversationSession.id == session_id)
        sess = self.session.scalars(stmt).first()
        if sess:
            sess.last_interaction_at = datetime.now()

        self.session.flush()
        return msg

    def get_recent_messages(
        self,
        session_id: int,
        limit: int = 10
    ) -> List[ConversationMessage]:
        """Retrieves recent conversation turns ordered chronologically for prompt context."""
        stmt = (
            select(ConversationMessage)
            .where(ConversationMessage.session_id == session_id)
            .order_by(ConversationMessage.id.desc())
            .limit(limit)
        )
        messages = list(self.session.scalars(stmt).all())
        messages.reverse()  # Chronological order
        return messages

    def update_state(
        self,
        session_id: int,
        state: Optional[str] = None,
        pending_fields: Optional[List[str]] = None,
        context_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Updates dialog state machine stage, pending elicitation fields, and context dict."""
        stmt = select(ConversationSession).where(ConversationSession.id == session_id)
        sess = self.session.scalars(stmt).first()
        if not sess:
            return False

        if state is not None:
            sess.current_state = state
        if pending_fields is not None:
            sess.pending_fields = json.dumps(pending_fields)
        if context_data is not None:
            # Merge with existing context if present
            current = {}
            if sess.context_data:
                try:
                    current = json.loads(sess.context_data)
                except Exception:
                    pass
            current.update(context_data)
            sess.context_data = json.dumps(current)

        sess.last_interaction_at = datetime.now()
        self.session.flush()
        return True

    def get_session_by_id(self, session_id: str) -> Optional[ConversationSession]:
        """Looks up session by business session_id string."""
        stmt = select(ConversationSession).where(ConversationSession.session_id == session_id)
        return self.session.scalars(stmt).first()
