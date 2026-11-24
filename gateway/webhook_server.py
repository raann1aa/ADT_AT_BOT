"""
FastAPI WhatsApp Webhook & Multi-Group Management Server.
Handles incoming Meta WhatsApp Cloud API webhooks, Excel farmer profile integration,
weekly Google Form broadcasts, and modern visual Operations Dashboard.
"""

import os
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from collections import deque

from fastapi import FastAPI, Request, Query, BackgroundTasks, HTTPException, status
from fastapi.responses import PlainTextResponse, JSONResponse, HTMLResponse
from pydantic import BaseModel

from agent.farmer_agent import FarmerAgent, FarmerProfile
from form_automation.excel_manager import ExcelProfileManager
from form_automation.models import FarmerFormSubmission, DistrictGroup
from form_automation.form_broadcast import FormBroadcaster
from .whatsapp_client import WhatsAppCloudClient
from .group_manager import WhatsAppGroupManager
from .message_logger import AuditLogger

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("WhatsAppWebhookServer")

# Secret verification token for Meta WhatsApp Webhook setup
DEFAULT_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "krishibot_secret_verify_token_2026")

# FastAPI App Instance
app = FastAPI(
    title="KrishiBot WhatsApp Gateway & RAG Service",
    description="Intelligent AI Agent for Multi-District Farmer WhatsApp Groups with Excel Sync",
    version="2.0.0"
)

from database.services.deduplication_service import DeduplicationService
from database.services.outbox_service import OutboxService
from database.services.farmer_service import FarmerService

# Shared Core Singletons
excel_manager = ExcelProfileManager()
group_manager = WhatsAppGroupManager()
whatsapp_client = WhatsAppCloudClient()
farmer_agent = FarmerAgent(default_form_link="https://forms.gle/WeeklyFarmerSurvey")
form_broadcaster = FormBroadcaster(whatsapp_client=whatsapp_client)
audit_logger = AuditLogger(max_history=500)
outbox_service = OutboxService(whatsapp_client=whatsapp_client)
farmer_service = FarmerService()

# Persistent database-backed message deduplication service
dedup_service = DeduplicationService()
processed_message_ids = dedup_service._memory_cache

class IncomingWebhookMessage(BaseModel):
    sender_phone: str
    sender_name: str
    message_text: str
    message_id: str
    group_id: Optional[str] = None
    timestamp: Optional[str] = None

