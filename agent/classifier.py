"""
Message Classification and Agricultural Intent Engine for WhatsApp Farmer Communication.
Supports 13 granular agricultural intents with full backward compatibility to legacy 5 categories,
incorporating comprehensive Marathi, Hindi, English, and transliterated farming terminology,
entity extraction, and confidence scoring.
"""

import re
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

from database.enums import AgriculturalIntent


class MessageCategory(str, Enum):
    """Legacy 5-category taxonomy preserved for backward compatibility."""
    FARMING_QUERY = "FARMING_QUERY"
    GREETING_OR_CHATTER = "GREETING_OR_CHATTER"
    SPAM_OR_FORWARD = "SPAM_OR_FORWARD"
    FORM_RELATED = "FORM_RELATED"
    URGENT_DISTRESS = "URGENT_DISTRESS"


# Mapping from 13 granular AgriculturalIntents to legacy 5 MessageCategories
INTENT_TO_LEGACY_CATEGORY: Dict[AgriculturalIntent, MessageCategory] = {
    AgriculturalIntent.CROP_DISEASE_PEST: MessageCategory.FARMING_QUERY,
    AgriculturalIntent.FERTILIZER_NUTRITION: MessageCategory.FARMING_QUERY,
    AgriculturalIntent.IRRIGATION_WATER: MessageCategory.FARMING_QUERY,
    AgriculturalIntent.VARIETY_SELECTION: MessageCategory.FARMING_QUERY,
    AgriculturalIntent.PLANTING_SOWING: MessageCategory.FARMING_QUERY,
    AgriculturalIntent.HARVESTING_POST_HARVEST: MessageCategory.FARMING_QUERY,
    AgriculturalIntent.WEATHER_CLIMATE: MessageCategory.FARMING_QUERY,
    AgriculturalIntent.CDO_COORDINATION_INQUIRY: MessageCategory.FARMING_QUERY,
    AgriculturalIntent.GOVERNMENT_SCHEME_SUBSIDY: MessageCategory.FARMING_QUERY,
    AgriculturalIntent.FARMER_PROFILE_UPDATE: MessageCategory.FARMING_QUERY,
    AgriculturalIntent.GENERAL_GREETING: MessageCategory.GREETING_OR_CHATTER,
    AgriculturalIntent.DISTRESS_EMERGENCY: MessageCategory.URGENT_DISTRESS,
    AgriculturalIntent.OFF_TOPIC_OTHER: MessageCategory.SPAM_OR_FORWARD,
}


@dataclass
class ClassificationResult:
    """Rich classification payload supporting both legacy and Phase 3 capabilities."""
    category: MessageCategory
    confidence: float
    reason: str
    should_reply: bool
    requires_escalation: bool = False
    detected_intent: Optional[str] = None
    # Phase 3 Granular Taxonomy & Context
    intent: Optional[AgriculturalIntent] = None
    extracted_entities: Dict[str, Any] = field(default_factory=dict)
    missing_parameters: List[str] = field(default_factory=list)
    requires_clarification: bool = False
    next_action: str = "ANSWER"  # "ANSWER", "IGNORE", "ESCALATE", "FORM_HELP", "CLARIFY"


# ---------------------------------------------------------------------------
# Multilingual Regex & Keyword Patterns (Marathi, Hindi, English, Transliterated)
# ---------------------------------------------------------------------------

GREETING_PATTERNS = [
    r"^(good\s*(morning|evening|night|afternoon)|gm|gn|ge|ga)\b",
    r"^(सुप्रभात|शुभ\s*(प्रभात|रात्रि|संध्या|दिवस))\b",
    r"^(राम\s*राम|ram\s*ram|जय\s*श्री\s*राम|jai\s*shree?\s*ram|राधे\s*राधे|radhe\s*radhe|हर\s*हर\s*महादेव|har\s*har\s*mahadev|जय\s*भोले)\b",
    r"^(नमस्ते|नमस्कार|प्रणाम|namaste|namaskar|pranam|जय\s*जवान\s*जय\s*किसान|जय\s*महाराष्ट्र)\b",
    r"^(सत\s*श्री\s*अकाल|sat\s*sri\s*akal|सलाम|आदाब|hello|hi|hey)\b",
    r"^(ok|okay|thik\s*hai|theek\s*hai|done|dhanyawad|shukriya|thanks|thank\s*you|धन्यवाद|शुक्रिया|ठीक\s*आहे|ठीक\s*है)[\s!.]*$",
]

