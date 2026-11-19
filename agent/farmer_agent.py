"""
Master Farmer Agent (KrishiBot).
Orchestrates Message Classification -> Knowledge Retrieval (RAG) -> LLM Generation -> WhatsApp Formatting.
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

from .classifier import WhatsAppMessageClassifier, MessageCategory, ClassificationResult
from .prompts import KRISHIBOT_SYSTEM_PROMPT, GOOGLE_FORM_ASSISTANT_PROMPT, URGENT_DISTRESS_RESPONSE
from .llm_client import GeminiLLMClient
from .response_formatter import format_whatsapp_message
from rag.pipeline import FarmingRAGPipeline
from rag.retriever import RetrievedChunk

logger = logging.getLogger("FarmerAgent")

@dataclass
class FarmerProfile:
    name: str = "किसान भाई"
    phone: str = ""
    district: str = "General"
    crop: str = "General"
    soil_type: str = "Loam"
    farm_size: str = "3 Acres"

@dataclass
class AgentResponse:
    status: str  # "ANSWERED", "IGNORED", "FORM_HELP", "ESCALATED"
    reply_text: Optional[str]
    category: MessageCategory
    classification_confidence: float
    reason: str
    rag_sources: List[str] = field(default_factory=list)
    processing_time_ms: float = 0.0
    requires_admin_alert: bool = False

class FarmerAgent:
    """
    Central AI agent for processing farmer WhatsApp group messages.
    Filters out noise/greetings and answers legitimate agricultural queries.
    """

    def __init__(
        self,
        rag_pipeline: Optional[FarmingRAGPipeline] = None,
        llm_client: Optional[GeminiLLMClient] = None,
        classifier: Optional[WhatsAppMessageClassifier] = None,
        default_form_link: str = "https://forms.gle/WeeklyFarmerSurvey"
    ):
        self.rag_pipeline = rag_pipeline or FarmingRAGPipeline()
        self.llm_client = llm_client or GeminiLLMClient()
        self.classifier = classifier or WhatsAppMessageClassifier()
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
        Processes an incoming message from a WhatsApp group.
        Decides whether to reply, ignore, or escalate.
        """
        start_time = time.time()
        farmer_profile = profile or FarmerProfile(name=sender_name or "किसान भाई", phone=sender_phone or "")

        # Step 1: Classify Message Intent
        classification = self.classifier.classify(message)
        logger.info(f"Classified message as [{classification.category.value}] (Confidence: {classification.confidence:.2f})")

        # Step 2: Handle Ignored Chatter / Spam
        if not classification.should_reply:
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            return AgentResponse(
                status="IGNORED",
                reply_text=None,
                category=classification.category,
                classification_confidence=classification.confidence,
                reason=classification.reason,
                processing_time_ms=elapsed_ms
            )

        # Step 3: Handle Emergency Distress
        if classification.category == MessageCategory.URGENT_DISTRESS:
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            return AgentResponse(
                status="ESCALATED",
                reply_text=URGENT_DISTRESS_RESPONSE,
                category=classification.category,
                classification_confidence=classification.confidence,
                reason=classification.reason,
                requires_admin_alert=True,
                processing_time_ms=elapsed_ms
            )

        # Step 4: Handle Google Form Interactions
        if classification.category == MessageCategory.FORM_RELATED:
            form_reply = (
                f"📋 *साप्ताहिक कृषि फॉर्म (Weekly Farm Form):*\n\n"
                f"नमस्ते {farmer_profile.name}! कृपया अपनी फसल, मिट्टी और खेत की ताजा जानकारी इस लिंक पर भरें:\n"
                f"👉 {self.default_form_link}\n\n"
                f"यदि आप पहले ही फॉर्म भर चुके हैं, तो आपका धन्यवाद! 🙏\n"
                f"_🌾 KrishiBot Assistant_"
            )
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            return AgentResponse(
                status="FORM_HELP",
                reply_text=form_reply,
                category=classification.category,
                classification_confidence=classification.confidence,
                reason="Google Form assistance provided",
                processing_time_ms=elapsed_ms
            )

        # Step 5: Handle Legitimate Agricultural Query (RAG + LLM)
        # Query RAG Vector Store
        retrieved_chunks = self.rag_pipeline.query(
            query=message,
            top_k=3,
            crop=farmer_profile.crop if farmer_profile.crop != "General" else None
        )

        rag_context = self.rag_pipeline.retriever.format_context_for_llm(retrieved_chunks)
        rag_source_titles = [f"{c.title} > {c.section_title}" for c in retrieved_chunks]

        # Build Grounded System Prompt
        system_prompt = KRISHIBOT_SYSTEM_PROMPT.format(
            farmer_name=farmer_profile.name,
            district=farmer_profile.district,
            crop=farmer_profile.crop,
            soil_type=farmer_profile.soil_type,
            farm_size=farmer_profile.farm_size,
            rag_context=rag_context
        )

        # Generate Response via Gemini LLM
        raw_llm_response = self.llm_client.generate(
            system_prompt=system_prompt,
            user_prompt=message
        )

        # Format for WhatsApp
        formatted_reply = format_whatsapp_message(raw_llm_response)
        elapsed_ms = round((time.time() - start_time) * 1000, 2)

        return AgentResponse(
            status="ANSWERED",
            reply_text=formatted_reply,
            category=MessageCategory.FARMING_QUERY,
            classification_confidence=classification.confidence,
            reason="Answered agricultural query with RAG context",
            rag_sources=rag_source_titles,
            processing_time_ms=elapsed_ms
        )