def process_message_background(msg: IncomingWebhookMessage):
    """
    Background worker that runs RAG retrieval, LLM synthesis, and WhatsApp delivery
    without delaying the immediate HTTP 200 response to Meta's webhook.
    """
    if not dedup_service.claim_message(msg.message_id, msg.sender_phone):
        logger.info(f"Duplicate message {msg.message_id} skipped in background.")
        return

    phone_masked = f"******{msg.sender_phone[-4:]}" if len(msg.sender_phone) >= 4 else msg.sender_phone
    group_id = msg.group_id or "group_general"
    group_info = group_manager.get_group(group_id)
    district_name = group_info.district if group_info else "General"
    group_name = group_info.group_name if group_info else "General Farmer Group"

    try:
        # 1. Look up Farmer Profile in Database & Excel
        db_farmer = None
        try:
            db_farmer = farmer_service.get_farmer_by_phone(msg.sender_phone)
        except Exception:
            pass

        registered_farmer = excel_manager.lookup_farmer(msg.sender_phone)

        if db_farmer:
            plot = db_farmer.plots[0] if (db_farmer.plots and len(db_farmer.plots) > 0) else None
            crop = plot.crops[0] if (plot and plot.crops and len(plot.crops) > 0) else None
            soil = plot.soil_profiles[0] if (plot and plot.soil_profiles and len(plot.soil_profiles) > 0) else None
            profile = FarmerProfile(
                name=db_farmer.full_name,
                phone=db_farmer.primary_phone,
                district=db_farmer.district.name if db_farmer.district else "General",
                crop=crop.crop_name if crop else "General",
                soil_type=soil.soil_type if soil else "Loam",
                farm_size=f"{plot.land_area} Acres" if plot else "3 Acres",
                farmer_id=db_farmer.id,
                preferred_language=db_farmer.preferred_language or "mr"
            )
            logger.info(f"✅ Recognized Farmer from DB: {db_farmer.full_name} (#{db_farmer.farmer_id})")
        elif registered_farmer:
            logger.info(f"✅ Recognized Farmer from Excel: {registered_farmer.farmer_name} ({registered_farmer.district}, Crop: {registered_farmer.crop_grown})")
            profile = FarmerProfile(
                name=registered_farmer.farmer_name,
                phone=registered_farmer.phone_number,
                district=registered_farmer.district,
                crop=registered_farmer.crop_grown,
                soil_type=registered_farmer.soil_type,
                farm_size=f"{registered_farmer.farm_size_acres} Acres"
            )
        else:
            # Fallback to group default crop if farmer hasn't filled the form yet
            default_crop = group_info.primary_crops[0] if (group_info and group_info.primary_crops) else "General"
            profile = FarmerProfile(
                name=msg.sender_name or "किसान भाई",
                phone=msg.sender_phone,
                district=district_name,
                crop=default_crop
            )

        # 2. Process via FarmerAgent (Classifier -> RAG -> LLM -> WhatsApp Formatter)
        response = farmer_agent.process_message(
            message=msg.message_text,
            sender_phone=msg.sender_phone,
            sender_name=msg.sender_name,
            group_id=group_id,
            profile=profile
        )

        # 3. Dispatch Reply via Transactional Outbox (Durable Queuing + Dispatch)
        if response.reply_text:
            if whatsapp_client.is_live:
                recipient = msg.sender_phone
            else:
                recipient = group_id if (group_id and group_id.startswith("group_")) else msg.sender_phone

            # Persist in transactional outbox first
            outbox_id = outbox_service.enqueue(
                recipient_phone=recipient,
                message_text=response.reply_text,
                idempotency_key=f"out_{msg.message_id}"
            )
            # Dispatch to external Meta WhatsApp client
            outbox_service.process_pending(client=whatsapp_client)
            masked_recipient = f"******{recipient[-4:]}" if (recipient and recipient.isdigit() and len(recipient) >= 4) else recipient
            logger.info(f"Dispatched outbox {outbox_id} to {masked_recipient} (Status: {response.status})")
        else:
            logger.info(f"🔕 Message from {msg.sender_name} was silently ignored: {response.reason}")

        # 4. Log to Audit History for Admin Dashboard
        audit_logger.log(
            sender_name=profile.name,
            sender_phone=msg.sender_phone,
            district=profile.district,
            group_id=group_id,
            group_name=group_name,
            incoming_text=msg.message_text,
            category=response.category.value,
            action=response.status,
            bot_reply=response.reply_text,
            rag_sources=response.rag_sources,
            processing_time_ms=response.processing_time_ms,
            is_escalated=response.requires_admin_alert
        )
        dedup_service.complete_message(msg.message_id)
    except Exception as ex:
        logger.error(f"Error processing background message {msg.message_id} from {phone_masked}: {ex}", exc_info=True)
        dedup_service.fail_message(msg.message_id, str(ex))
        audit_logger.log(
            sender_name=msg.sender_name or "Unknown",
            sender_phone=msg.sender_phone,
            district=district_name,
            group_id=group_id,
            group_name=group_name,
            incoming_text=msg.message_text,
            category="PROCESSING_ERROR",
            action="FAILED",
            bot_reply="An internal error occurred while processing this message.",
            is_escalated=True
        )

@app.get("/", tags=["Health"])
def root_status():
    """System status and diagnostics."""
    return {
        "service": "KrishiBot WhatsApp Gateway & RAG Service",
        "status": "online",
        "registered_groups": len(group_manager.get_all_groups()),
        "registered_farmers_in_excel": len(excel_manager.get_all_farmers()),
        "knowledge_chunks_indexed": farmer_agent.rag_pipeline.stats()["chunks_count"],
        "whatsapp_client_mode": "LIVE" if whatsapp_client.is_live else "DRY-RUN SIMULATION",
        "dashboard_url": "/dashboard"
    }

@app.get("/dashboard", response_class=HTMLResponse, tags=["Admin Dashboard"])
@app.get("/admin", response_class=HTMLResponse, tags=["Admin Dashboard"])
def serve_dashboard():
    """Renders the interactive visual Admin & Operations Dashboard."""
    template_path = Path(__file__).resolve().parent / "templates" / "dashboard.html"
    if not template_path.exists():
        return HTMLResponse("<h1>Dashboard template not found</h1>", status_code=404)
    with open(template_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content, status_code=200)

@app.get("/api/dashboard/stats", tags=["Admin Dashboard"])
def get_dashboard_stats():
    """Returns analytics metrics for the dashboard charts and KPI cards."""
    return audit_logger.get_stats()

@app.get("/api/dashboard/messages", tags=["Admin Dashboard"])
def get_dashboard_messages(limit: int = 50, category: Optional[str] = None):
    """Returns recent message audit logs."""
    return {"messages": audit_logger.get_recent(limit=limit, category=category)}

@app.get("/api/dashboard/groups", tags=["Admin Dashboard"])
def get_dashboard_groups():
    """Returns district groups for the dashboard."""
    return {"groups": [g.model_dump() for g in group_manager.get_all_groups()]}

@app.post("/api/dashboard/escalations/resolve-all", tags=["Admin Dashboard"])
def resolve_all_escalations():
    """Marks all pending escalations as handled."""
    for item in audit_logger.logs:
        item.resolved = True
    return {"status": "success", "message": "All escalations resolved"}