SPAM_PATTERNS = [
    r"(forwarded\s*as\s*received|फॉरवर्ड|शेयर\s*करें|ग्रुप\s*मध्ये\s*पाठवा|ग्रुप\s*में\s*भेजें|like\s*and\s*subscribe)",
    r"(हैप्पी\s*(दिवाली|होली|ईद|नवरात्रि|क्रिसमस)|happy\s*(diwali|holi|eid|navratri|new\s*year))",
    r"(आज\s*का\s*सुविचार|thought\s*of\s*the\s*day|आज\s*का\s*पंचांग|राशिफल|horoscope)",
    r"(भगवान\s*(भला\s*करे|कृपा\s*करें)|देव\s*कल्याण\s*करो|god\s*bless\s*you)",
]

DISTRESS_PATTERNS = [
    r"(आत्महत्या|suicide|मरने\s*जा\s*रहा|जीव\s*देणार|जान\s*दे\s*दूंगा|curse\s*my\s*life|zeher\s*kha\s*liya|विष\s*घेतले|ज़हर\s*खा\s*लिया)",
    r"(hospital\s*emergency|urgent\s*help\s*death|fatal\s*poisoning|आग\s*लागली|शेत\s*जळून\s*खाक|flood\s*disaster)",
]

# Form & Subsidy
FORM_PATTERNS = [
    r"(google\s*form|गूगल\s*फॉर्म|form\s*link|फॉर्म\s*लिंक|form\s*bhar\s*diya|form\s*submit|फॉर्म\s*भरला|फॉर्म\s*भर\s*दिया|फॉर्म\s*उघडत\s*नाही|फॉर्म\s*नहीं\s*खुल\s*रहा)",
    r"(details\s*fill|farm\s*details|weekly\s*form|साप्ताहिक\s*फॉर्म|साप्ताहिक\s*सर्वेक्षण)",
]

SUBSIDY_PATTERNS = [
    r"(अनुदान|subsidy|mahadbt|महाडीबीटी|pm\s*kisan|पीक\s*विमा|fasal\s*bima|pik\s*vima|योजना|scheme|मृदा\s*आरोग्य|soil\s*health\s*card|ठिबक\s*अनुदान|drip\s*subsidy|कर्जमाफी|kcc)",
]

PROFILE_UPDATE_PATTERNS = [
    r"(\d+(\.\d+)?\s*(एकर|एकड|acre|acres|गुंठे|guntha)\s*(जमीन|रान|शेत|farm|land))",
    r"(लागवड\s*तारीख|planting\s*date|पेरणी\s*दिनांक|तारीख\s*आहे|date\s*is)",
    r"(काळी\s*माती|black\s*cotton|तांबडी\s*माती|गाळाची\s*माती|medium\s*black|clay\s*loam)",
    r"(माझे\s*नाव|my\s*name\s*is|गावाचे\s*नाव|village\s*is)",
]

CDO_PATTERNS = [
    r"(cdo|cane\s*development|ऊस\s*विकास\s*अधिकारी|कारखाना|factory|sugar\s*mill|ऊस\s*नोंद|cane\s*registration|स्लिप|slip|वजन\s*काटा|फील्ड\s*व्हिजिट|field\s*visit)",
]

