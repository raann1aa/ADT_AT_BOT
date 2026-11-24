"""
Phase 3 Test Suite: Central AI Agent & Conversation Automation
===============================================================
Comprehensive test suite verifying:
  1. Conversational Memory (Persistence, Context Retrieval, Restart Recovery, Isolation)
  2. Multi-Turn Conversation Management (Sequential turns, follow-up answers, topic switches)
  3. Missing Farm Information Detection (Distinguishing 5 verification states, protecting VERIFIED)
  4. Intelligent Follow-Up Automation (Priority ordering, duplicate avoidance, localized questions)
  5. Agricultural Intent Classification (13 Categories, Entity Extraction, Confidence & Clarity)
  6. Transactional Outbox (Durable queuing, dispatch, retry backoff, duplicate protection)
  7. Field History Audit (Old vs New values, actor attribution, chronological audit trails)

Usage:
    cd ADT-AI-BOT
    python scripts/test_phase_3_conversation.py
"""

import os
import sys
import uuid
import json
from pathlib import Path
from datetime import datetime, date

# Enforce isolated in-memory SQLite for test execution
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from database.connection import init_db, get_db_session
from database.models import Farmer, FarmPlot, CropRecord, SoilProfile, OutboxMessage, FieldHistory, ConversationSession
from database.enums import (
    VerificationStatus, PlantingSeason, AreaUnit,
    OutboxMessageStatus, ConversationState, AgriculturalIntent
)
from database.repositories import (
    FarmerRepository, CDORepository, OutboxRepository,
    FieldHistoryRepository, ConversationRepository
)
from database.services import OutboxService
from agent.classifier import WhatsAppMessageClassifier, MessageCategory, INTENT_TO_LEGACY_CATEGORY
from agent.conversation_manager import ConversationManager
from agent.followup_engine import FollowupEngine, FIELD_PRIORITY_ORDER
from agent.farmer_agent import FarmerAgent, FarmerProfile

# Initialize database schema
init_db()

PASS = 0
FAIL = 0
RESULTS = []


def test(label: str, fn):
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        RESULTS.append(("PASS", label, ""))
        print(f"  ✅ PASS: {label}")
    except Exception as ex:
        FAIL += 1
        RESULTS.append(("FAIL", label, str(ex)))
        print(f"  ❌ FAIL: {label}\n       {ex}")


# =============================================================================
# SECTION 1: Conversational Memory
# =============================================================================
print("\n" + "=" * 70)
print("SECTION 1: Conversational Memory & State Tracking")
print("=" * 70)

def test_1_1_session_persistence_and_resumption():
    cm = ConversationManager()
    phone = "9823000001"
    sess = cm.get_or_resume_session(phone)
    assert sess["session_id"].startswith("SESS-")
    assert sess["phone_number"] == phone
    assert sess["current_state"] == ConversationState.IDLE.value

    # Resuming same phone should return existing session
    sess2 = cm.get_or_resume_session(phone)
    assert sess2["session_id"] == sess["session_id"], "Session resumption must reuse existing session"

test("1.1 Session persistence and resumption across requests", test_1_1_session_persistence_and_resumption)


def test_1_2_context_retrieval_and_turn_recording():
    cm = ConversationManager()
    phone = "9823000002"
    sess = cm.get_or_resume_session(phone)
    session_pk = sess["id"]

    cm.record_turn(
        session_pk=session_pk,
        user_message="माझा ऊस 4 एकर आहे",
        assistant_reply="माहिती नोंदवली आहे. धन्यवाद!",
        intent=AgriculturalIntent.FARMER_PROFILE_UPDATE.value,
        entities={"crop": "Sugarcane", "land_area": 4.0}
    )

    history = cm.get_conversation_history(session_pk=session_pk)
    assert len(history) == 2, f"Expected 2 turns (user + assistant), got {len(history)}"
    assert history[0]["role"] == "farmer"
    assert "ऊस 4 एकर" in history[0]["text"]
    assert history[1]["role"] == "assistant"

    prompt_ctx = cm.format_history_for_prompt(session_pk=session_pk)
    assert "Farmer:" in prompt_ctx
    assert "KrishiBot:" in prompt_ctx

test("1.2 Multi-turn dialog recording and formatted prompt retrieval", test_1_2_context_retrieval_and_turn_recording)


