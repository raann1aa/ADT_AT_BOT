"""
Unified LLM Client supporting Google Gemini API with fallback to
intelligent local extractive RAG generation when API keys are not configured.
"""

import os
import re
import json
import logging
from typing import Optional, Dict, Any, List

import requests

logger = logging.getLogger(__name__)

# Default Gemini model
DEFAULT_GEMINI_MODEL = "gemini-1.5-flash"
GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

class GeminiLLMClient:
    """
    Client for generating grounded agricultural answers using Google Gemini.
    Features seamless zero-key fallback for local testing and demonstration.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = DEFAULT_GEMINI_MODEL,
        temperature: float = 0.2,
        max_output_tokens: int = 400
    ):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self.model_name = model_name
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.is_live = bool(self.api_key and self.api_key.strip() and not self.api_key.startswith("your_"))

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """
        Generates an answer from Gemini if API key is valid,
        or generates an intelligent local RAG extraction if offline.
        """
        if self.is_live:
            try:
                return self._call_gemini_api(system_prompt, user_prompt)
            except Exception as e:
                logger.warning(f"Gemini API call failed ({e}). Falling back to local RAG generator.")
                return self._generate_local_fallback(system_prompt, user_prompt)
        else:
            return self._generate_local_fallback(system_prompt, user_prompt)

    def _call_gemini_api(self, system_prompt: str, user_prompt: str) -> str:
        """Invokes the official Google Gemini REST API via HTTPS POST."""
        endpoint = f"{GEMINI_API_BASE_URL}/{self.model_name}:generateContent?key={self.api_key}"

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}]
                }
            ],
            "systemInstruction": {
                "parts": [{"text": system_prompt}]
            },
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_output_tokens,
                "topP": 0.8
            }
        }

        headers = {"Content-Type": "application/json"}
        response = requests.post(endpoint, json=payload, headers=headers, timeout=20)

        if response.status_code != 200:
            raise RuntimeError(f"Gemini API error {response.status_code}: {response.text}")

        data = response.json()
        try:
            candidates = data.get("candidates", [])
            if candidates:
                first_candidate = candidates[0]
                content = first_candidate.get("content", {})
                parts = content.get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip()
        except Exception as ex:
            raise RuntimeError(f"Failed to parse Gemini response: {ex}")

        return "उत्तर प्राप्त करने में असमर्थ। कृपया पुनः प्रयास करें।"

    def _generate_local_fallback(self, system_prompt: str, user_prompt: str) -> str:
        """
        Intelligent local generator that extracts key actionable recommendations,
        dosages, and instructions directly from the retrieved RAG context in system_prompt.
        """
        # Extract RAG context section from system prompt
        context_marker = "RETRIEVED KNOWLEDGE BASE CONTEXT:"
        if context_marker in system_prompt:
            rag_context = system_prompt.split(context_marker, 1)[1].strip()
        else:
            rag_context = system_prompt

        is_hindi = bool(re.search(r"[\u0900-\u097F]", user_prompt))
        
        # Parse out bullet points and bold lines from top chunk in RAG context
        lines = rag_context.splitlines()
        actionable_points = []
        found_source = ""

        for line in lines:
            line_str = line.strip()
            if line_str.startswith("--- Source 1:"):
                found_source = line_str.replace("---", "").strip()
            # Capture doses, sprays, chemical names, or bold lines
            if any(marker in line_str.lower() for marker in ["dose:", "spray", "apply", "उपचार", "दवा", "स्प्रे", "लीटर", "acre", "kg", "ml"]):
                clean_pt = line_str.lstrip("-*•# ").strip()
                if (
                    len(clean_pt) > 15
                    and not clean_pt.startswith("Source")
                    and not clean_pt.startswith("[")
                    and not clean_pt.startswith("---")
                    and clean_pt not in actionable_points
                ):
                    actionable_points.append(clean_pt)
            if len(actionable_points) >= 4:
                break

        # If not enough specific lines found, grab clean descriptive sentences
        if not actionable_points:
            for line in lines:
                clean = line.strip().lstrip("-*•# ")
                if len(clean) > 30 and not clean.startswith("[") and not clean.startswith("Source"):
                    actionable_points.append(clean)
                if len(actionable_points) >= 3:
                    break

        # Format into crisp WhatsApp response
        if is_hindi:
            header = "🌾 *किसान भाई, आपके सवाल का समाधान:*"
            bullets = "\n".join([f"• {pt}" for pt in actionable_points[:3]])
            disclaimer = "\n\n⚠️ *सावधानी:* मौसम साफ होने पर ही छिड़काव करें।\n_🌾 किसान सहायक KrishiBot_"
        else:
            header = "🌾 *KrishiBot Advisory:*"
            bullets = "\n".join([f"• {pt}" for pt in actionable_points[:3]])
            disclaimer = "\n\n⚠️ *Precaution:* Spray during calm weather. Verify with your local KVK.\n_🌾 KrishiBot Farmer Assistant_"

        return f"{header}\n\n{bullets}{disclaimer}"
