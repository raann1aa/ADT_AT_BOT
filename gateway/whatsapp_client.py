"""
WhatsApp Gateway Client.
Interfaces with the official Meta WhatsApp Cloud API (Graph API v21.0)
with automatic dry-run simulation mode for development & testing.
"""

import os
import logging
from typing import Dict, Any, Optional
import requests

logger = logging.getLogger("WhatsAppClient")

META_GRAPH_API_VERSION = "v21.0"
META_GRAPH_BASE_URL = f"https://graph.facebook.com/{META_GRAPH_API_VERSION}"

class WhatsAppCloudClient:
    """
    Client for dispatching messages via Meta WhatsApp Cloud API.
    Operates in live mode if WHATSAPP_TOKEN & PHONE_NUMBER_ID are provided,
    otherwise runs in safe dry-run simulation mode.
    """

    def __init__(
        self,
        access_token: Optional[str] = None,
        phone_number_id: Optional[str] = None
    ):
        self.access_token = access_token or os.environ.get("WHATSAPP_TOKEN", "")
        self.phone_number_id = phone_number_id or os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
        self.is_live = bool(
            self.access_token
            and self.phone_number_id
            and not self.access_token.startswith("your_")
            and not self.phone_number_id.startswith("your_")
        )

        if self.is_live:
            logger.info("WhatsApp Client initialized in LIVE Meta Cloud API mode.")
        else:
            logger.info("WhatsApp Client initialized in DRY-RUN SIMULATION mode (messages logged to console).")

    def send_message(self, to: str, message_text: str) -> Dict[str, Any]:
        """
        Sends a WhatsApp text message to an individual phone number or group ID.
        """
        if not to or not message_text:
            return {"status": "error", "message": "Recipient or text missing"}

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {
                "preview_url": True,
                "body": message_text
            }
        }

        if self.is_live:
            # Meta Cloud API strictly requires a valid recipient phone number
            clean_digits = "".join(filter(str.isdigit, to))
            if not clean_digits:
                logger.warning(f"Invalid recipient for live Meta Cloud API: '{to}'. Individual API requires numeric phone.")
                return {"status": "error", "code": 400, "detail": f"Invalid recipient for Cloud API: {to}"}

            url = f"{META_GRAPH_BASE_URL}/{self.phone_number_id}/messages"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=10)
                if response.status_code in (200, 201):
                    masked_to = f"******{clean_digits[-4:]}" if len(clean_digits) >= 4 else clean_digits
                    logger.info(f"Delivered WhatsApp message to {masked_to}")
                    return {"status": "delivered", "data": response.json()}
                else:
                    logger.error(f"WhatsApp Cloud API error {response.status_code}: {response.text}")
                    return {"status": "error", "code": response.status_code, "detail": response.text}
            except Exception as e:
                logger.error(f"Exception sending WhatsApp message: {e}")
                return {"status": "exception", "detail": str(e)}
        else:
            # Simulation / Dry-run output
            logger.info(f"🟢 [OUTGOING WHATSAPP -> {to}]:\n{message_text}")
            return {
                "status": "simulated_sent",
                "recipient": to,
                "text_preview": message_text[:80]
            }