def test_1_3_farmer_isolation_no_cross_contamination():
    cm = ConversationManager()
    phone_a = "9823000003"
    phone_b = "9823000004"

    sess_a = cm.get_or_resume_session(phone_a)
    sess_b = cm.get_or_resume_session(phone_b)

    cm.record_turn(
        session_pk=sess_a["id"],
        user_message="कांद्यावर करपा आला आहे",
        assistant_reply="मँकोझेब फवारा.",
        intent=AgriculturalIntent.CROP_DISEASE_PEST.value
    )

    history_a = cm.get_conversation_history(session_pk=sess_a["id"])
    history_b = cm.get_conversation_history(session_pk=sess_b["id"])

    assert len(history_a) == 2
    assert len(history_b) == 0, "Farmer B session must remain completely empty (zero cross-farmer leak)"

test("1.3 Farmer isolation: zero cross-farmer context contamination", test_1_3_farmer_isolation_no_cross_contamination)


# =============================================================================
# SECTION 2: Multi-Turn Conversation Management
# =============================================================================
print("\n" + "=" * 70)
print("SECTION 2: Multi-Turn Conversation Management")
print("=" * 70)

def test_2_1_state_machine_transition():
    cm = ConversationManager()
    phone = "9823000005"
    sess = cm.get_or_resume_session(phone)
    session_pk = sess["id"]

    cm.record_turn(
        session_pk=session_pk,
        user_message="उसाला पाणी कधी द्यावे?",
        assistant_reply="ठिबक सिंचनाने पाणी द्या.",
        intent=AgriculturalIntent.IRRIGATION_WATER.value,
        new_state=ConversationState.AWAITING_FIELD_INPUT.value,
        updated_context={"awaiting_field": "planting_season"}
    )

    resumed = cm.get_or_resume_session(phone)
    assert resumed["current_state"] == ConversationState.AWAITING_FIELD_INPUT.value
    assert resumed["context_data"].get("awaiting_field") == "planting_season"

test("2.1 Dialog state machine transition to AWAITING_FIELD_INPUT", test_2_1_state_machine_transition)


def test_2_2_unrelated_message_does_not_corrupt_state():
    """If farmer asks an unrelated question while state was awaiting input, agent answers question safely."""
    with get_db_session() as s:
        repo = FarmerRepository(s)
        d = CDORepository(s).get_or_create_district("Ahmednagar")
        farmer = repo.create_farmer(
            farmer_id="FARM-MT-01",
            full_name="Sanjay Kale",
            primary_phone="9823000006",
            district_id=d.id
        )
        s.commit()
        fid = farmer.id

    agent = FarmerAgent()
    profile = FarmerProfile(name="Sanjay Kale", phone="9823000006", district="Ahmednagar", farmer_id=fid)

    # First turn: Ask general query
    resp1 = agent.process_message("उसाला खत कोणते द्यावे?", sender_phone="9823000006", profile=profile)
    assert resp1.status == "ANSWERED"

    # Second turn: Farmer switches to weather topic instead of answering follow-up
    resp2 = agent.process_message("आज पाऊस पडेल का?", sender_phone="9823000006", profile=profile)
    assert resp2.status == "ANSWERED"
    assert resp2.intent == AgriculturalIntent.WEATHER_CLIMATE

test("2.2 Unrelated message handled gracefully without state corruption", test_2_2_unrelated_message_does_not_corrupt_state)


# =============================================================================
# SECTION 3: Missing Farm Information Detection & Verification Status
# =============================================================================
print("\n" + "=" * 70)
print("SECTION 3: Missing Farm Information Detection")
print("=" * 70)

def test_3_1_inspect_missing_fields_categorization():
    fe = FollowupEngine()
    with get_db_session() as s:
        repo = FarmerRepository(s)
        d = CDORepository(s).get_or_create_district("Satara")
        farmer = repo.create_farmer(
            farmer_id="FARM-MF-01",
            full_name="Anand Ghadge",
            primary_phone="9823000007",
            district_id=d.id
        )
        plot = repo.add_plot(
            farmer_id=farmer.id,
            plot_identifier="PLOT-1",
            land_area=5.0,
            area_status=VerificationStatus.VERIFIED
        )
        repo.add_crop_to_plot(
            farm_plot_id=plot.id,
            crop_name="Sugarcane",
            crop_status=VerificationStatus.UNVERIFIED
        )
        s.commit()

        # Re-fetch with loaded relations
        db_f = repo.get_by_id(farmer.id)
        mmap = fe.inspect_missing_fields(db_f)

        assert mmap["cultivated_area"] == VerificationStatus.VERIFIED
        assert mmap["crop"] == VerificationStatus.UNVERIFIED
        assert mmap["soil_type"] == VerificationStatus.MISSING
        assert mmap["npk_information"] == VerificationStatus.MISSING

test("3.1 Correct categorization of VERIFIED, UNVERIFIED, and MISSING fields", test_3_1_inspect_missing_fields_categorization)


