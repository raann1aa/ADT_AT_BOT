"""
Message Classification Engine for WhatsApp Farmer Groups.
Categorizes incoming messages into:
- FARMING_QUERY: Actionable agricultural questions -> Triggers RAG + LLM.
- GREETING_OR_CHATTER: Casual social greetings, 'good morning', emojis -> Silently Ignored.
- SPAM_OR_FORWARD: Viral forwards, religious wishes, jokes, political chatter -> Silently Ignored.
- FORM_RELATED: Questions or submissions regarding the weekly Google Form -> Form Assistant.
- URGENT_DISTRESS: Distress signals, crisis, or emergency -> Escalates to Human Admin.
"""

import re
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any

class MessageCategory(str, Enum):
    FARMING_QUERY = "FARMING_QUERY"
    GREETING_OR_CHATTER = "GREETING_OR_CHATTER"
    SPAM_OR_FORWARD = "SPAM_OR_FORWARD"
    FORM_RELATED = "FORM_RELATED"
    URGENT_DISTRESS = "URGENT_DISTRESS"

@dataclass
class ClassificationResult:
    category: MessageCategory
    confidence: float
    reason: str
    should_reply: bool
    requires_escalation: bool = False
    detected_intent: Optional[str] = None

# Common social greetings in English, Hindi, and Hinglish
GREETING_PATTERNS = [
    r"^(good\s*(morning|evening|night|afternoon)|gm|gn|ge|ga)\b",
    r"^(सुप्रभात|शुभ\s*(प्रभात|रात्रि|संध्या))\b",
    r"^(राम\s*राम|ram\s*ram|जय\s*श्री\s*राम|jai\s*shree?\s*ram|राधे\s*राधे|radhe\s*radhe|हर\s*हर\s*महादेव|har\s*har\s*mahadev|जय\s*भोले)\b",
    r"^(नमस्ते|नमस्कार|प्रणाम|namaste|namaskar|pranam|जय\s*जवान\s*जय\s*किसान)\b",
    r"^(सत\s*श्री\s*अकाल|sat\s*sri\s*akal|सलाम|आदाब|hello|hi|hey)\b",
    r"^(ok|okay|thik\s*hai|theek\s*hai|done|dhanyawad|shukriya|thanks|thank\s*you|धन्यवाद|शुक्रिया|ठीक\s*है)[\s!.]*$",
]

# Patterns representing forwards, festival spam, blessings
SPAM_PATTERNS = [
    r"(forwarded\s*as\s*received|फॉरवर्ड|शेयर\s*करें|ग्रुप\s*में\s*भेजें|like\s*and\s*subscribe)",
    r"(हैप्पी\s*(दिवाली|होली|ईद|नवरात्रि|क्रिसमस)|happy\s*(diwali|holi|eid|navratri|new\s*year))",
    r"(आज\s*का\s*सुविचार|thought\s*of\s*the\s*day|आज\s*का\s*पंचांग|राशिफल|horoscope)",
    r"(भगवान\s*(भला\s*करे|कृपा\s*करें)|god\s*bless\s*you)",
]

# Google Form related keywords
FORM_PATTERNS = [
    r"(google\s*form|गूगल\s*फॉर्म|form\s*link|फॉर्म\s*लिंक|form\s*bhar\s*diya|form\s*submit|फॉर्म\s*भर\s*दिया|फॉर्म\s*नहीं\s*खुल\s*रहा)",
    r"(details\s*fill|farm\s*details|weekly\s*form|साप्ताहिक\s*फॉर्म)",
]

# Distress / Emergency triggers
DISTRESS_PATTERNS = [
    r"(आत्महत्या|suicide|मरने\s*जा\s*रहा|जान\s*दे\s*दूंगा|curse\s*my\s*life|zeher\s*kha\s*liya|ज़हर\s*खा\s*लिया)",
    r"(hospital\s*emergency|urgent\s*help\s*death|fatal\s*poisoning)",
]

# Agricultural keywords indicating legitimate queries
AGRI_QUERY_KEYWORDS = [
    # Crops
    "wheat", "rice", "paddy", "cotton", "sugarcane", "onion", "tomato", "soybean", "maize", "gram", "mustard", "potato", "chilli",
    "गेहूं", "धान", "चावल", "कपास", "गन्ना", "प्याज", "टमाटर", "सोयाबीन", "मक्का", "चना", "सरसों", "आलू", "मिर्च",
    "gehu", "dhan", "kapas", "ganna", "pyaj", "kanda", "tamatar", "chana", "sarson", "aalu", "makka",
    
    # Farming concepts & problems
    "spray", "dawai", "khad", "urea", "dap", "npk", "fertilizer", "sinchai", "irrigation", "water", "paani",
    "keeda", "sundi", "pest", "disease", "rog", "bimari", "wilt", "blight", "rust", "rot", "curl", "thrips", "whitefly",
    "बीमारी", "रोग", "कीड़ा", "सुंडी", "खाद", "स्प्रे", "दवाई", "सिंचाई", "यूरिया", "पत्ता", "फूल", "फल", "पीला", "सड़न",
    "upchar", "ilaaj", "control", "dose", "rate", "msp", "mandi", "bhav", "rate", "kist", "installment",
    "pm kisan", "fasal bima", "kcc", "soil", "mitti", "seed", "beej", "subsidy", "solar pump", "drip"
]