FERTILIZER_PATTERNS = [
    r"(खत|खाद|fertilizer|युरिया|urea|डीएपी|dap|एनपीके|npk|पोटॅश|potash|10:26:26|12:32:16|19:19:19|0:52:34|0:0:50)",
    r"(सूक्ष्म\s*अन्नद्रव्य|micronutrient|झिंक|zinc|फेरस|ferrous|सल्फर|sulphur|शेणखत|fym|कंपोस्ट|जिवाणू\s*खत|बायोफर्टिलायझर|बेसल\s*डोस|basal\s*dose)",
    r"(खताचे\s*डोस|fertilizer\s*dose|खत\s*व्यवस्थापन|खत\s*कधी\s*द्यावे)",
]

IRRIGATION_PATTERNS = [
    r"(ठिबक|drip|तुषार|sprinkler|सिंचन|irrigation|पाणी\s*(व्यवस्थापन|कधी\s*द्यावे|पाळी|ताण)|water\s*schedule|water\s*stress|पाण्याचा\s*ताण|मोटर|पंप)",
]

VARIETY_PATTERNS = [
    r"(वाण|variety|जात|बेणे|seed\s*setts|co\s*86032|८६०३२|com\s*0265|०२६५|co\s*09057|०९०५७|vsi\s*434|फुले\s*(२६५|समर्थ)|भीमा\s*(सुपर|किरण)|पंचगंगा)",
    r"(कोणते\s*वाण|which\s*variety|सुधारित\s*वाण|बेणे\s*प्रक्रिया|seed\s*treatment)",
]

PLANTING_PATTERNS = [
    r"(लागवड|lagwad|planting|पेरणी|sowing|sow|plant|टोकण|रोप\s*लागवड)",
    r"(सुरू\s*लागवड|suru|आडसाली|adsali|पूर्वहंगामी|pre-seasonal|हंगाम|season|खरिप|kharif|रब्बी|rabi)",
    r"(सरी\s*पद्धत|पट्टा\s*पद्धत|अंतर|spacing|५\s*फूट|4\s*feet|रोपे|seedling)",
]

HARVESTING_PATTERNS = [
    r"(तोडणी|todani|harvest|cutting|ऊस\s*तोड|कापणी)",
    r"(खोडवा|khodwa|ratoon|खोडवा\s*व्यवस्थापन|पाचट\s*व्यवस्थापन|mulching|बगलबगल\s*छाटणी|stubble\s*shaving)",
    r"(साखर\s*उतारा|sugar\s*recovery|पक्वता|maturity|brix|ब्रिक्स)",
]

WEATHER_PATTERNS = [
    r"(पाऊस|rain|barish|हवामान|weather|mausam|गारपीट|hailstorm|धुके|fog|थंडी|cold|frost|ढगाळ|cloudy|तापमान|temperature)",
]

PEST_DISEASE_PATTERNS = [
    r"(कीड|कीटक|pest|keeda|रोग|disease|rog|bimari|बुरशी|fungus|fungicide|बुरशीनाशक|फवारणी|spray|औषध|dawai)",
    r"(हुमणी|white\s*grub|तांबेरा|rust|काणी|smut|खोडकीड|shoot\s*borer|शेंडाकीड|top\s*borer|पांढरी\s*माशी|whitefly|तुडतुडे|jassids|थ्रिप्स|thrips|मावा|aphids|करपा|blight|सड|rot|विल्ट|wilt)",
    r"(पिवळे\s*पडणे|yellowing|पाने\s*सुकणे|वाळणे|curling|spots|ठिपके)",
]

QUESTION_INDICATORS = [
    r"\?",
    r"\b(kaise|kab|kya|kyu|kyon|kitna|kitni|kaun|kaunsa|kaha|kahan)\b",
    r"\b(कसे|कधी|काय|का|किती|कोणते|कुठे|उपाय|सांगा|औषध|फवारू)\b",
    r"\b(कैसे|कब|क्या|क्यों|कितना|कितनी|कौन|कौनसा|कहाँ|उपाय|दवा|बताएं|बताओ)\b",
    r"\b(how|what|when|why|which|where|suggest|recommend|dosage|treatment|control|remedy)\b"
]


