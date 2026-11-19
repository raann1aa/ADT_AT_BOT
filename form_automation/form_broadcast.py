"""
Weekly Google Form Broadcaster for Multi-District WhatsApp Groups.
Automates broadcasting customized form links by district and schedules reminders.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from .models import DistrictGroup

logger = logging.getLogger("FormBroadcaster")

# Default registry of district groups
DEFAULT_DISTRICT_GROUPS = [
    DistrictGroup(
        group_id="group_nashik_01",
        group_name="नाशिक जिल्हा कांदा व भाजीपाला उत्पादक गट",
        district="Nashik",
        state="Maharashtra",
        primary_crops=["Onion", "Tomato", "Grapes", "Sugarcane"],
        default_language="Marathi",
        active_form_link="https://forms.gle/NashikWeeklyFarmSurvey"
    ),
    DistrictGroup(
        group_id="group_indore_02",
        group_name="इंदौर मालवा सोयाबीन व गेहूं किसान समूह",
        district="Indore",
        state="Madhya Pradesh",
        primary_crops=["Soybean", "Wheat", "Gram", "Potato"],
        default_language="Hindi",
        active_form_link="https://forms.gle/IndoreWeeklyFarmSurvey"
    ),
    DistrictGroup(
        group_id="group_ludhiana_03",
        group_name="Ludhiana Progressive Wheat & Paddy Farmers",
        district="Ludhiana",
        state="Punjab",
        primary_crops=["Wheat", "Paddy", "Mustard", "Maize"],
        default_language="Punjabi/Hindi",
        active_form_link="https://forms.gle/PunjabWeeklyFarmSurvey"
    ),
]

class FormBroadcaster:
    """
    Handles broadcasting the weekly Google Form link to registered district groups.
    """

    def __init__(self, groups: Optional[List[DistrictGroup]] = None, whatsapp_client=None):
        self.groups = groups or DEFAULT_DISTRICT_GROUPS
        self.whatsapp_client = whatsapp_client

    def compose_broadcast_message(self, group: DistrictGroup) -> str:
        """Composes a localized, friendly weekly reminder tailored to the group's district and language."""
        date_str = datetime.now().strftime("%d %B %Y")

        if group.district == "Nashik":
            return (
                f"🌾 *साप्ताहिक शेती सर्वेक्षण ({date_str})*\n"
                f"📍 *{group.group_name}*\n\n"
                f"नमस्कार शेतकरी मित्रांनो! आपल्या शेतातील पिकांची सद्यस्थिती, पाणी आणि खत व्यवस्थापनाचा आढावा घेण्यासाठी कृपया खालील २-मिनिटांचा फॉर्म भरा:\n\n"
                f"👉 *फॉर्म लिंक:* {group.active_form_link}\n\n"
                f"फॉर्म भरल्याने आपल्या गटातील कृषी शास्त्रज्ञांना योग्य सल्ला देणे सोपे होते. धन्यवाद! 🙏\n"
                f"_🤖 कृषी सहाय्यक KrishiBot_"
            )
        else:
            return (
                f"🌾 *साप्ताहिक खेत सर्वेक्षण ({date_str})*\n"
                f"📍 *{group.group_name}*\n\n"
                f"नमस्ते किसान भाईयों! अपने खेत की वर्तमान स्थिति, फसल का प्रकार, कीट समस्या और सिंचाई का विवरण कृपया इस 2-मिनट के फॉर्म में भरें:\n\n"
                f"👉 *फॉर्म लिंक:* {group.active_form_link}\n\n"
                f"आपके द्वारा भरे गए विवरण से हमारे कृषि विशेषज्ञ आपको सही समय पर सटीक सलाह दे सकेंगे। धन्यवाद! 🙏\n"
                f"_🤖 किसान सहायक KrishiBot_"
            )

    def broadcast_to_all_groups(self) -> List[Dict[str, Any]]:
        """Sends the weekly form broadcast message to all registered groups."""
        results = []
        for group in self.groups:
            msg = self.compose_broadcast_message(group)
            status = "SIMULATED_SENT"

            if self.whatsapp_client and hasattr(self.whatsapp_client, "send_message"):
                try:
                    self.whatsapp_client.send_message(to=group.group_id, message_text=msg)
                    status = "DELIVERED"
                except Exception as ex:
                    logger.error(f"Failed to send to group {group.group_id}: {ex}")
                    status = f"FAILED: {ex}"

            logger.info(f"Broadcasted weekly form to [{group.district}]: {group.group_id} ({status})")
            results.append({
                "group_id": group.group_id,
                "district": group.district,
                "status": status,
                "timestamp": datetime.now().isoformat(),
                "message_preview": msg.splitlines()[0]
            })

        return results
