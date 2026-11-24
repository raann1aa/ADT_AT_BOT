"""
Intelligent Agronomic Follow-Up and Missing Information Elicitation Engine.
Analyzes farmer profiles for missing agricultural parameters, selects prioritized questions,
respects verified data boundaries, and records safe unverified updates with audit history.
"""

import re
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, date

from database.connection import get_db_session
from database.models import Farmer, FarmPlot, CropRecord, SoilProfile
from database.enums import VerificationStatus, PlantingSeason, AreaUnit, ConversationState
from database.repositories import FarmerRepository, FieldHistoryRepository

logger = logging.getLogger("FollowupEngine")

# Priority order for asking missing agronomic parameters
FIELD_PRIORITY_ORDER = [
    "crop",
    "planting_date",
    "planting_season",
    "cultivated_area",
    "crop_variety",
    "soil_type",
    "irrigation_information",
    "crop_growth_stage",
    "npk_information"
]

# Multilingual friendly question templates (Marathi default, with Hindi & English support)
FOLLOWUP_TEMPLATES = {
    "crop": {
        "mr": "🌾 आपल्या शेतात सध्या कोणती मुख्य पिके घेतली आहेत? (उदा. ऊस, कांदा, कापूस, सोयाबीन)",
        "hi": "🌾 आपके खेत में अभी मुख्य फसल कौन सी लगी है? (जैसे: गन्ना, प्याज, कपास, सोयाबीन)",
        "en": "🌾 What is the primary crop currently planted on your farm?"
    },
    "planting_date": {
        "mr": "📅 आपल्या पिकाची लागवड / पेरणी कधी झाली आहे? (अंदाजे तारीख किंवा महिना सांगावा)",
        "hi": "📅 आपकी फसल की बुआई / रोपाई किस तारीख या महीने में हुई थी?",
        "en": "📅 When was your crop planted or sown? (Approximate date or month)"
    },
    "planting_season": {
        "mr": "🌱 ऊस / पिकाचा लागवड हंगाम कोणता आहे? (सुरू, आडसाली, पूर्वहंगामी किंवा खोडवा)",
        "hi": "🌱 गन्ने की बुआई का मौसम कौन सा है? (सुरू, अडसाली, पूर्व-मौसमी या पेड़ी/खोडवा)",
        "en": "🌱 What is the planting season? (Suru, Adsali, Pre-seasonal, or Ratoon)"
    },
    "cultivated_area": {
        "mr": "📏 आपले एकूण शेतक्षेत्र किंवा या पिकाखालील क्षेत्र किती एकर आहे?",
        "hi": "📏 इस फसल का रकबा या आपका कुल खेत कितने एकड़ का है?",
        "en": "📏 How many acres of land are under this crop?"
    },
    "crop_variety": {
        "mr": "🌿 आपण कोणत्या वाणाची (उदा. को ८६०३२, कोएम ०२६५, फुले २६५) लागवड केली आहे?",
        "hi": "🌿 आपने किस किस्म (जैसे: को 86032, कोएम 0265) की बुआई की है?",
        "en": "🌿 What crop variety have you planted (e.g. Co 86032, CoM 0265)?"
    },
    "soil_type": {
        "mr": "🏞️ आपल्या शेतातील मातीचा प्रकार कोणता आहे? (उदा. काळी कसदार, मध्यम काळी, हलकी किंवा गाळाची)",
        "hi": "🏞️ आपके खेत की मिट्टी किस प्रकार की है? (जैसे: भारी काली, मध्यम, दोमट या बलुई)",
        "en": "🏞️ What is the soil type of your plot? (e.g. Black cotton, Medium black, Loam)"
    },
    "irrigation_information": {
        "mr": "💧 आपल्या शेतात सिंचनाची कोणती सोय आहे? (उदा. ठिबक सिंचन, तुषार किंवा मोकळे पाणी)",
        "hi": "💧 आपके खेत में सिंचाई की क्या व्यवस्था है? (ड्रिप, स्प्रिंकलर या खुला पानी)",
        "en": "💧 What irrigation method is used? (Drip, Sprinkler, or Flood irrigation)"
    },
    "crop_growth_stage": {
        "mr": "🌿 पीक सध्या कोणत्या वाढीच्या अवस्थेत आहे? (उदा. उगवण, फुटवे फुटणे, मोठी वाढ किंवा पक्वता)",
        "hi": "🌿 फसल अभी किस अवस्था में है? (जैसे: कल्ले फूटना, बढ़वार या परिपक्वता)",
        "en": "🌿 What is the current growth stage of your crop?"
    },
    "npk_information": {
        "mr": "🧪 आपण माती परीक्षण केले आहे का, किंवा अलीकडे कोणते खत (NPK) दिले आहे?",
        "hi": "🧪 क्या आपने मिट्टी परीक्षण कराया है, या हाल ही में कौन सा खाद दिया है?",
        "en": "🧪 Have you done soil testing, or what NPK fertilizer was applied recently?"
    }
}