@app.get("/webhook", tags=["WhatsApp Webhook"])
def verify_meta_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token")
):
    """
    Meta WhatsApp Cloud API Verification Endpoint.
    Validates token when setting up Webhook URL in Meta App Dashboard.
    """
    logger.info(f"Webhook verification attempt. Mode: {hub_mode}")
    if hub_mode == "subscribe" and hub_verify_token and hub_verify_token == DEFAULT_VERIFY_TOKEN:
        logger.info("✅ Webhook verified successfully with Meta!")
        return PlainTextResponse(content=hub_challenge or "", status_code=200)

    logger.warning("❌ Webhook verification failed: invalid verify_token or mode")
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verification token mismatch")

@app.post("/webhook", tags=["WhatsApp Webhook"])
async def receive_whatsapp_event(request: Request, background_tasks: BackgroundTasks):
    """
    Meta WhatsApp Cloud API Ingestion Endpoint.
    Receives incoming group/individual messages and processes them asynchronously.
    """
    try:
        body = await request.json()
    except Exception as json_err:
        logger.warning(f"Malformed JSON payload in webhook request: {json_err}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    if not isinstance(body, dict):
        logger.warning("Invalid webhook body structure: expected a JSON object.")
        raise HTTPException(status_code=400, detail="Invalid JSON payload: expected an object")

    # Parse standard Meta Cloud API payload structure defensively
    entries = body.get("entry", [])
    if not isinstance(entries, list):
        entries = []

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changes = entry.get("changes", [])
        if not isinstance(changes, list):
            continue
        for change in changes:
            if not isinstance(change, dict):
                continue
            value = change.get("value", {})
            if not isinstance(value, dict):
                continue
            messages = value.get("messages", [])
            contacts = value.get("contacts", [])
            if not isinstance(messages, list):
                messages = []
            if not isinstance(contacts, list):
                contacts = []

            contact_map = {
                c.get("wa_id"): c.get("profile", {}).get("name")
                for c in contacts
                if isinstance(c, dict)
            }

            for m in messages:
                if not isinstance(m, dict):
                    continue
                msg_type = m.get("type", "text")
                sender_phone = str(m.get("from", "")).strip()
                msg_id = m.get("id", f"msg_{time.time()}")

                # Check unsupported message types without crashing
                if msg_type != "text":
                    phone_masked = f"******{sender_phone[-4:]}" if len(sender_phone) >= 4 else "unknown"
                    logger.info(f"Received non-text message type '{msg_type}' from {phone_masked}. Skipping (media support scheduled for Phase 4).")
                    continue

                msg_text = m.get("text", {}).get("body", "") if isinstance(m.get("text"), dict) else ""
                
                # Validate required message text
                if not msg_text or not msg_text.strip():
                    logger.warning(f"Empty text in message {msg_id}; skipping.")
                    continue

                # Persistent + RAM deduplicate immediately to avoid queueing duplicate background workers
                if dedup_service.is_duplicate(msg_id):
                    logger.info(f"Duplicate incoming message {msg_id} dropped at ingress.")
                    continue

                sender_name = contact_map.get(sender_phone, "किसान भाई")
                group_id = m.get("group_id") or value.get("metadata", {}).get("group_id", "group_nashik_01")

                incoming = IncomingWebhookMessage(
                    sender_phone=sender_phone,
                    sender_name=sender_name,
                    message_text=msg_text.strip(),
                    message_id=msg_id,
                    group_id=group_id
                )

                # Queue background processing so Webhook responds in <10ms to Meta
                background_tasks.add_task(process_message_background, incoming)

    return JSONResponse(content={"status": "EVENT_RECEIVED"}, status_code=200)

@app.get("/api/farmers", tags=["Farmer Profiles"])
def list_registered_farmers():
    """Returns the list of farmers registered via the Google Form and cached from Excel."""
    return {
        "total_farmers": len(excel_manager.get_all_farmers()),
        "farmers": [f.model_dump() for f in excel_manager.get_all_farmers()]
    }

@app.post("/api/form-submission", tags=["Google Form Automation"])
def handle_google_form_submission(submission: FarmerFormSubmission):
    """
    Webhook endpoint to receive Google Form submissions (via Apps Script or Zapier)
    and sync them directly into the Excel workbook and cache.
    """
    excel_manager.record_submission(submission)
    logger.info(f"Recorded Google Form submission for: {submission.farmer_name} ({submission.district})")
    return {"status": "success", "message": f"Profile for {submission.farmer_name} synced to Excel."}

@app.post("/api/broadcast-weekly-form", tags=["Google Form Automation"])
def trigger_weekly_form_broadcast():
    """Manually triggers the weekly Google Form broadcast across all registered district groups."""
    results = form_broadcaster.broadcast_to_all_groups()
    return {
        "status": "success",
        "broadcast_count": len(results),
        "details": results
    }