class WhatsAppMessageClassifier:
    """
    Intelligent Multilingual Agricultural Intent Classifier for KrishiBot.
    Categorizes farmer messages across 13 distinct agronomic intents with entity extraction,
    confidence scoring, and seamless backward compatibility to legacy categories.
    """

    def __init__(self):
        self.greeting_re = [re.compile(p, re.IGNORECASE) for p in GREETING_PATTERNS]
        self.spam_re = [re.compile(p, re.IGNORECASE) for p in SPAM_PATTERNS]
        self.distress_re = [re.compile(p, re.IGNORECASE) for p in DISTRESS_PATTERNS]
        self.form_re = [re.compile(p, re.IGNORECASE) for p in FORM_PATTERNS]
        self.subsidy_re = [re.compile(p, re.IGNORECASE) for p in SUBSIDY_PATTERNS]
        self.profile_update_re = [re.compile(p, re.IGNORECASE) for p in PROFILE_UPDATE_PATTERNS]
        self.cdo_re = [re.compile(p, re.IGNORECASE) for p in CDO_PATTERNS]
        self.fertilizer_re = [re.compile(p, re.IGNORECASE) for p in FERTILIZER_PATTERNS]
        self.irrigation_re = [re.compile(p, re.IGNORECASE) for p in IRRIGATION_PATTERNS]
        self.variety_re = [re.compile(p, re.IGNORECASE) for p in VARIETY_PATTERNS]
        self.planting_re = [re.compile(p, re.IGNORECASE) for p in PLANTING_PATTERNS]
        self.harvesting_re = [re.compile(p, re.IGNORECASE) for p in HARVESTING_PATTERNS]
        self.weather_re = [re.compile(p, re.IGNORECASE) for p in WEATHER_PATTERNS]
        self.pest_disease_re = [re.compile(p, re.IGNORECASE) for p in PEST_DISEASE_PATTERNS]
        self.question_re = [re.compile(p, re.IGNORECASE) for p in QUESTION_INDICATORS]

    def extract_entities(self, text: str) -> Dict[str, Any]:
        """Extracts agricultural entities (crop, area, planting date/season, soil, etc.) from message."""
        entities: Dict[str, Any] = {}
        lower = text.lower()

        # Crop recognition
        crops = {
            "sugarcane": ["sugarcane", "गन्ना", "ऊस", "oos", "ganna"],
            "onion": ["onion", "प्याज", "कांदा", "kanda", "pyaj"],
            "cotton": ["cotton", "कपास", "कापूस", "kapas"],
            "soybean": ["soybean", "सोयाबीन", "soyabean"],
            "wheat": ["wheat", "गेहूं", "गहू", "gehu", "gahu"],
            "maize": ["maize", "मक्का", "मका", "makka"],
            "tomato": ["tomato", "टमाटर", "टोमॅटो", "tamatar"]
        }
        for crop_name, keywords in crops.items():
            if any(k in lower for k in keywords):
                entities["crop"] = crop_name.capitalize()
                break

        # Area recognition (e.g. "4 acres", "2.5 एकर", "20 गुंठे")
        area_match = re.search(r"(\d+(\.\d+)?)\s*(acre|acres|एकर|एकड|guntha|gunthe|गुंठे|हेक्टर|hectare)", lower)
        if area_match:
            try:
                entities["land_area"] = float(area_match.group(1))
                unit_str = area_match.group(3)
                if any(u in unit_str for u in ["guntha", "गुंठे"]):
                    entities["area_unit"] = "GUNTHAS"
                elif any(u in unit_str for u in ["hectare", "हेक्टर"]):
                    entities["area_unit"] = "HECTARES"
                else:
                    entities["area_unit"] = "ACRES"
            except Exception:
                pass

        # Sugarcane season recognition
        if any(w in lower for w in ["adsali", "आडसाली"]):
            entities["planting_season"] = "ADSALI"
        elif any(w in lower for w in ["suru", "सुरू"]):
            entities["planting_season"] = "SURU"
        elif any(w in lower for w in ["pre-seasonal", "पूर्वहंगामी", "pre seasonal"]):
            entities["planting_season"] = "PRE_SEASONAL"
        elif any(w in lower for w in ["khodwa", "खोडवा", "ratoon"]):
            entities["is_ratoon"] = True

        # Variety recognition
        variety_match = re.search(r"\b(co\s*86032|86032|८६०३२|को\s*८६०३२|com\s*0265|0265|०२६५|co\s*09057|09057|vsi\s*434|फुले\s*२६५)\b", lower)
        if variety_match:
            var_raw = variety_match.group(0).upper().replace(" ", "")
            if "८६०३२" in var_raw:
                entities["crop_variety"] = "CO86032"
            elif "०२६५" in var_raw:
                entities["crop_variety"] = "COM0265"
            else:
                entities["crop_variety"] = var_raw

        # Soil type recognition
        if any(s in lower for s in ["काळी", "black cotton", "black soil", "भारी"]):
            entities["soil_type"] = "Black Cotton"
        elif any(s in lower for s in ["मध्यम", "medium black"]):
            entities["soil_type"] = "Medium Black"
        elif any(s in lower for s in ["तांबडी", "red soil", "हलकी"]):
            entities["soil_type"] = "Red Loam"

        # Drip irrigation mention
        if any(d in lower for d in ["ठिबक", "drip", "ड्रिप"]):
            entities["has_drip_irrigation"] = True

        return entities

    def classify(self, message: str) -> ClassificationResult:
        """
        Classifies message across the 13-intent agricultural taxonomy.
        Provides 100% backward compatibility for callers expecting legacy MessageCategory.
        """
        if not message or not message.strip():
            return ClassificationResult(
                category=MessageCategory.GREETING_OR_CHATTER,
                intent=AgriculturalIntent.GENERAL_GREETING,
                confidence=1.0,
                reason="Empty message",
                should_reply=False,
                next_action="IGNORE"
            )

        text = message.strip()
        lower_text = text.lower()
        entities = self.extract_entities(text)
        has_question = any(p.search(lower_text) for p in self.question_re)

        # 1. Urgent Distress / Emergency (Top Priority)
        for pattern in self.distress_re:
            if pattern.search(lower_text):
                return ClassificationResult(
                    category=MessageCategory.URGENT_DISTRESS,
                    intent=AgriculturalIntent.DISTRESS_EMERGENCY,
                    confidence=0.98,
                    reason="Matched crisis/distress pattern - requires human escalation",
                    should_reply=True,
                    requires_escalation=True,
                    detected_intent="emergency_distress",
                    extracted_entities=entities,
                    next_action="ESCALATE"
                )

        # 2. Government Schemes & Subsidies (Including Google Form links)
        for pattern in self.form_re:
            if pattern.search(lower_text):
                return ClassificationResult(
                    category=MessageCategory.FORM_RELATED,
                    intent=AgriculturalIntent.GOVERNMENT_SCHEME_SUBSIDY,
                    confidence=0.95,
                    reason="Matched weekly Google Form inquiry or submission",
                    should_reply=True,
                    detected_intent="google_form_inquiry",
                    extracted_entities=entities,
                    next_action="FORM_HELP"
                )

        for pattern in self.subsidy_re:
            if pattern.search(lower_text):
                return ClassificationResult(
                    category=MessageCategory.FARMING_QUERY,
                    intent=AgriculturalIntent.GOVERNMENT_SCHEME_SUBSIDY,
                    confidence=0.92,
                    reason="Matched government scheme, subsidy, or crop insurance inquiry",
                    should_reply=True,
                    detected_intent="government_scheme_subsidy",
                    extracted_entities=entities,
                    next_action="ANSWER"
                )

        # 3. Farmer Profile Update (Self-supplied farm facts)
        if any(p.search(lower_text) for p in self.profile_update_re) and len(entities) >= 1:
            return ClassificationResult(
                category=MessageCategory.FARMING_QUERY,
                intent=AgriculturalIntent.FARMER_PROFILE_UPDATE,
                confidence=0.92,
                reason="Farmer self-reported farm profile parameters (area, soil, crop, variety)",
                should_reply=True,
                detected_intent="farmer_profile_update",
                extracted_entities=entities,
                next_action="ANSWER"
            )

        # 8. Harvesting & Post-Harvest / Ratoon Management
        for pattern in self.harvesting_re:
            if pattern.search(lower_text):
                return ClassificationResult(
                    category=MessageCategory.FARMING_QUERY,
                    intent=AgriculturalIntent.HARVESTING_POST_HARVEST,
                    confidence=0.92 if has_question else 0.85,
                    reason="Cane harvesting, sugar recovery, or ratoon (खोडवा) management",
                    should_reply=True,
                    detected_intent="harvesting_post_harvest",
                    extracted_entities=entities,
                    next_action="ANSWER"
                )

        # 9. CDO & Sugar Mill Coordination
        for pattern in self.cdo_re:
            if pattern.search(lower_text):
                return ClassificationResult(
                    category=MessageCategory.FARMING_QUERY,
                    intent=AgriculturalIntent.CDO_COORDINATION_INQUIRY,
                    confidence=0.90,
                    reason="CDO officer visit, sugar factory slip, or crushing coordination inquiry",
                    should_reply=True,
                    detected_intent="cdo_coordination_inquiry",
                    extracted_entities=entities,
                    next_action="ANSWER"
                )

        # 5. Fertilizer & Soil Nutrition
        for pattern in self.fertilizer_re:
            if pattern.search(lower_text):
                missing = []
                if "crop" not in entities:
                    missing.append("crop")
                return ClassificationResult(
                    category=MessageCategory.FARMING_QUERY,
                    intent=AgriculturalIntent.FERTILIZER_NUTRITION,
                    confidence=0.94 if has_question else 0.88,
                    reason="NPK, micronutrient, or soil fertilizer inquiry",
                    should_reply=True,
                    detected_intent="fertilizer_nutrition",
                    extracted_entities=entities,
                    missing_parameters=missing,
                    next_action="ANSWER"
                )

        # 6. Irrigation & Water Management
        for pattern in self.irrigation_re:
            if pattern.search(lower_text):
                return ClassificationResult(
                    category=MessageCategory.FARMING_QUERY,
                    intent=AgriculturalIntent.IRRIGATION_WATER,
                    confidence=0.92 if has_question else 0.85,
                    reason="Drip or furrow irrigation schedule inquiry",
                    should_reply=True,
                    detected_intent="irrigation_water",
                    extracted_entities=entities,
                    next_action="ANSWER"
                )

        # 7. Variety Selection & Seed Quality
        for pattern in self.variety_re:
            if pattern.search(lower_text):
                return ClassificationResult(
                    category=MessageCategory.FARMING_QUERY,
                    intent=AgriculturalIntent.VARIETY_SELECTION,
                    confidence=0.92 if has_question else 0.85,
                    reason="Crop variety, seed sett, or nursery plant selection inquiry",
                    should_reply=True,
                    detected_intent="variety_selection",
                    extracted_entities=entities,
                    next_action="ANSWER"
                )

        # 8. Planting & Sowing Practices
        for pattern in self.planting_re:
            if pattern.search(lower_text):
                return ClassificationResult(
                    category=MessageCategory.FARMING_QUERY,
                    intent=AgriculturalIntent.PLANTING_SOWING,
                    confidence=0.92 if has_question else 0.85,
                    reason="Planting season, spacing, or sowing method inquiry",
                    should_reply=True,
                    detected_intent="planting_sowing",
                    extracted_entities=entities,
                    next_action="ANSWER"
                )

        # 9. Harvesting & Post-Harvest / Ratoon Management
        for pattern in self.harvesting_re:
            if pattern.search(lower_text):
                return ClassificationResult(
                    category=MessageCategory.FARMING_QUERY,
                    intent=AgriculturalIntent.HARVESTING_POST_HARVEST,
                    confidence=0.92 if has_question else 0.85,
                    reason="Cane harvesting, sugar recovery, or ratoon (खोडवा) management",
                    should_reply=True,
                    detected_intent="harvesting_post_harvest",
                    extracted_entities=entities,
                    next_action="ANSWER"
                )

        # 10. Weather & Climate Advisories
        for pattern in self.weather_re:
            if pattern.search(lower_text):
                return ClassificationResult(
                    category=MessageCategory.FARMING_QUERY,
                    intent=AgriculturalIntent.WEATHER_CLIMATE,
                    confidence=0.90 if has_question else 0.82,
                    reason="Rainfall, weather, or temperature stress advisory",
                    should_reply=True,
                    detected_intent="weather_climate",
                    extracted_entities=entities,
                    next_action="ANSWER"
                )

        # 11. Pest & Disease Diagnosis and Treatment
        for pattern in self.pest_disease_re:
            if pattern.search(lower_text):
                missing = []
                if "crop" not in entities:
                    missing.append("crop")
                return ClassificationResult(
                    category=MessageCategory.FARMING_QUERY,
                    intent=AgriculturalIntent.CROP_DISEASE_PEST,
                    confidence=0.95 if has_question else 0.88,
                    reason="Pest infestation, fungal/bacterial disease, or spray advisory",
                    should_reply=True,
                    detected_intent="crop_disease_pest",
                    extracted_entities=entities,
                    missing_parameters=missing,
                    next_action="ANSWER"
                )

        # 12. Spam / Broadcast Forwards
        for pattern in self.spam_re:
            if pattern.search(lower_text):
                return ClassificationResult(
                    category=MessageCategory.SPAM_OR_FORWARD,
                    intent=AgriculturalIntent.OFF_TOPIC_OTHER,
                    confidence=0.95,
                    reason="Matched broadcast/spam/holiday forward pattern",
                    should_reply=False,
                    detected_intent="spam_forward",
                    next_action="IGNORE"
                )

        # Pure emoji check
        clean_no_emoji = re.sub(r"[^\w\s]", "", text)
        if len(clean_no_emoji.strip()) <= 1 and len(text) <= 5:
            return ClassificationResult(
                category=MessageCategory.GREETING_OR_CHATTER,
                intent=AgriculturalIntent.GENERAL_GREETING,
                confidence=0.99,
                reason="Emoji or single punctuation character",
                should_reply=False,
                next_action="IGNORE"
            )

        # 13. Social Greetings & Pleasantries
        for pattern in self.greeting_re:
            if pattern.search(lower_text):
                return ClassificationResult(
                    category=MessageCategory.GREETING_OR_CHATTER,
                    intent=AgriculturalIntent.GENERAL_GREETING,
                    confidence=0.95,
                    reason="Matched standard social greeting/pleasantry",
                    should_reply=False,
                    detected_intent="social_greeting",
                    next_action="IGNORE"
                )

        # Generic question with agricultural terms
        if entities or has_question:
            confidence = 0.85 if entities else 0.60
            return ClassificationResult(
                category=MessageCategory.FARMING_QUERY,
                intent=AgriculturalIntent.CROP_DISEASE_PEST if entities else AgriculturalIntent.OFF_TOPIC_OTHER,
                confidence=confidence,
                reason="General inquiry containing agricultural terms",
                should_reply=True,
                detected_intent="general_farming_query",
                extracted_entities=entities,
                requires_clarification=(confidence < 0.65),
                next_action="ANSWER" if confidence >= 0.65 else "CLARIFY"
            )

        # Short casual chatter default
        if len(lower_text.split()) <= 4:
            return ClassificationResult(
                category=MessageCategory.GREETING_OR_CHATTER,
                intent=AgriculturalIntent.GENERAL_GREETING,
                confidence=0.75,
                reason="Short casual chatter without farming intent",
                should_reply=False,
                next_action="IGNORE"
            )

        # Unclassified non-farming conversation
        return ClassificationResult(
            category=MessageCategory.SPAM_OR_FORWARD,
            intent=AgriculturalIntent.OFF_TOPIC_OTHER,
            confidence=0.65,
            reason="Unclassified non-farming conversation",
            should_reply=False,
            next_action="IGNORE"
        )