class FollowupEngine:
    """
    Evaluates profile completeness and generates structured, gentle follow-up questions.
    Protects verified values and safely records unverified user responses.
    """

    def inspect_missing_fields(self, farmer: Optional[Farmer]) -> Dict[str, VerificationStatus]:
        """
        Inspects farmer profile, plots, crops, and soils to categorize each field's status:
        VERIFIED, UNVERIFIED, MISSING, NOT_PROVIDED, or UNKNOWN.
        """
        status_map: Dict[str, VerificationStatus] = {}

        if not farmer:
            for field_name in FIELD_PRIORITY_ORDER:
                status_map[field_name] = VerificationStatus.MISSING
            return status_map

        # 1. Farm plot fields
        plot = farmer.plots[0] if (farmer.plots and len(farmer.plots) > 0) else None

        if plot:
            # Area
            if plot.area_status == VerificationStatus.VERIFIED:
                status_map["cultivated_area"] = VerificationStatus.VERIFIED
            elif plot.land_area and plot.land_area > 0:
                status_map["cultivated_area"] = plot.area_status
            else:
                status_map["cultivated_area"] = VerificationStatus.MISSING

            # Irrigation
            if plot.irrigation_status == VerificationStatus.VERIFIED:
                status_map["irrigation_information"] = VerificationStatus.VERIFIED
            elif plot.has_drip_irrigation is not None:
                status_map["irrigation_information"] = plot.irrigation_status
            else:
                status_map["irrigation_information"] = VerificationStatus.MISSING

            # 2. Crop fields
            crop = plot.crops[0] if (plot.crops and len(plot.crops) > 0) else None
            if crop:
                status_map["crop"] = crop.crop_status
                status_map["crop_variety"] = crop.variety_status
                status_map["planting_date"] = crop.planting_date_status
                status_map["planting_season"] = crop.season_status
                status_map["crop_growth_stage"] = crop.stage_status
            else:
                status_map["crop"] = VerificationStatus.MISSING
                status_map["crop_variety"] = VerificationStatus.MISSING
                status_map["planting_date"] = VerificationStatus.MISSING
                status_map["planting_season"] = VerificationStatus.MISSING
                status_map["crop_growth_stage"] = VerificationStatus.MISSING

            # 3. Soil fields
            soil = plot.soil_profiles[0] if (plot.soil_profiles and len(plot.soil_profiles) > 0) else None
            if soil:
                status_map["soil_type"] = soil.soil_type_status
                status_map["soil_fertility"] = soil.fertility_status
                status_map["npk_information"] = soil.npk_status
            else:
                status_map["soil_type"] = VerificationStatus.MISSING
                status_map["soil_fertility"] = VerificationStatus.MISSING
                status_map["npk_information"] = VerificationStatus.MISSING
        else:
            for field_name in FIELD_PRIORITY_ORDER:
                status_map[field_name] = VerificationStatus.MISSING

        return status_map

    def select_next_field_to_elicit(
        self,
        status_map: Dict[str, VerificationStatus],
        asked_fields: Optional[List[str]] = None
    ) -> Optional[str]:
        """
        Selects the single highest priority missing or unverified parameter to ask next.
        Avoids repeating questions that were already asked in recent dialog turns.
        """
        asked = set(asked_fields or [])

        # Iterate in prioritized agronomic order
        for field_name in FIELD_PRIORITY_ORDER:
            current_status = status_map.get(field_name, VerificationStatus.MISSING)
            
            # If already verified, never ask
            if current_status == VerificationStatus.VERIFIED:
                continue

            # If already asked in this session, skip to prevent repeated questioning
            if field_name in asked:
                continue

            # Eligible for gentle elicitation
            if current_status in (
                VerificationStatus.MISSING,
                VerificationStatus.NOT_PROVIDED,
                VerificationStatus.UNKNOWN,
                VerificationStatus.UNVERIFIED
            ):
                return field_name

        return None

    def generate_question(self, field_name: str, preferred_language: str = "mr") -> str:
        """Retrieves localized gentle question text for a specific missing parameter."""
        lang = preferred_language if preferred_language in ("mr", "hi", "en") else "mr"
        field_templates = FOLLOWUP_TEMPLATES.get(field_name, FOLLOWUP_TEMPLATES["crop"])
        return field_templates.get(lang, field_templates["mr"])

    def parse_and_apply_answer(
        self,
        farmer_id: int,
        field_name: str,
        message_text: str,
        extracted_entities: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        Parses incoming farmer message and safely writes the updated field with
        VerificationStatus.UNVERIFIED and audit changelog tracking.
        Never overwrites a VERIFIED field.
        """
        with get_db_session() as session:
            repo = FarmerRepository(session)
            history_repo = FieldHistoryRepository(session)
            farmer = repo.get_by_id(farmer_id)

            if not farmer:
                return False, f"Farmer ID #{farmer_id} not found."

            if not farmer.plots:
                # Create default plot
                plot = repo.add_plot(
                    farmer_id=farmer.id,
                    plot_identifier="PLOT-1",
                    land_area=3.0,
                    area_status=VerificationStatus.UNVERIFIED,
                    data_source="WHATSAPP_CHAT"
                )
            else:
                plot = farmer.plots[0]

            crop = plot.crops[0] if plot.crops else None
            soil = plot.soil_profiles[0] if plot.soil_profiles else None

            # Route by target field
            if field_name == "cultivated_area":
                if plot.area_status == VerificationStatus.VERIFIED:
                    return False, "Land area is VERIFIED; protected from AI overwrite."
                area_val = extracted_entities.get("land_area")
                if not area_val:
                    # Regex fallback
                    m = re.search(r"(\d+(\.\d+)?)", message_text)
                    if m:
                        try:
                            area_val = float(m.group(1))
                        except Exception:
                            pass
                if area_val:
                    old_area = plot.land_area
                    plot.land_area = area_val
                    plot.area_status = VerificationStatus.UNVERIFIED
                    plot.data_source = "WHATSAPP_CHAT"
                    history_repo.record_change(
                        entity_type="FarmPlot",
                        entity_id=plot.id,
                        field_name="land_area",
                        old_value=old_area,
                        new_value=area_val,
                        changed_by="FARMER_AI_AGENT",
                        change_source="WHATSAPP_CHAT"
                    )
                    session.commit()
                    return True, f"Updated land area to {area_val} acres."

            elif field_name == "crop":
                crop_val = extracted_entities.get("crop")
                if not crop_val:
                    # Look for keywords in text
                    lower = message_text.lower()
                    if any(k in lower for k in ["ऊस", "oos", "ganna", "sugarcane"]):
                        crop_val = "Sugarcane"
                    elif any(k in lower for k in ["कांदा", "kanda", "onion"]):
                        crop_val = "Onion"
                    elif any(k in lower for k in ["कापूस", "kapas", "cotton"]):
                        crop_val = "Cotton"
                    elif any(k in lower for k in ["सोयाबीन", "soybean"]):
                        crop_val = "Soybean"

                if crop_val:
                    if crop:
                        if crop.crop_status == VerificationStatus.VERIFIED:
                            return False, "Crop is VERIFIED; protected from AI overwrite."
                        old_crop = crop.crop_name
                        crop.crop_name = crop_val
                        crop.crop_status = VerificationStatus.UNVERIFIED
                        history_repo.record_change(
                            entity_type="CropRecord",
                            entity_id=crop.id,
                            field_name="crop_name",
                            old_value=old_crop,
                            new_value=crop_val,
                            changed_by="FARMER_AI_AGENT",
                            change_source="WHATSAPP_CHAT"
                        )
                    else:
                        crop = repo.add_crop_to_plot(
                            farm_plot_id=plot.id,
                            crop_name=crop_val,
                            crop_status=VerificationStatus.UNVERIFIED,
                            data_source="WHATSAPP_CHAT"
                        )
                    session.commit()
                    return True, f"Updated crop to {crop_val}."

            elif field_name == "planting_season":
                season_val = extracted_entities.get("planting_season")
                if not season_val:
                    lower = message_text.lower()
                    if any(k in lower for k in ["adsali", "आडसाली"]):
                        season_val = PlantingSeason.ADSALI
                    elif any(k in lower for k in ["suru", "सुरू"]):
                        season_val = PlantingSeason.SURU
                    elif any(k in lower for k in ["pre-seasonal", "पूर्वहंगामी"]):
                        season_val = PlantingSeason.PRE_SEASONAL

                if season_val and crop:
                    if crop.season_status == VerificationStatus.VERIFIED:
                        return False, "Planting season is VERIFIED; protected from overwrite."
                    old_season = crop.planting_season.value if crop.planting_season else None
                    crop.planting_season = season_val if isinstance(season_val, PlantingSeason) else PlantingSeason(season_val)
                    crop.season_status = VerificationStatus.UNVERIFIED
                    history_repo.record_change(
                        entity_type="CropRecord",
                        entity_id=crop.id,
                        field_name="planting_season",
                        old_value=old_season,
                        new_value=season_val,
                        changed_by="FARMER_AI_AGENT",
                        change_source="WHATSAPP_CHAT"
                    )
                    session.commit()
                    return True, f"Updated planting season to {season_val}."

            elif field_name == "soil_type":
                soil_val = extracted_entities.get("soil_type")
                if not soil_val:
                    lower = message_text.lower()
                    if any(k in lower for k in ["काळी", "black"]):
                        soil_val = "Black Cotton"
                    elif any(k in lower for k in ["मध्यम", "medium"]):
                        soil_val = "Medium Black"
                    elif any(k in lower for k in ["तांबडी", "red"]):
                        soil_val = "Red Loam"

                if soil_val:
                    if soil:
                        if soil.soil_type_status == VerificationStatus.VERIFIED:
                            return False, "Soil type is VERIFIED; protected from overwrite."
                        old_soil = soil.soil_type
                        soil.soil_type = soil_val
                        soil.soil_type_status = VerificationStatus.UNVERIFIED
                        history_repo.record_change(
                            entity_type="SoilProfile",
                            entity_id=soil.id,
                            field_name="soil_type",
                            old_value=old_soil,
                            new_value=soil_val,
                            changed_by="FARMER_AI_AGENT",
                            change_source="WHATSAPP_CHAT"
                        )
                    else:
                        soil = repo.add_soil_profile(
                            farm_plot_id=plot.id,
                            soil_type=soil_val,
                            soil_type_status=VerificationStatus.UNVERIFIED,
                            data_source="WHATSAPP_CHAT"
                        )
                    session.commit()
                    return True, f"Updated soil type to {soil_val}."

            elif field_name == "irrigation_information":
                has_drip = extracted_entities.get("has_drip_irrigation")
                if has_drip is None:
                    lower = message_text.lower()
                    if any(k in lower for k in ["ठिबक", "drip", "होय", "yes"]):
                        has_drip = True
                    elif any(k in lower for k in ["नाही", "no", "पाटपाणी", "flood"]):
                        has_drip = False

                if has_drip is not None:
                    if plot.irrigation_status == VerificationStatus.VERIFIED:
                        return False, "Irrigation status is VERIFIED; protected from overwrite."
                    old_drip = plot.has_drip_irrigation
                    plot.has_drip_irrigation = has_drip
                    plot.irrigation_status = VerificationStatus.UNVERIFIED
                    history_repo.record_change(
                        entity_type="FarmPlot",
                        entity_id=plot.id,
                        field_name="has_drip_irrigation",
                        old_value=old_drip,
                        new_value=has_drip,
                        changed_by="FARMER_AI_AGENT",
                        change_source="WHATSAPP_CHAT"
                    )
                    session.commit()
                    return True, f"Updated drip irrigation to {has_drip}."

            return False, "Could not extract parameter value from response."
