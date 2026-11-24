"""
Master Farmer Agent (KrishiBot) — Phase 3 Stateful Multi-Turn Implementation.
Orchestrates:
  1. Multi-Turn Conversational Memory & State Machine
  2. 13-Intent Granular Agricultural Classification with Entity Extraction
  3. Grounded Knowledge Retrieval (RAG Pipeline)
  4. Context-Enriched LLM Response Generation with Dialog History
  5. Missing Agronomic Parameter Detection & Gentle Follow-Up Elicitation
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

from .classifier import WhatsAppMessageClassifier, MessageCategory, ClassificationResult
from .prompts import KRISHIBOT_SYSTEM_PROMPT, GOOGLE_FORM_ASSISTANT_PROMPT, URGENT_DISTRESS_RESPONSE
from .llm_client import GeminiLLMClient
from .response_formatter import format_whatsapp_message
from .conversation_manager import ConversationManager
from .followup_engine import FollowupEngine
from rag.pipeline import FarmingRAGPipeline
from rag.retriever import RetrievedChunk
from database.enums import AgriculturalIntent, ConversationState

logger = logging.getLogger("FarmerAgent")


@dataclass
class FarmerProfile:
    """Farmer demographic and agricultural profile context."""
    name: str = "किसान भाई"
    phone: str = ""
    district: str = "General"
    crop: str = "General"
    soil_type: str = "Loam"
    farm_size: str = "3 Acres"
    farmer_id: Optional[int] = None
    preferred_language: str = "mr"


@dataclass
class AgentResponse:
    """Agent response payload with execution metrics and multi-turn state."""
    status: str  # "ANSWERED", "IGNORED", "FORM_HELP", "ESCALATED"
    reply_text: Optional[str]
    category: MessageCategory
    classification_confidence: float
    reason: str
    rag_sources: List[str] = field(default_factory=list)
    processing_time_ms: float = 0.0
    requires_admin_alert: bool = False
    # Phase 3 Granular Taxonomy & Conversational State
    intent: Optional[AgriculturalIntent] = None
    followup_question: Optional[str] = None
    extracted_entities: Dict[str, Any] = field(default_factory=dict)
    session_id: Optional[str] = None


class FarmerAgent:
    """
    Central AI agent for processing farmer WhatsApp communications.
    Maintains conversational memory, resolves missing agronomic parameters,
    and grounds recommendations in verified RAG knowledge.
    """

    def __init__(
        self,
        rag_pipeline: Optional[FarmingRAGPipeline] = None,
        llm_client: Optional[GeminiLLMClient] = None,
        classifier: Optional[WhatsAppMessageClassifier] = None,
        conversation_manager: Optional[ConversationManager] = None,
        followup_engine: Optional[FollowupEngine] = None,
        default_form_link: str = "https://forms.gle/WeeklyFarmerSurvey"
    ):
        self.rag_pipeline = rag_pipeline or FarmingRAGPipeline()
        self.llm_client = llm_client or GeminiLLMClient()
        self.classifier = classifier or WhatsAppMessageClassifier()
        self.conversation_manager = conversation_manager or ConversationManager()
        self.followup_engine = followup_engine or FollowupEngine()
        self.default_form_link = default_form_link

    def process_message(
        self,
        message: str,
        sender_phone: Optional[str] = None,
        sender_name: Optional[str] = None,
        group_id: Optional[str] = None,
        profile: Optional[FarmerProfile] = None
    ) -> AgentResponse:
        """
        Processes an incoming WhatsApp message with multi-turn context awareness.
        """
        start_time = time.time()
        farmer_profile = profile or FarmerProfile(name=sender_name or "किसान भाई", phone=sender_phone or "")
        active_phone = sender_phone or farmer_profile.phone

        # -------------------------------------------------------------------
        # Step 1: Manage Conversational Session (Memory & State Machine)
        # -------------------------------------------------------------------
        session_info = None
        session_pk = None
        session_id_str = None
        context_data: Dict[str, Any] = {}
        asked_questions: List[str] = []
        is_awaiting_input = False
        awaiting_field = None

        if active_phone:
            try:
                session_info = self.conversation_manager.get_or_resume_session(
                    phone_number=active_phone,
                    farmer_id=farmer_profile.farmer_id
                )
                session_pk = session_info["id"]
                session_id_str = session_info["session_id"]
                context_data = session_info.get("context_data", {})
                asked_questions = context_data.get("asked_questions", [])
                is_awaiting_input = (session_info.get("current_state") == ConversationState.AWAITING_FIELD_INPUT.value)
                awaiting_field = context_data.get("awaiting_field")
            except Exception as e:
                logger.error(f"Error resuming conversation session for {active_phone}: {e}")

        # -------------------------------------------------------------------
        # Step 2: Classify Message Intent & Extract Entities (13 Categories)
        # -------------------------------------------------------------------
        classification = self.classifier.classify(message)
        logger.info(f"Classified message as [{classification.intent.value if classification.intent else classification.category.value}] (Confidence: {classification.confidence:.2f})")

        # -------------------------------------------------------------------
        # Step 3: Handle State Machine Awaiting Input Transition
        # -------------------------------------------------------------------
        elicitation_acknowledged = False
        if is_awaiting_input and awaiting_field and farmer_profile.farmer_id:
            # Check if this incoming message is an answer to the pending field
            is_profile_reply = (
                classification.intent == AgriculturalIntent.FARMER_PROFILE_UPDATE or
                len(classification.extracted_entities) > 0 or
                len(message.split()) <= 6
            )
            if is_profile_reply:
                applied, note = self.followup_engine.parse_and_apply_answer(
                    farmer_id=farmer_profile.farmer_id,
                    field_name=awaiting_field,
                    message_text=message,
                    extracted_entities=classification.extracted_entities
                )
                if applied:
                    elicitation_acknowledged = True
                    logger.info(f"Successfully elicited {awaiting_field} from farmer: {note}")
                    context_data["awaiting_field"] = None

        # -------------------------------------------------------------------
        # Step 4: Handle Ignored Chatter / Spam
        # -------------------------------------------------------------------
        if not classification.should_reply and not elicitation_acknowledged:
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            if session_pk:
                try:
                    self.conversation_manager.record_turn(
                        session_pk=session_pk,
                        user_message=message,
                        assistant_reply=None,
                        intent=classification.intent.value if classification.intent else None,
                        entities=classification.extracted_entities,
                        new_state=ConversationState.IDLE.value,
                        updated_context=context_data
                    )
                except Exception as ex:
                    logger.error(f"Error recording ignored turn: {ex}")

            return AgentResponse(
                status="IGNORED",
                reply_text=None,
                category=classification.category,
                classification_confidence=classification.confidence,
                reason=classification.reason,
                intent=classification.intent,
                extracted_entities=classification.extracted_entities,
                session_id=session_id_str,
                processing_time_ms=elapsed_ms
            )

        # -------------------------------------------------------------------
        # Step 5: Handle Emergency Distress
        # -------------------------------------------------------------------
        if classification.category == MessageCategory.URGENT_DISTRESS:
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            if session_pk:
                try:
                    self.conversation_manager.record_turn(
                        session_pk=session_pk,
                        user_message=message,
                        assistant_reply=URGENT_DISTRESS_RESPONSE,
                        intent=classification.intent.value if classification.intent else None,
                        entities=classification.extracted_entities,
                        new_state=ConversationState.ESCALATED.value,
                        updated_context=context_data
                    )
                except Exception as ex:
                    logger.error(f"Error recording distress turn: {ex}")

            return AgentResponse(
                status="ESCALATED",
                reply_text=URGENT_DISTRESS_RESPONSE,
                category=classification.category,
                classification_confidence=classification.confidence,
                reason=classification.reason,
                intent=classification.intent,
                requires_admin_alert=True,
                extracted_entities=classification.extracted_entities,
                session_id=session_id_str,
                processing_time_ms=elapsed_ms
            )

        # -------------------------------------------------------------------
        # Step 6: Handle Google Form Interactions
        # -------------------------------------------------------------------
        if classification.category == MessageCategory.FORM_RELATED and not elicitation_acknowledged:
            form_reply = (
                f"📋 *साप्ताहिक कृषि फॉर्म (Weekly Farm Form):*\n\n"
                f"नमस्ते {farmer_profile.name}! कृपया अपनी फसल, मिट्टी और खेत की ताजा जानकारी इस लिंक पर भरें:\n"
                f"👉 {self.default_form_link}\n\n"
                f"यदि आप पहले ही फॉर्म भर चुके हैं, तो आपका धन्यवाद! 🙏\n"
                f"_🌾 KrishiBot Assistant_"
            )
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            if session_pk:
                try:
                    self.conversation_manager.record_turn(
                        session_pk=session_pk,
                        user_message=message,
                        assistant_reply=form_reply,
                        intent=classification.intent.value if classification.intent else None,
                        entities=classification.extracted_entities,
                        new_state=ConversationState.IDLE.value,
                        updated_context=context_data
                    )
                except Exception as ex:
                    logger.error(f"Error recording form turn: {ex}")

            return AgentResponse(
                status="FORM_HELP",
                reply_text=form_reply,
                category=classification.category,
                classification_confidence=classification.confidence,
                reason="Google Form assistance provided",
                intent=classification.intent,
                extracted_entities=classification.extracted_entities,
                session_id=session_id_str,
                processing_time_ms=elapsed_ms
            )

        # -------------------------------------------------------------------
        # Step 7: Handle Agricultural Query (RAG + History + Follow-Up)
        # -------------------------------------------------------------------
        # Query RAG Vector Store
        retrieved_chunks = self.rag_pipeline.query(
            query=message,
            top_k=3,
            crop=farmer_profile.crop if farmer_profile.crop != "General" else None
        )

        rag_context = self.rag_pipeline.retriever.format_context_for_llm(retrieved_chunks)
        rag_source_titles = [f"{c.title} > {c.section_title}" for c in retrieved_chunks]

        # Retrieve recent dialog turns for multi-turn conversational grounding
        history_str = "No prior conversational context."
        if session_pk:
            try:
                history_str = self.conversation_manager.format_history_for_prompt(session_pk)
            except Exception as e:
                logger.error(f"Error assembling dialog history: {e}")

        # Assemble Grounded System Prompt
        system_prompt = (
            KRISHIBOT_SYSTEM_PROMPT.format(
                farmer_name=farmer_profile.name,
                district=farmer_profile.district,
                crop=farmer_profile.crop,
                soil_type=farmer_profile.soil_type,
                farm_size=farmer_profile.farm_size,
                rag_context=rag_context
            ) + f"\n\nRECENT CONVERSATION HISTORY:\n{history_str}\n"
        )

        # Generate Response via Gemini LLM (falls back to extractive local RAG when API key unset)
        raw_llm_response = self.llm_client.generate(
            system_prompt=system_prompt,
            user_prompt=message
        )

        # Format for WhatsApp
        formatted_reply = format_whatsapp_message(raw_llm_response)

        # Prepend acknowledgment if farmer answered a pending question
        if elicitation_acknowledged and awaiting_field:
            ack_msg = "✅ *धन्यवाद! तुमची माहिती नोंदवली आहे.* (Information saved)\n\n"
            formatted_reply = ack_msg + formatted_reply

        # -------------------------------------------------------------------
        # Step 8: Missing Parameter Elicitation (Gentle Follow-Up)
        # -------------------------------------------------------------------
        followup_q = None
        next_state = ConversationState.IDLE.value

        if active_phone and farmer_profile.farmer_id:
            try:
                from database.connection import get_db_session as _get_session
                from database.repositories import FarmerRepository as _FR
                with _get_session() as s:
                    db_farmer = _FR(s).get_by_id(farmer_profile.farmer_id)
                    missing_map = self.followup_engine.inspect_missing_fields(db_farmer)
                    
                    next_field = self.followup_engine.select_next_field_to_elicit(
                        status_map=missing_map,
                        asked_fields=asked_questions
                    )
                    if next_field:
                        followup_q = self.followup_engine.generate_question(
                            field_name=next_field,
                            preferred_language=farmer_profile.preferred_language
                        )
                        # Append single polite question after answering immediate query
                        formatted_reply += f"\n\n💬 *टीप / अधिक माहितीसाठी:*\n{followup_q}"
                        
                        # Update tracking
                        asked_questions.append(next_field)
                        context_data["asked_questions"] = asked_questions
                        context_data["awaiting_field"] = next_field
                        next_state = ConversationState.AWAITING_FIELD_INPUT.value
            except Exception as ex:
                logger.error(f"Error inspecting missing fields for follow-up: {ex}")

        # Record this turn in conversational memory
        if session_pk:
            try:
                self.conversation_manager.record_turn(
                    session_pk=session_pk,
                    user_message=message,
                    assistant_reply=formatted_reply,
                    intent=classification.intent.value if classification.intent else None,
                    entities=classification.extracted_entities,
                    new_state=next_state,
                    updated_context=context_data
                )
            except Exception as ex:
                logger.error(f"Error recording completed turn: {ex}")

        elapsed_ms = round((time.time() - start_time) * 1000, 2)

        return AgentResponse(
            status="ANSWERED",
            reply_text=formatted_reply,
            category=classification.category,
            classification_confidence=classification.confidence,
            reason="Answered agricultural query with RAG context and conversational state",
            intent=classification.intent,
            followup_question=followup_q,
            extracted_entities=classification.extracted_entities,
            session_id=session_id_str,
            rag_sources=rag_source_titles,
            processing_time_ms=elapsed_ms
        )