def test_3_2_verified_field_immune_to_ai_overwrite():
    fe = FollowupEngine()
    with get_db_session() as s:
        repo = FarmerRepository(s)
        d = CDORepository(s).get_or_create_district("Sangli")
        farmer = repo.create_farmer(
            farmer_id="FARM-MF-02",
            full_name="Rajesh Thorat",
            primary_phone="9823000008",
            district_id=d.id
        )
        plot = repo.add_plot(
            farmer_id=farmer.id,
            plot_identifier="PLOT-1",
            land_area=8.0,
            area_status=VerificationStatus.VERIFIED
        )
        s.commit()
        fid = farmer.id

    # Attempt to overwrite VERIFIED area through chat extraction
    applied, msg = fe.parse_and_apply_answer(
        farmer_id=fid,
        field_name="cultivated_area",
        message_text="माझे शेत 2 एकर आहे",
        extracted_entities={"land_area": 2.0}
    )
    assert not applied, "VERIFIED field must be protected from AI overwrite"
    assert "VERIFIED" in msg

    with get_db_session() as s:
        p = s.query(FarmPlot).filter(FarmPlot.farmer_id == fid).first()
        assert p.land_area == 8.0, "Verified value must remain strictly unchanged"

test("3.2 VERIFIED values are strictly immune to AI-extracted overwrites", test_3_2_verified_field_immune_to_ai_overwrite)


def test_3_3_unverified_update_applied_safely():
    fe = FollowupEngine()
    with get_db_session() as s:
        repo = FarmerRepository(s)
        d = CDORepository(s).get_or_create_district("Solapur")
        farmer = repo.create_farmer(
            farmer_id="FARM-MF-03",
            full_name="Bapu Shinde",
            primary_phone="9823000009",
            district_id=d.id
        )
        plot = repo.add_plot(
            farmer_id=farmer.id,
            plot_identifier="PLOT-1",
            land_area=3.0,
            area_status=VerificationStatus.UNVERIFIED
        )
        s.commit()
        fid = farmer.id

    applied, msg = fe.parse_and_apply_answer(
        farmer_id=fid,
        field_name="cultivated_area",
        message_text="माझे 6.5 एकर क्षेत्र आहे",
        extracted_entities={"land_area": 6.5}
    )
    assert applied, f"Unverified field must be updatable: {msg}"

    with get_db_session() as s:
        p = s.query(FarmPlot).filter(FarmPlot.farmer_id == fid).first()
        assert p.land_area == 6.5
        assert p.area_status == VerificationStatus.UNVERIFIED
        assert p.data_source == "WHATSAPP_CHAT"

test("3.3 UNVERIFIED field updated with WHATSAPP_CHAT provenance", test_3_3_unverified_update_applied_safely)


# =============================================================================
# SECTION 4: Intelligent Follow-Up Automation
# =============================================================================
print("\n" + "=" * 70)
print("SECTION 4: Intelligent Follow-Up Automation")
print("=" * 70)

def test_4_1_priority_order_and_duplicate_prevention():
    fe = FollowupEngine()
    status_map = {
        "crop": VerificationStatus.VERIFIED,
        "planting_date": VerificationStatus.MISSING,
        "cultivated_area": VerificationStatus.MISSING,
        "soil_type": VerificationStatus.MISSING
    }

    # First turn: Next field should be planting_date
    next1 = fe.select_next_field_to_elicit(status_map, asked_fields=[])
    assert next1 == "planting_date"

    # Second turn: planting_date was already asked -> should pick cultivated_area
    next2 = fe.select_next_field_to_elicit(status_map, asked_fields=["planting_date"])
    assert next2 == "planting_season" or next2 == "cultivated_area"

test("4.1 Prioritized field selection and duplicate question prevention", test_4_1_priority_order_and_duplicate_prevention)


def test_4_2_localized_followup_question_generation():
    fe = FollowupEngine()
    q_mr = fe.generate_question("cultivated_area", preferred_language="mr")
    q_hi = fe.generate_question("cultivated_area", preferred_language="hi")
    q_en = fe.generate_question("cultivated_area", preferred_language="en")

    assert "एकर" in q_mr
    assert "एकड़" in q_hi
    assert "acres" in q_en

test("4.2 Multilingual follow-up question generation (Marathi, Hindi, English)", test_4_2_localized_followup_question_generation)


# =============================================================================
# SECTION 5: Agricultural Intent Classification (13 Categories)
# =============================================================================
print("\n" + "=" * 70)
print("SECTION 5: 13-Intent Granular Agricultural Classification")
print("=" * 70)

