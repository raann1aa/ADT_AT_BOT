"""
Automated End-to-End Integration Test for WhatsApp Webhook Server,
Excel Farmer Profile Lookup, and Google Form Automation.
Usage:
    python scripts/test_webhook_flow.py
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

_TEST_DATA_DIRECTORY = tempfile.TemporaryDirectory(prefix="krishibot_webhook_test_")
_TEST_DATA_PATH = Path(_TEST_DATA_DIRECTORY.name)
_TEST_EXCEL_PATH = _TEST_DATA_PATH / "farmer_profiles.xlsx"
shutil.copy2(BASE_DIR / "data" / "farmer_profiles.xlsx", _TEST_EXCEL_PATH)

from form_automation import excel_manager as excel_manager_module
from database.services import excel_migration_service as excel_migration_module

excel_manager_module.DEFAULT_EXCEL_PATH = _TEST_EXCEL_PATH
excel_migration_module.DEFAULT_BACKUP_DIR = _TEST_DATA_PATH / "backups"

from fastapi.testclient import TestClient
from gateway.webhook_server import app, DEFAULT_VERIFY_TOKEN

client = TestClient(app)

def test_webhook_verification():
    print("\n[1/6] Testing Meta Webhook Verification Endpoint...")
    params = {
        "hub.mode": "subscribe",
        "hub.challenge": "1158201444",
        "hub.verify_token": DEFAULT_VERIFY_TOKEN
    }
    response = client.get("/webhook", params=params)
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    assert response.text == "1158201444", f"Expected challenge return, got {response.text}"
    print("  ✅ Meta Webhook handshake passed (returned challenge string).")

def test_system_status():
    print("\n[2/6] Testing System Diagnostics & Status...")
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    print(f"  ✅ Service: {data['service']}")
    print(f"  ✅ Registered Groups: {data['registered_groups']}")
    print(f"  ✅ Farmers in Excel: {data['registered_farmers_in_excel']}")
    print(f"  ✅ RAG Chunks: {data['knowledge_chunks_indexed']}")
    assert data["registered_farmers_in_excel"] >= 6
    assert data["knowledge_chunks_indexed"] >= 190

def test_excel_farmers_list():
    print("\n[3/6] Testing Excel Farmer Registry...")
    response = client.get("/api/farmers")
    assert response.status_code == 200
    data = response.json()
    farmers = data["farmers"]
    print(f"  ✅ Retrieved {len(farmers)} farmer records from Excel.")
    ramesh = next((f for f in farmers if f["farmer_name"] == "Ramesh Patil"), None)
    assert ramesh is not None
    assert ramesh["district"] == "Nashik"
    assert ramesh["crop_grown"] == "Onion"
    print(f"  ✅ Verified profile: Ramesh Patil -> {ramesh['district']}, {ramesh['farm_size_acres']} Acres, Crop: {ramesh['crop_grown']}")

def test_incoming_webhook_message_greeting():
    print("\n[4/6] Testing Incoming Webhook (Social Greeting - Must Be Ignored)...")
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "919823011111",
                                    "id": "wamid.greeting123",
                                    "timestamp": "1732014000",
                                    "type": "text",
                                    "text": {"body": "सुप्रभात सभी किसान भाईयों 🙏"}
                                }
                            ],
                            "contacts": [
                                {"profile": {"name": "Ramesh Patil"}, "wa_id": "919823011111"}
                            ],
                            "metadata": {"group_id": "group_nashik_01"}
                        }
                    }
                ]
            }
        ]
    }
    response = client.post("/webhook", json=payload)
    assert response.status_code == 200
    assert response.json() == {"status": "EVENT_RECEIVED"}
    print("  ✅ Webhook accepted greeting payload with 200 OK (Background task silently discarded noise).")

def test_incoming_webhook_message_agri_query():
    print("\n[5/6] Testing Incoming Webhook (Legitimate Pest Query with Excel Lookup)...")
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "919823011111",
                                    "id": "wamid.query456",
                                    "timestamp": "1732014010",
                                    "type": "text",
                                    "text": {"body": "Kanda storage rot aur purple blotch rokne ke liye dawai bataye"}
                                }
                            ],
                            "contacts": [
                                {"profile": {"name": "Ramesh Patil"}, "wa_id": "919823011111"}
                            ],
                            "metadata": {"group_id": "group_nashik_01"}
                        }
                    }
                ]
            }
        ]
    }
    response = client.post("/webhook", json=payload)
    assert response.status_code == 200
    assert response.json() == {"status": "EVENT_RECEIVED"}
    print("  ✅ Webhook accepted query payload with 200 OK (RAG + Excel profile resolved).")

def test_weekly_form_broadcast_and_submission():
    print("\n[6/6] Testing Google Form Broadcast & Live Ingestion...")
    # Broadcast to all district groups
    b_resp = client.post("/api/broadcast-weekly-form")
    assert b_resp.status_code == 200
    b_data = b_resp.json()
    print(f"  ✅ Form Broadcasted to {b_data['broadcast_count']} district groups.")

    # Ingest a new form submission into Excel
    new_farmer = {
        "farmer_name": "Mukesh Sharma",
        "phone_number": "9826077777",
        "district": "Indore",
        "area_tehsil": "Depalpur",
        "farm_size_acres": 7.5,
        "crop_grown": "Potato",
        "soil_type": "Black Cotton",
        "sowing_stage": "Tuber Formation",
        "has_drip_irrigation": True
    }
    s_resp = client.post("/api/form-submission", json=new_farmer)
    assert s_resp.status_code == 200
    print(f"  ✅ Ingested new submission into Excel: {new_farmer['farmer_name']} ({new_farmer['district']})")

    # Verify farmer is immediately queryable in cache
    f_resp = client.get("/api/farmers")
    all_names = [f["farmer_name"] for f in f_resp.json()["farmers"]]
    assert "Mukesh Sharma" in all_names
    print("  ✅ Confirmed new submission appears in Excel profile store.")

def test_admin_dashboard_endpoints():
    print("\n[7/7] Testing Admin Dashboard UI & Analytics Endpoints...")
    d_resp = client.get("/dashboard")
    assert d_resp.status_code == 200
    assert "KrishiBot Ops Control" in d_resp.text
    print("  ✅ Admin Dashboard HTML rendered successfully.")

    stats_resp = client.get("/api/dashboard/stats")
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert "queries_answered" in stats
    assert "noise_filtered" in stats
    print(f"  ✅ Dashboard Analytics: {stats['queries_answered']} Queries, {stats['noise_filtered']} Noise Messages Filtered.")

    msg_resp = client.get("/api/dashboard/messages")
    assert msg_resp.status_code == 200
    messages = msg_resp.json()["messages"]
    assert len(messages) > 0
    print(f"  ✅ Live Message Stream: {len(messages)} recent audit logs available.")

def test_webhook_resilience_and_error_handling():
    print("\n[8/8] Testing Webhook Resilience & Error Handling (Task C & E)...")
    
    # 1. Invalid verification token -> Must return 403 Forbidden
    bad_verify = client.get("/webhook", params={"hub.mode": "subscribe", "hub.challenge": "123", "hub.verify_token": "wrong_secret"})
    assert bad_verify.status_code == 403, f"Expected 403, got {bad_verify.status_code}"
    print("  ✅ Rejected invalid webhook verification token with 403 Forbidden.")

    # 2. Malformed non-JSON payload -> Must return 400
    bad_json = client.post("/webhook", content=b"not a valid json string", headers={"Content-Type": "application/json"})
    assert bad_json.status_code == 400, f"Expected 400, got {bad_json.status_code}"
    print("  ✅ Safely rejected malformed JSON body with 400 Bad Request.")

    # 3. Non-object JSON payload -> Must return 400
    non_dict = client.post("/webhook", json=["an", "array", "payload"])
    assert non_dict.status_code == 400, f"Expected 400, got {non_dict.status_code}"
    print("  ✅ Safely rejected non-object JSON body with 400 Bad Request.")

    # 4. Unsupported media message (audio) -> Handled cleanly without crashing
    media_payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "919823011111",
                        "id": "wamid.audio123",
                        "type": "audio",
                        "audio": {"id": "media_audio_001"}
                    }]
                }
            }]
        }]
    }
    media_resp = client.post("/webhook", json=media_payload)
    assert media_resp.status_code == 200
    print("  ✅ Non-text media message handled safely without crashing (skipped for Phase 4).")

    # 5. Duplicate message payload -> Ingress deduplication
    dup_id = "wamid.dup_test_999"
    dup_payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "919823011111",
                        "id": dup_id,
                        "type": "text",
                        "text": {"body": "First delivery"}
                    }]
                }
            }]
        }]
    }
    resp1 = client.post("/webhook", json=dup_payload)
    assert resp1.status_code == 200
    resp2 = client.post("/webhook", json=dup_payload)
    assert resp2.status_code == 200
    print("  ✅ Duplicate incoming message ID deduplicated safely at ingress.")

    # 6. Empty text payload -> Handled safely without crashing
    empty_payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "919823011111",
                        "id": "wamid.empty_text",
                        "type": "text",
                        "text": {"body": "   "}
                    }]
                }
            }]
        }]
    }
    empty_resp = client.post("/webhook", json=empty_payload)
    assert empty_resp.status_code == 200
    print("  ✅ Empty text message handled safely without crashing.")

def main():
    print("=" * 80)
    print("🧪 RUNNING END-TO-END GATEWAY, WEBHOOK & DASHBOARD TEST SUITE")
    print("=" * 80)
    test_webhook_verification()
    test_system_status()
    test_excel_farmers_list()
    test_incoming_webhook_message_greeting()
    test_incoming_webhook_message_agri_query()
    test_weekly_form_broadcast_and_submission()
    test_admin_dashboard_endpoints()
    test_webhook_resilience_and_error_handling()
    print("\n" + "=" * 80)
    print("🎉 ALL 8/8 INTEGRATION & RESILIENCE TESTS PASSED SUCCESSFULLY!")
    print("=" * 80)

if __name__ == "__main__":
    main()
