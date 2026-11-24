"""
Conversational Memory and Multi-Turn State Manager for KrishiBot.
Tracks sequential dialog turns, isolates context per farmer, maintains state machine
stages across server restarts, and injects relevant conversation history into LLM prompts.
"""

import json
import logging
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

from database.connection import get_db_session
from database.models import ConversationSession, ConversationMessage
from database.repositories import ConversationRepository
from database.enums import ConversationState

logger = logging.getLogger("ConversationManager")


class ConversationManager:
    """
    Manages multi-turn conversational context, persistence, and state transitions.
    Guarantees zero cross-farmer context contamination by isolating sessions per phone.
    """

    def __init__(self, max_history_turns: int = 5):
        self.max_history_turns = max_history_turns

    def get_or_resume_session(
        self,
        phone_number: str,
        farmer_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Retrieves or initializes an active conversation session.
        Returns serialized session dictionary safe for decoupled processing.
        """
        with get_db_session() as session:
            repo = ConversationRepository(session)
            sess = repo.get_or_create_session(phone_number=phone_number, farmer_id=farmer_id)
            
            pending_fields = []
            if sess.pending_fields:
                try:
                    pending_fields = json.loads(sess.pending_fields)
                except Exception:
                    pass

            context_data = {}
            if sess.context_data:
                try:
                    context_data = json.loads(sess.context_data)
                except Exception:
                    pass

            return {
                "id": sess.id,
                "session_id": sess.session_id,
                "farmer_id": sess.farmer_id,
                "phone_number": sess.phone_number,
                "current_state": sess.current_state,
                "pending_fields": pending_fields,
                "context_data": context_data,
                "last_interaction_at": sess.last_interaction_at.isoformat() if sess.last_interaction_at else None
            }

    def record_turn(
        self,
        session_pk: int,
        user_message: str,
        assistant_reply: Optional[str] = None,
        intent: Optional[str] = None,
        entities: Optional[Dict[str, Any]] = None,
        new_state: Optional[str] = None,
        pending_fields: Optional[List[str]] = None,
        updated_context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Atomically records user and assistant messages into session history
        and advances the dialog state machine.
        """
        with get_db_session() as session:
            repo = ConversationRepository(session)

            # Record farmer user message
            repo.add_message(
                session_id=session_pk,
                sender_role="farmer",
                message_text=user_message,
                intent=intent,
                entities=entities
            )

            # Record assistant reply if dispatched
            if assistant_reply:
                repo.add_message(
                    session_id=session_pk,
                    sender_role="assistant",
                    message_text=assistant_reply,
                    intent=intent
                )

            # Update state machine parameters
            repo.update_state(
                session_id=session_pk,
                state=new_state,
                pending_fields=pending_fields,
                context_data=updated_context
            )
            session.commit()

    def get_conversation_history(
        self,
        session_pk: int,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Retrieves ordered recent message history for context assembly."""
        turn_limit = limit or self.max_history_turns
        with get_db_session() as session:
            repo = ConversationRepository(session)
            messages = repo.get_recent_messages(session_id=session_pk, limit=turn_limit * 2)
            
            history = []
            for msg in messages:
                history.append({
                    "role": msg.sender_role,
                    "text": msg.message_text,
                    "intent": msg.intent,
                    "created_at": msg.created_at.isoformat() if msg.created_at else None
                })
            return history

    def format_history_for_prompt(self, session_pk: int) -> str:
        """Formats recent multi-turn conversation into a clean prompt string."""
        history = self.get_conversation_history(session_pk=session_pk)
        if not history:
            return "No prior conversational context."

        formatted_lines = []
        for turn in history:
            prefix = "Farmer:" if turn["role"] == "farmer" else "KrishiBot:"
            formatted_lines.append(f"{prefix} {turn['text']}")

        return "\n".join(formatted_lines)