# Question indicators in Hindi / English / Hinglish
QUESTION_INDICATORS = [
    r"\?",
    r"\b(kaise|kab|kya|kyu|kyon|kitna|kitni|kaun|kaunsa|kaha|kahan)\b",
    r"\b(कैसे|कब|क्या|क्यों|कितना|कितनी|कौन|कौनसा|कहाँ|उपाय|दवा|बताएं|बताओ)\b",
    r"\b(how|what|when|why|which|where|suggest|recommend|dosage|treatment|control)\b"
]

class WhatsAppMessageClassifier:
    """
    High-performance hybrid classifier for farmer WhatsApp messages.
    Uses regex rule heuristics for instant (<1ms) filtering of greetings & spam,
    and semantic token matching for agricultural query intent.
    """

    def __init__(self):
        self.greeting_re = [re.compile(p, re.IGNORECASE) for p in GREETING_PATTERNS]
        self.spam_re = [re.compile(p, re.IGNORECASE) for p in SPAM_PATTERNS]
        self.form_re = [re.compile(p, re.IGNORECASE) for p in FORM_PATTERNS]
        self.distress_re = [re.compile(p, re.IGNORECASE) for p in DISTRESS_PATTERNS]
        self.question_re = [re.compile(p, re.IGNORECASE) for p in QUESTION_INDICATORS]

    def _has_agri_keyword(self, lower_text: str) -> bool:
        """Checks for agricultural keywords using whole-word boundary matching."""
        tokens = set(re.findall(r"[\w\u0900-\u097F]+", lower_text))
        for k in AGRI_QUERY_KEYWORDS:
            if " " in k:
                if k in lower_text:
                    return True
            else:
                if k in tokens:
                    return True
        return False

    def classify(self, message: str) -> ClassificationResult:
        """
        Classifies an incoming WhatsApp message string.
        Returns ClassificationResult indicating category, confidence, and action.
        """
        if not message or not message.strip():
            return ClassificationResult(
                category=MessageCategory.GREETING_OR_CHATTER,
                confidence=1.0,
                reason="Empty message",
                should_reply=False
            )

        text = message.strip()
        lower_text = text.lower()

        # Step 1: Check Urgent Distress / Emergency (Top Priority)
        for pattern in self.distress_re:
            if pattern.search(lower_text):
                return ClassificationResult(
                    category=MessageCategory.URGENT_DISTRESS,
                    confidence=0.98,
                    reason="Matched crisis/distress pattern - requires human escalation",
                    should_reply=True,
                    requires_escalation=True,
                    detected_intent="emergency_distress"
                )

        # Step 2: Check Form-Related Messages
        for pattern in self.form_re:
            if pattern.search(lower_text):
                return ClassificationResult(
                    category=MessageCategory.FORM_RELATED,
                    confidence=0.92,
                    reason="Matched Google Form submission or enquiry pattern",
                    should_reply=True,
                    detected_intent="google_form_inquiry"
                )

        # Step 3: Check Spam / Forwarded Messages
        for pattern in self.spam_re:
            if pattern.search(lower_text):
                return ClassificationResult(
                    category=MessageCategory.SPAM_OR_FORWARD,
                    confidence=0.95,
                    reason="Matched broadcast/spam/holiday forward pattern",
                    should_reply=False,
                    detected_intent="spam_forward"
                )

        # Step 4: Check if message is pure emoji or very short non-agri word
        clean_text_no_emojis = re.sub(r"[^\w\s]", "", text)
        if len(clean_text_no_emojis.strip()) <= 1 and len(text) <= 5:
            return ClassificationResult(
                category=MessageCategory.GREETING_OR_CHATTER,
                confidence=0.99,
                reason="Emoji or single punctuation character",
                should_reply=False
            )

        # Step 5: Check Greetings & Social Chatter
        for pattern in self.greeting_re:
            if pattern.search(lower_text):
                # Ensure it doesn't also contain a farming query (e.g. "Good morning sir, gehu me dawai...")
                has_agri_content = self._has_agri_keyword(lower_text)
                if not has_agri_content:
                    return ClassificationResult(
                        category=MessageCategory.GREETING_OR_CHATTER,
                        confidence=0.95,
                        reason="Matched standard social greeting/pleasantry",
                        should_reply=False,
                        detected_intent="social_greeting"
                    )

        # Step 6: Check for Agricultural Query Indicators
        has_agri_keyword = self._has_agri_keyword(lower_text)
        has_question_indicator = any(pattern.search(lower_text) for pattern in self.question_re)

        if has_agri_keyword:
            confidence = 0.95 if has_question_indicator else 0.85
            return ClassificationResult(
                category=MessageCategory.FARMING_QUERY,
                confidence=confidence,
                reason="Contains agricultural domain concepts and problem indicators",
                should_reply=True,
                detected_intent="farming_problem_or_query"
            )

        # If it has question marks or question words but no agri keywords, check length
        if has_question_indicator and len(lower_text.split()) >= 3:
            # Ambiguous general question
            return ClassificationResult(
                category=MessageCategory.FARMING_QUERY,
                confidence=0.60,
                reason="General inquiry or question format",
                should_reply=True,
                detected_intent="general_question"
            )

        # Step 7: Fallback Default (Ignore short chatter/noise)
        if len(lower_text.split()) <= 4:
            return ClassificationResult(
                category=MessageCategory.GREETING_OR_CHATTER,
                confidence=0.75,
                reason="Short casual chatter without farming intent",
                should_reply=False
            )

        return ClassificationResult(
            category=MessageCategory.SPAM_OR_FORWARD,
            confidence=0.65,
            reason="Unclassified non-farming conversation",
            should_reply=False
        )