def test_5_1_all_13_intents():
    classifier = WhatsAppMessageClassifier()

    cases = [
        ("उसावर तांबेरा रोग आला आहे, काय फवारावे?", AgriculturalIntent.CROP_DISEASE_PEST),
        ("खताचा दुसरा डोस किती द्यावा? NPK 10:26:26 योग्य आहे का?", AgriculturalIntent.FERTILIZER_NUTRITION),
        ("ठिबक सिंचनाने उसाला पाणी किती तास द्यावे?", AgriculturalIntent.IRRIGATION_WATER),
        ("को ८६०३२ वाण चांगला आहे की कोएम ०२६५?", AgriculturalIntent.VARIETY_SELECTION),
        ("सुरू उसाची लागवड कधी करावी? पट्टा पद्धत कशी आहे?", AgriculturalIntent.PLANTING_SOWING),
        ("ऊस तोडणी प्रोग्राम कधी सुरू होणार? खोडवा व्यवस्थापन कसे करावे?", AgriculturalIntent.HARVESTING_POST_HARVEST),
        ("पुढील आठवड्यात पाऊस पडेल का? गारपिटीची शक्यता आहे का?", AgriculturalIntent.WEATHER_CLIMATE),
        ("महाडीबीटी ठिबक अनुदान योजना कशी अर्ज करावी?", AgriculturalIntent.GOVERNMENT_SCHEME_SUBSIDY),
        ("कारखान्याचा फील्ड ऑफिसर (CDO) कधी व्हिजिट करणार?", AgriculturalIntent.CDO_COORDINATION_INQUIRY),
        ("माझे क्षेत्र 5 एकर असून काळी माती आहे", AgriculturalIntent.FARMER_PROFILE_UPDATE),
        ("राम राम साहेब, नमस्कार 🙏", AgriculturalIntent.GENERAL_GREETING),
        ("सर्व पीक जळून गेले आहे, मी आत्महत्या करणार", AgriculturalIntent.DISTRESS_EMERGENCY),
        ("आजचा पंचांग व सुविचार ग्रुपमध्ये फॉरवर्ड केला आहे", AgriculturalIntent.OFF_TOPIC_OTHER),
    ]

    for text_sample, expected_intent in cases:
        res = classifier.classify(text_sample)
        assert res.intent == expected_intent, (
            f"Expected {expected_intent.value} for '{text_sample}', got {res.intent.value if res.intent else None}"
        )
        # Check backward compatibility mapping
        expected_legacy = INTENT_TO_LEGACY_CATEGORY[expected_intent]
        assert res.category == expected_legacy, (
            f"Legacy category mismatch for {expected_intent.value}: expected {expected_legacy}, got {res.category}"
        )

test("5.1 All 13 agricultural intents classified accurately with legacy mapping", test_5_1_all_13_intents)


def test_5_2_entity_extraction_marathi_hindi():
    classifier = WhatsAppMessageClassifier()
    entities = classifier.extract_entities("माझा 4.5 एकर ऊस आहे आणि वाण को ८६०३२ आहे, ठिबक सिंचन केले आहे")
    assert entities.get("crop") == "Sugarcane"
    assert entities.get("land_area") == 4.5
    assert entities.get("area_unit") == "ACRES"
    assert "CO86032" in entities.get("crop_variety", "").upper().replace(" ", "")
    assert entities.get("has_drip_irrigation") is True

test("5.2 Multilingual entity extraction (Crop, Area, Variety, Drip)", test_5_2_entity_extraction_marathi_hindi)


def test_5_3_ambiguous_message_clarification():
    classifier = WhatsAppMessageClassifier()
    # Ambiguous short question
    res = classifier.classify("कसे करायचे?")
    assert res.requires_clarification or res.confidence < 0.70

test("5.3 Ambiguous messages trigger low confidence or clarification requirement", test_5_3_ambiguous_message_clarification)


# =============================================================================
# SECTION 6: Transactional Outbox
# =============================================================================
print("\n" + "=" * 70)
print("SECTION 6: Transactional Outbox Pattern")
print("=" * 70)

class MockWhatsAppClient:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.sent_messages = []

    def send_message(self, to: str, message_text: str):
        if self.should_fail:
            raise ConnectionError("Meta WhatsApp API 503 Service Unavailable")
        self.sent_messages.append({"to": to, "text": message_text})


def test_6_1_outbox_durable_creation_and_dispatch():
    outbox_svc = OutboxService()
    mock_client = MockWhatsAppClient(should_fail=False)

    outbox_id = outbox_svc.enqueue(
        recipient_phone="9823000010",
        message_text="तुमचा सल्ला तयार आहे.",
        idempotency_key="key_test_01"
    )
    assert outbox_id.startswith("OUT-")
    assert outbox_svc.get_status(outbox_id) == OutboxMessageStatus.PENDING.value

    # Process dispatch
    report = outbox_svc.process_pending(client=mock_client)
    assert report["dispatched"] >= 1
    assert outbox_svc.get_status(outbox_id) == OutboxMessageStatus.DISPATCHED.value
    assert len(mock_client.sent_messages) >= 1

test("6.1 Outbox message durable enqueue and successful external dispatch", test_6_1_outbox_durable_creation_and_dispatch)


def test_6_2_outbox_retry_and_failure_handling():
    outbox_svc = OutboxService()
    failing_client = MockWhatsAppClient(should_fail=True)

    outbox_id = outbox_svc.enqueue(
        recipient_phone="9823000011",
        message_text="पुन्हा प्रयत्न संदेश.",
        idempotency_key="key_test_02",
        max_retries=2
    )

    # First attempt fails -> RETRYING
    outbox_svc.process_pending(client=failing_client)
    with get_db_session() as s:
        m = s.query(OutboxMessage).filter(OutboxMessage.outbox_id == outbox_id).first()
        assert m.status == OutboxMessageStatus.RETRYING
        assert m.retry_count == 1
        assert "503" in m.last_error

    # Second attempt fails -> FAILED (max retries reached)
    outbox_svc.process_pending(client=failing_client)
    with get_db_session() as s:
        m = s.query(OutboxMessage).filter(OutboxMessage.outbox_id == outbox_id).first()
        assert m.status == OutboxMessageStatus.FAILED
        assert m.retry_count == 2

test("6.2 Outbox failure increments retry count and transitions to FAILED", test_6_2_outbox_retry_and_failure_handling)


def test_6_3_outbox_duplicate_enqueue_prevention():
    outbox_svc = OutboxService()
    id1 = outbox_svc.enqueue("9823000012", "संदेश 1", idempotency_key="dup_key_99")
    id2 = outbox_svc.enqueue("9823000012", "संदेश 1", idempotency_key="dup_key_99")
    assert id1 == id2, "Duplicate enqueue with same idempotency key must return existing outbox ID"

test("6.3 Idempotency key prevents duplicate outbox queuing", test_6_3_outbox_duplicate_enqueue_prevention)


# =============================================================================
# SECTION 7: Field History Audit
# =============================================================================
print("\n" + "=" * 70)
print("SECTION 7: Field History Audit Trail")
print("=" * 70)

def test_7_1_field_history_recording():
    with get_db_session() as s:
        repo = FieldHistoryRepository(s)
        entry = repo.record_change(
            entity_type="CropRecord",
            entity_id=101,
            field_name="crop_name",
            old_value="Wheat",
            new_value="Sugarcane",
            changed_by="CDO_DESHMUKH",
            change_source="CDO_FIELD_INSPECTION"
        )
        assert entry is not None
        assert entry.old_value == "Wheat"
        assert entry.new_value == "Sugarcane"
        assert entry.changed_by == "CDO_DESHMUKH"
        s.commit()

        # Query history
        hist = repo.get_history(entity_type="CropRecord", entity_id=101)
        assert len(hist) >= 1
        assert hist[0].field_name == "crop_name"

test("7.1 FieldHistory records old and new values with actor attribution", test_7_1_field_history_recording)


def test_7_2_identical_values_skip_empty_history():
    with get_db_session() as s:
        repo = FieldHistoryRepository(s)
        entry = repo.record_change(
            entity_type="CropRecord",
            entity_id=102,
            field_name="crop_name",
            old_value="Sugarcane",
            new_value="Sugarcane",  # No change
            changed_by="SYSTEM"
        )
        assert entry is None, "Identical value must not create redundant audit entry"

test("7.2 Unchanged values skip creating empty audit records", test_7_2_identical_values_skip_empty_history)


# =============================================================================
# SUMMARY REPORT
# =============================================================================
print("\n" + "=" * 70)
print("PHASE 3 VERIFICATION SUMMARY")
print("=" * 70)

TOTAL = PASS + FAIL
print(f"\n  Total Tests : {TOTAL}")
print(f"  ✅ Passed   : {PASS}")
print(f"  ❌ Failed   : {FAIL}")

if FAIL > 0:
    print("\n  FAILED TESTS:")
    for status_str, label, err in RESULTS:
        if status_str == "FAIL":
            print(f"    ✗ {label}: {err}")
    sys.exit(1)
else:
    print(f"\n  🎉 ALL {TOTAL}/{TOTAL} PHASE 3 TESTS PASSED PERFECTLY!\n")
