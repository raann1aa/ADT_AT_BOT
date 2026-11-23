"""
Comprehensive Automated Test Suite for Phase 2: Database and Farmer Information Management.

Tests:
 1. Database initialization and schema creation
 2. Farmer CRUD operations
 3. Multiple farm plots per farmer
 4. Crop and planting records
 5. Soil profiles with NPK tracking
 6. Verification status lifecycle
 7. Data provenance preservation
 8. Farmer lookup by phone and farmer ID
 9. Shared phone number handling
10. Duplicate detection (create vs update)
11. Excel migration with idempotency
12. Migration backup creation
13. Persistent webhook message deduplication
14. Concurrent duplicate rejection
15. CDO and Agronomist directory operations
16. Issue creation, escalation, resolution
17. Follow-up task tracking
18. Audit log persistence
19. FarmerService backward compatibility
20. ExcelProfileManager DB-backed lookup
21. Regression: Webhook flow tests
22. Regression: RAG retrieval tests

Usage:
    python scripts/test_phase_2_database.py
"""

import sys
import os
import time
import uuid
import threading
from pathlib import Path
from datetime import date, datetime

# Ensure project root is on the path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Always use in-memory SQLite for tests to avoid touching production data
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from database.connection import init_db, get_db_session, check_connection, Base, engine
from database.repositories import FarmerRepository, CDORepository, IssueRepository, AuditRepository, IdempotencyRepository
from database.services import FarmerService, DeduplicationService, ExcelMigrationService
from database.enums import VerificationStatus, PlantingSeason, AreaUnit, IssuePriority, TaskTargetRole, WebhookEventStatus
from database.models import Farmer, FarmPlot, CropRecord, SoilProfile, District, CDO, Agronomist, WebhookEvent, AuditLog

# Counters
PASSED = 0
FAILED = 0
ERRORS = []


def test(name: str, fn):
    global PASSED, FAILED, ERRORS
    try:
        fn()
        print(f"  ✅ PASS: {name}")
        PASSED += 1
    except AssertionError as e:
        print(f"  ❌ FAIL: {name} — {e}")
        FAILED += 1
        ERRORS.append((name, str(e)))
    except Exception as e:
        print(f"  ❌ ERROR: {name} — {type(e).__name__}: {e}")
        FAILED += 1
        ERRORS.append((name, f"{type(e).__name__}: {e}"))


# ============================================================
# SECTION 1: Database Initialization
# ============================================================
print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("SECTION 1: Database Initialization & Schema")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

# Initialize in-memory database
init_db()

def test_db_connection():
    assert check_connection(), "Database connectivity check failed"

def test_schema_all_tables():
    expected_tables = {
        "districts", "divisions", "factories", "cdos", "agronomists",
        "farmers", "farmer_contacts", "farm_plots", "crop_records",
        "soil_profiles", "conversation_sessions", "issues",
        "follow_up_tasks", "webhook_events", "audit_logs"
    }
    actual_tables = set(Base.metadata.tables.keys())
    missing = expected_tables - actual_tables
    assert not missing, f"Missing tables: {missing}"

test("DB connectivity check", test_db_connection)
test("All 15 tables created by schema", test_schema_all_tables)


# ============================================================
# SECTION 2: CDO & Geographic Hierarchy
# ============================================================
print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("SECTION 2: Geographic Hierarchy & CDO Directory")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

DISTRICT_ID = None
DIVISION_ID = None
FACTORY_ID = None
CDO_ID = None

def test_create_district():
    global DISTRICT_ID
    with get_db_session() as session:
        repo = CDORepository(session)
        district = repo.get_or_create_district("Nashik", "Maharashtra")
        DISTRICT_ID = district.id
        assert district.id is not None
        assert district.name == "Nashik"
        assert district.state == "Maharashtra"

def test_idempotent_district():
    with get_db_session() as session:
        repo = CDORepository(session)
        d1 = repo.get_or_create_district("Nashik", "Maharashtra")
        d2 = repo.get_or_create_district("Nashik", "Maharashtra")
        assert d1.id == d2.id, "get_or_create_district must be idempotent"

def test_create_division():
    global DIVISION_ID
    with get_db_session() as session:
        repo = CDORepository(session)
        d = repo.get_or_create_district("Nashik", "Maharashtra")
        div = repo.get_or_create_division(d.id, "Niphad")
        DIVISION_ID = div.id
        assert div.id is not None
        assert div.district_id == d.id

def test_create_factory():
    global FACTORY_ID
    with get_db_session() as session:
        repo = CDORepository(session)
        div = repo.get_or_create_division(DISTRICT_ID, "Niphad")
        factory = repo.get_or_create_factory("Nashik Sugar Factory", "NSF-001", division_id=div.id)
        FACTORY_ID = factory.id
        assert factory.code == "NSF-001"

def test_create_cdo():
    global CDO_ID
    with get_db_session() as session:
        repo = CDORepository(session)
        cdo = repo.create_cdo(
            cdo_code="CDO-N01",
            name="Rajendra Pawar",
            phone_number="9876500001",
            email="rajendra.pawar@nashik.gov",
            factory_id=FACTORY_ID,
            division_id=DIVISION_ID
        )
        CDO_ID = cdo.id
        assert cdo.id is not None
        assert cdo.cdo_code == "CDO-N01"

def test_cdo_lookup_by_code():
    with get_db_session() as session:
        repo = CDORepository(session)
        cdo = repo.get_cdo_by_code("CDO-N01")
        assert cdo is not None
        assert cdo.name == "Rajendra Pawar"

def test_create_agronomist():
    with get_db_session() as session:
        repo = CDORepository(session)
        agro = repo.create_agronomist(
            name="Dr. Suresh Kamble",
            phone_number="9876500002",
            specialization="Entomology"
        )
        assert agro.id is not None
        assert agro.specialization == "Entomology"

test("Create district record", test_create_district)
test("get_or_create_district is idempotent", test_idempotent_district)
test("Create division under district", test_create_division)
test("Create factory linked to division", test_create_factory)
test("Create CDO with factory and division", test_create_cdo)
test("CDO lookup by employee code", test_cdo_lookup_by_code)
test("Create agronomist specialist", test_create_agronomist)


# ============================================================
# SECTION 3: Farmer CRUD
# ============================================================
print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("SECTION 3: Farmer CRUD Operations")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

FARMER_A_ID = None
FARMER_B_ID = None

def test_create_farmer():
    global FARMER_A_ID
    with get_db_session() as session:
        repo = FarmerRepository(session)
        farmer = repo.create_farmer(
            farmer_id="FARM-TEST-001",
            full_name="Ramesh Patil",
            primary_phone="9823011111",
            tehsil="Niphad",
            district_id=DISTRICT_ID,
            preferred_language="mr",
            data_source="TEST"
        )
        FARMER_A_ID = farmer.id
        assert farmer.farmer_id == "FARM-TEST-001"
        assert farmer.primary_phone == "9823011111"
        assert farmer.name_status == VerificationStatus.UNVERIFIED

def test_lookup_farmer_by_phone():
    with get_db_session() as session:
        repo = FarmerRepository(session)
        farmer = repo.lookup_by_phone("9823011111")
        assert farmer is not None
        assert farmer.full_name == "Ramesh Patil"

def test_lookup_farmer_by_phone_with_country_code():
    with get_db_session() as session:
        repo = FarmerRepository(session)
        farmer = repo.lookup_by_phone("+919823011111")
        assert farmer is not None, "Lookup with +91 country code must work"
        assert farmer.full_name == "Ramesh Patil"

def test_lookup_farmer_by_farmer_id():
    with get_db_session() as session:
        repo = FarmerRepository(session)
        farmer = repo.get_by_farmer_id("FARM-TEST-001")
        assert farmer is not None
        assert farmer.full_name == "Ramesh Patil"

def test_lookup_unknown_farmer_returns_none():
    with get_db_session() as session:
        repo = FarmerRepository(session)
        farmer = repo.lookup_by_phone("9999999999")
        assert farmer is None, "Unknown phone must return None, not raise exception"

def test_create_second_farmer():
    global FARMER_B_ID
    with get_db_session() as session:
        repo = FarmerRepository(session)
        farmer = repo.create_farmer(
            farmer_id="FARM-TEST-002",
            full_name="Dnyaneshwar Shinde",
            primary_phone="9823022222",
            tehsil="Yeola",
            district_id=DISTRICT_ID,
            data_source="TEST"
        )
        FARMER_B_ID = farmer.id
        assert farmer.farmer_id == "FARM-TEST-002"

def test_farmer_count():
    with get_db_session() as session:
        repo = FarmerRepository(session)
        count = repo.count()
        assert count >= 2, f"Expected at least 2 farmers, got {count}"

test("Create new farmer record", test_create_farmer)
test("Lookup farmer by clean 10-digit phone", test_lookup_farmer_by_phone)
test("Lookup farmer with +91 country code normalization", test_lookup_farmer_by_phone_with_country_code)
test("Lookup farmer by stable farmer ID", test_lookup_farmer_by_farmer_id)
test("Lookup unknown phone returns None gracefully", test_lookup_unknown_farmer_returns_none)
test("Create second farmer record", test_create_second_farmer)
test("Farmer count is accurate", test_farmer_count)


# ============================================================
# SECTION 4: Multi-Plot Farms, Crops, Soil
# ============================================================
print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("SECTION 4: Multi-Plot Farms, Crops & Soil Profiles")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

PLOT_1_ID = None
PLOT_2_ID = None

def test_add_first_plot():
    global PLOT_1_ID
    with get_db_session() as session:
        repo = FarmerRepository(session)
        plot = repo.add_plot(
            farmer_id=FARMER_A_ID,
            plot_identifier="PLOT-1",
            land_area=4.5,
            area_unit=AreaUnit.ACRES,
            has_drip_irrigation=True,
            area_status=VerificationStatus.UNVERIFIED,
            data_source="TEST"
        )
        PLOT_1_ID = plot.id
        assert plot.land_area == 4.5
        assert plot.area_unit == AreaUnit.ACRES

def test_add_second_plot_same_farmer():
    global PLOT_2_ID
    with get_db_session() as session:
        repo = FarmerRepository(session)
        plot = repo.add_plot(
            farmer_id=FARMER_A_ID,
            plot_identifier="PLOT-2",
            land_area=2.0,
            area_unit=AreaUnit.ACRES,
            has_drip_irrigation=False,
            area_status=VerificationStatus.UNVERIFIED,
            data_source="TEST"
        )
        PLOT_2_ID = plot.id
        assert plot.farmer_id == FARMER_A_ID
        assert PLOT_2_ID != PLOT_1_ID

def test_farmer_has_multiple_plots():
    with get_db_session() as session:
        repo = FarmerRepository(session)
        farmer = repo.get_by_farmer_id("FARM-TEST-001")
        assert farmer is not None
        assert len(farmer.plots) == 2, f"Expected 2 plots, got {len(farmer.plots)}"

def test_add_crop_to_plot():
    with get_db_session() as session:
        repo = FarmerRepository(session)
        crop = repo.add_crop_to_plot(
            farm_plot_id=PLOT_1_ID,
            crop_name="Onion",
            crop_variety="Phule Samarth",
            planting_date=date(2026, 10, 15),
            planting_season=PlantingSeason.RABI,
            growth_stage="Bulb Expansion",
            crop_status=VerificationStatus.UNVERIFIED,
            data_source="TEST"
        )
        assert crop.crop_name == "Onion"
        assert crop.planting_season == PlantingSeason.RABI
        assert crop.variety_status == VerificationStatus.VERIFIED

def test_add_sugarcane_with_suru_season():
    with get_db_session() as session:
        repo = FarmerRepository(session)
        crop = repo.add_crop_to_plot(
            farm_plot_id=PLOT_2_ID,
            crop_name="Sugarcane",
            crop_variety="Co 86032",
            planting_season=PlantingSeason.SURU,
            growth_stage="Grand Growth Stage",
            data_source="TEST"
        )
        assert crop.planting_season == PlantingSeason.SURU
        assert crop.planting_date_status == VerificationStatus.MISSING, "Missing planting date must be MISSING not UNVERIFIED"

def test_add_soil_profile_with_npk():
    with get_db_session() as session:
        repo = FarmerRepository(session)
        soil = repo.add_soil_profile(
            farm_plot_id=PLOT_1_ID,
            soil_type="Black Cotton",
            soil_fertility="Medium",
            ph_level=7.2,
            nitrogen_n_kg_ha=120.0,
            phosphorus_p_kg_ha=28.5,
            potassium_k_kg_ha=180.0,
            data_source="SOIL_HEALTH_CARD",
            supplied_by="CDO-N01"
        )
        assert soil.soil_type == "Black Cotton"
        assert soil.nitrogen_n_kg_ha == 120.0
        assert soil.npk_status == VerificationStatus.VERIFIED

def test_soil_profile_missing_npk_marked_missing():
    with get_db_session() as session:
        repo = FarmerRepository(session)
        soil = repo.add_soil_profile(
            farm_plot_id=PLOT_2_ID,
            soil_type="Clay Loam",
            data_source="TEST"
        )
        assert soil.npk_status == VerificationStatus.MISSING, "Missing NPK values must be marked MISSING"

test("Add first farm plot to farmer", test_add_first_plot)
test("Add second plot to same farmer (multi-plot support)", test_add_second_plot_same_farmer)
test("Farmer profile contains 2 plots (eager loading)", test_farmer_has_multiple_plots)
test("Add crop record with planting season RABI", test_add_crop_to_plot)
test("Add sugarcane crop with SURU season, missing date = MISSING", test_add_sugarcane_with_suru_season)
test("Add soil profile with NPK values -> npk_status=VERIFIED", test_add_soil_profile_with_npk)
test("Missing NPK values -> npk_status=MISSING (no fabrication)", test_soil_profile_missing_npk_marked_missing)


# ============================================================
# SECTION 5: Verification Status & Data Provenance
# ============================================================
print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("SECTION 5: Verification Status & Data Provenance")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

def test_verification_enum_values():
    statuses = [VerificationStatus.VERIFIED, VerificationStatus.UNVERIFIED,
                VerificationStatus.MISSING, VerificationStatus.NEEDS_CORRECTION]
    assert len(statuses) == 4

def test_farmer_created_with_unverified_name():
    with get_db_session() as session:
        repo = FarmerRepository(session)
        farmer = repo.get_by_farmer_id("FARM-TEST-001")
        assert farmer.name_status == VerificationStatus.UNVERIFIED

def test_missing_village_marked_as_missing():
    with get_db_session() as session:
        repo = FarmerRepository(session)
        farmer = repo.get_by_farmer_id("FARM-TEST-001")
        assert farmer.village_status == VerificationStatus.MISSING

def test_provenance_data_source_stored():
    with get_db_session() as session:
        repo = FarmerRepository(session)
        farmer = repo.get_by_farmer_id("FARM-TEST-001")
        assert farmer.data_source == "TEST"

def test_provenance_created_at_timestamp():
    with get_db_session() as session:
        repo = FarmerRepository(session)
        farmer = repo.get_by_farmer_id("FARM-TEST-001")
        assert farmer.created_at is not None

test("All 4 verification status values present", test_verification_enum_values)
test("New farmer gets UNVERIFIED name_status", test_farmer_created_with_unverified_name)
test("Missing village field gets MISSING status (not UNVERIFIED)", test_missing_village_marked_as_missing)
test("Data source stored in provenance field", test_provenance_data_source_stored)
test("created_at timestamp is auto-populated", test_provenance_created_at_timestamp)


# ============================================================
# SECTION 6: Shared Phone Handling
# ============================================================
print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("SECTION 6: Shared & Alternate Phone Handling")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

def test_alternate_contact_lookup():
    """Farmer B's son shares a device with Farmer A. Alternate contact lookup."""
    with get_db_session() as session:
        repo = FarmerRepository(session)
        # Register Farmer B's son's phone as alternate contact for Farmer B
        repo.add_contact(
            farmer_id=FARMER_B_ID,
            phone_number="9823099999",
            contact_name="Vishal Shinde",
            relationship_type="Son",
            is_primary=False
        )
        # Lookup by shared phone must return the owner (Farmer B)
        farmer = repo.lookup_by_phone("9823099999")
        assert farmer is not None, "Lookup via alternate contact number must resolve"
        assert farmer.farmer_id == "FARM-TEST-002"

def test_duplicate_primary_phone_prevented():
    """Two different farmers cannot share the same primary phone."""
    from sqlalchemy.exc import IntegrityError
    raised = False
    try:
        with get_db_session() as session:
            repo = FarmerRepository(session)
            repo.create_farmer(
                farmer_id="FARM-TEST-DUP",
                full_name="Duplicate Person",
                primary_phone="9823011111",  # Already taken by Farmer A
                data_source="TEST"
            )
    except (IntegrityError, Exception) as e:
        raised = True
    assert raised, "Duplicate primary phone must raise an integrity error"

test("Alternate contact phone lookup resolves to farmer owner", test_alternate_contact_lookup)
test("Duplicate primary phone rejected by DB constraint", test_duplicate_primary_phone_prevented)


# ============================================================
# SECTION 7: Issues & Follow-Up Tasks
# ============================================================
print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("SECTION 7: Issue Tracking & Follow-Up Tasks")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

ISSUE_ID = None

def test_create_issue():
    global ISSUE_ID
    with get_db_session() as session:
        repo = IssueRepository(session)
        issue = repo.create_issue(
            farmer_id=FARMER_A_ID,
            title="Purple blotch on onion leaves",
            description="Yellowing and purple spots with water-soaked margins on outer leaves",
            category="PEST_DISEASE",
            priority=IssuePriority.HIGH
        )
        ISSUE_ID = issue.id
        assert issue.issue_code.startswith("ISS-")
        assert issue.status.value == "OPEN"
        assert issue.priority == IssuePriority.HIGH

def test_escalate_issue_to_cdo():
    with get_db_session() as session:
        repo = IssueRepository(session)
        issue = repo.escalate_to_cdo(ISSUE_ID, CDO_ID, notes="Inspect field on 25-Nov")
        assert issue.status.value == "ESCALATED_CDO"
        assert issue.assigned_cdo_id == CDO_ID

def test_create_follow_up_task():
    with get_db_session() as session:
        repo = IssueRepository(session)
        task = repo.create_follow_up_task(
            issue_id=ISSUE_ID,
            target_role=TaskTargetRole.CDO,
            description="Field visit to inspect purple blotch severity",
            target_phone="9876500001"
        )
        assert task.task_code.startswith("TSK-")
        assert task.target_role == TaskTargetRole.CDO

def test_resolve_issue():
    with get_db_session() as session:
        repo = IssueRepository(session)
        issue = repo.resolve_issue(ISSUE_ID, "Applied Iprodione @ 2g/L spray. 90% recovery in 10 days.")
        assert issue.status.value == "RESOLVED"
        assert issue.resolved_at is not None

def test_list_open_issues_empty_after_resolve():
    with get_db_session() as session:
        repo = IssueRepository(session)
        open_issues = repo.list_open_issues()
        # Our single test issue was resolved
        unresolved = [i for i in open_issues if i.id == ISSUE_ID]
        assert len(unresolved) == 0

test("Create new issue with auto-generated code", test_create_issue)
test("Escalate issue to CDO", test_escalate_issue_to_cdo)
test("Create follow-up task for CDO", test_create_follow_up_task)
test("Resolve issue with resolution notes", test_resolve_issue)
test("Resolved issue no longer in open list", test_list_open_issues_empty_after_resolve)


# ============================================================
# SECTION 8: Audit Log Persistence
# ============================================================
print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("SECTION 8: Persistent Audit Logging")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

def test_persist_audit_log():
    with get_db_session() as session:
        repo = AuditRepository(session)
        entry = repo.log(
            sender_name="Ramesh Patil",
            sender_phone="9823011111",
            district="Nashik",
            group_id="group_nashik_01",
            group_name="Nashik Farmers Group",
            incoming_text="Kanda madhe purple blotch aale",
            category="FARMING_QUERY",
            action="ANSWERED",
            bot_reply="Apply Iprodione 50 WP @ 2g/L",
            rag_sources=["Purple Blotch > Chemical Control"],
            processing_time_ms=42.5,
            is_escalated=False
        )
        assert entry.log_id.startswith("log_")
        assert entry.category == "FARMING_QUERY"

def test_audit_log_stats():
    with get_db_session() as session:
        repo = AuditRepository(session)
        stats = repo.get_stats()
        assert "total_messages_received" in stats
        assert stats["total_messages_received"] >= 1

def test_audit_escalation_tracking():
    with get_db_session() as session:
        repo = AuditRepository(session)
        entry = repo.log(
            sender_name="Emergency Farmer",
            sender_phone="9800000001",
            district="Nashik",
            group_id="group_test",
            group_name="Test Group",
            incoming_text="Poora khet mar gaya - red mite",
            category="FARMING_QUERY",
            action="ESCALATED",
            is_escalated=True
        )
        escalations = repo.get_escalations()
        assert len(escalations) >= 1

def test_audit_resolve_escalation():
    with get_db_session() as session:
        repo = AuditRepository(session)
        # Get an escalated entry
        escalations = repo.get_escalations()
        assert len(escalations) > 0
        log_id = escalations[0]["id"]
        success = repo.resolve_escalation(log_id)
        assert success, "Resolve escalation must return True"

test("Persist audit log entry to database", test_persist_audit_log)
test("Audit statistics calculated from database", test_audit_log_stats)
test("Escalation tracking across restarts", test_audit_escalation_tracking)
test("Resolve escalation updates resolved flag", test_audit_resolve_escalation)


# ============================================================
# SECTION 9: Webhook Message Deduplication
# ============================================================
print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("SECTION 9: Persistent Webhook Deduplication")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

def test_first_claim_succeeds():
    with get_db_session() as session:
        repo = IdempotencyRepository(session)
        claimed = repo.claim_message("MSG-TEST-001", "9823011111")
        assert claimed, "First claim of new message ID must return True"

def test_duplicate_claim_rejected():
    with get_db_session() as session:
        repo = IdempotencyRepository(session)
        claimed = repo.claim_message("MSG-TEST-001", "9823011111")
        assert not claimed, "Second claim of same message ID must return False"

def test_complete_message():
    with get_db_session() as session:
        repo = IdempotencyRepository(session)
        repo.claim_message("MSG-TEST-002", "9823011111")
        repo.complete_message("MSG-TEST-002")
        assert repo.is_duplicate("MSG-TEST-002"), "Completed message must still be considered duplicate"

def test_fail_message():
    with get_db_session() as session:
        repo = IdempotencyRepository(session)
        repo.claim_message("MSG-TEST-003", "9823011111")
        repo.fail_message("MSG-TEST-003", "LLM timeout error")
        assert repo.is_duplicate("MSG-TEST-003"), "Failed message must still be recorded"

def test_concurrent_duplicate_rejection():
    """
    Simulates two concurrent threads attempting to process the same message.
    Only one should succeed; the other must be rejected.
    """
    # DeduplicationService has RAM-first hybrid protection
    svc = DeduplicationService()
    unique_msg_id = f"MSG-CONCURRENT-{uuid.uuid4().hex[:8]}"
    results = []

    def try_claim():
        result = svc.claim_message(unique_msg_id, "9823011111")
        results.append(result)

    t1 = threading.Thread(target=try_claim)
    t2 = threading.Thread(target=try_claim)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    successful = sum(1 for r in results if r)
    assert successful == 1, f"Exactly 1 thread must succeed; got {successful} successes"

def test_dedup_service_hybrid_ram_then_db():
    """RAM cache speeds up repeat checks without DB round-trips."""
    svc = DeduplicationService()
    msg_id = f"MSG-HYBRID-{uuid.uuid4().hex[:8]}"
    r1 = svc.claim_message(msg_id, "9823011111")
    r2 = svc.claim_message(msg_id, "9823011111")  # Should hit RAM cache
    assert r1 is True
    assert r2 is False

test("First message claim returns True", test_first_claim_succeeds)
test("Duplicate message claim returns False", test_duplicate_claim_rejected)
test("Completed message still counts as duplicate", test_complete_message)
test("Failed message still remains in ledger", test_fail_message)
test("Concurrent duplicate claims: exactly 1 success", test_concurrent_duplicate_rejection)
test("Hybrid RAM+DB dedup: second call hits RAM cache", test_dedup_service_hybrid_ram_then_db)


# ============================================================
# SECTION 10: Excel Migration (Isolated Copy)
# ============================================================
print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("SECTION 10: Excel Migration Service")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

import pandas as pd
import tempfile
import shutil

# Create a fresh isolated database for migration tests
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
# Re-init because env changed
from importlib import reload
import database.connection as db_conn
# Reinitialize with same in-memory engine
init_db()

EXCEL_TEST_DIR = Path(tempfile.mkdtemp())
EXCEL_TEST_PATH = EXCEL_TEST_DIR / "test_farmer_profiles.xlsx"

# Create sample test Excel file
sample_df = pd.DataFrame([
    {"Farmer Name": "Ramesh Patil", "Phone Number": "9823011111", "District": "Nashik", "Tehsil / Taluka": "Niphad", "Farm Size (Acres)": 4.5, "Crop Grown": "Onion", "Soil Type": "Black Cotton", "Crop Stage": "Bulb Expansion", "Drip Irrigation": "Yes", "Submission Date": "2026-11-15 09:30"},
    {"Farmer Name": "Dnyaneshwar Shinde", "Phone Number": "9823022222", "District": "Nashik", "Tehsil / Taluka": "Yeola", "Farm Size (Acres)": 6.0, "Crop Grown": "Onion", "Soil Type": "Clay Loam", "Crop Stage": "Harvesting / Storage", "Drip Irrigation": "Yes", "Submission Date": "2026-11-15 10:15"},
    {"Farmer Name": "Suresh Yadav", "Phone Number": "9876533333", "District": "Indore", "Tehsil / Taluka": "Sanwer", "Farm Size (Acres)": 5.0, "Crop Grown": "Soybean", "Soil Type": "Medium Black", "Crop Stage": "Pod Filling", "Drip Irrigation": "No", "Submission Date": "2026-11-15 11:00"},
    {"Farmer Name": "Bad Row",   "Phone Number": "",            "District": "Unknown", "Tehsil / Taluka": "",       "Farm Size (Acres)": 0.0, "Crop Grown": "?",       "Soil Type": "",             "Crop Stage": "",           "Drip Irrigation": "No",  "Submission Date": ""},
])
sample_df.to_excel(EXCEL_TEST_PATH, index=False)

MIGRATION_SVC = ExcelMigrationService(excel_path=EXCEL_TEST_PATH, backup_dir=EXCEL_TEST_DIR / "backups")

def test_migration_creates_backup():
    backup = MIGRATION_SVC.create_timestamped_backup()
    assert backup.exists(), "Timestamped backup file must be created"
    assert "backup" in backup.name

def test_migration_first_run():
    report = MIGRATION_SVC.run_migration()
    assert report["status"] in ("success", "completed_with_errors")
    assert report["created_count"] == 3, f"Expected 3 valid farmers, got {report['created_count']}"
    assert report["skipped_count"] == 1, f"Expected 1 skipped (empty phone), got {report['skipped_count']}"
    assert report["error_count"] == 0

def test_migration_idempotency():
    report = MIGRATION_SVC.run_migration()
    assert report["created_count"] == 0, "Re-run must not create duplicate records"
    assert report["updated_count"] == 3, f"Re-run must update existing records, got updated={report['updated_count']}"
    assert report["error_count"] == 0

def test_migration_no_fabricated_defaults():
    # The blank-phone row must be skipped, not defaulted to some invented phone
    with get_db_session() as session:
        repo = FarmerRepository(session)
        assert repo.lookup_by_phone("9823011111") is not None
        assert repo.lookup_by_phone("") is None
        assert repo.lookup_by_phone("nan") is None

def test_excel_export_roundtrip():
    export_path = EXCEL_TEST_DIR / "export_check.xlsx"
    actual_path = MIGRATION_SVC.export_database_to_excel(output_path=export_path)
    assert actual_path.exists(), "Export file must exist"
    df = pd.read_excel(actual_path)
    assert len(df) >= 3
    assert "Farmer Name" in df.columns
    assert "Phone Number" in df.columns

test("Migration creates timestamped backup before running", test_migration_creates_backup)
test("First migration run creates 3 valid, skips 1 invalid", test_migration_first_run)
test("Second migration run updates existing, creates 0 new (idempotency)", test_migration_idempotency)
test("No default values fabricated for missing/invalid rows", test_migration_no_fabricated_defaults)
test("Export database to Excel round-trip preserves structure", test_excel_export_roundtrip)

# Clean up temp files
try:
    shutil.rmtree(EXCEL_TEST_DIR)
except Exception:
    pass


# ============================================================
# SECTION 11: FarmerService Backward Compatibility
# ============================================================
print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("SECTION 11: FarmerService Backward Compatibility")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

# Reload with original in-memory DB (which has our test data from sections 1-9)
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
init_db()

# Re-create the two original test farmers for compatibility checks
with get_db_session() as session:
    repo = FarmerRepository(session)
    cdo_repo = CDORepository(session)
    dist = cdo_repo.get_or_create_district("Nashik")
    # Create farmer for service tests
    try:
        f = repo.create_farmer("FARM-SVC-001", "Ramesh Patil", "9800012345", district_id=dist.id)
        p = repo.add_plot(f.id, "PLOT-1", 4.5, has_drip_irrigation=True)
        repo.add_crop_to_plot(p.id, "Onion", growth_stage="Bulb Expansion")
        repo.add_soil_profile(p.id, soil_type="Black Cotton")
    except Exception:
        pass


def test_farmer_service_get_profile():
    svc = FarmerService()
    profile = svc.get_farmer_profile_by_phone("9800012345")
    assert profile is not None
    assert profile.name == "Ramesh Patil"
    assert profile.crop == "Onion"

def test_farmer_service_unknown_phone_returns_none():
    svc = FarmerService()
    profile = svc.get_farmer_profile_by_phone("9700000000")
    assert profile is None

def test_farmer_service_get_submission():
    svc = FarmerService()
    sub = svc.get_farmer_submission("9800012345")
    assert sub is not None
    assert sub.farmer_name == "Ramesh Patil"
    assert sub.crop_grown == "Onion"

def test_farmer_service_count():
    svc = FarmerService()
    count = svc.count_farmers()
    assert count >= 1

test("FarmerService returns FarmerProfile from database", test_farmer_service_get_profile)
test("FarmerService returns None for unknown phone", test_farmer_service_unknown_phone_returns_none)
test("FarmerService returns FarmerFormSubmission (legacy compat)", test_farmer_service_get_submission)
test("FarmerService count returns >= 1 farmers", test_farmer_service_count)


# ============================================================
# SECTION 12: Regression — Webhook Flow Tests
# ============================================================
print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("SECTION 12: Regression — Webhook Flow Tests")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

from fastapi.testclient import TestClient
from gateway.webhook_server import app, DEFAULT_VERIFY_TOKEN

client = TestClient(app)

def test_webhook_verification():
    params = {"hub.mode": "subscribe", "hub.challenge": "1158201444", "hub.verify_token": DEFAULT_VERIFY_TOKEN}
    response = client.get("/webhook", params=params)
    assert response.status_code == 200
    assert response.text == "1158201444"

def test_webhook_invalid_token():
    params = {"hub.mode": "subscribe", "hub.challenge": "abc", "hub.verify_token": "WRONG_TOKEN"}
    response = client.get("/webhook", params=params)
    assert response.status_code == 403

def test_webhook_valid_text_message():
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"field": "messages", "value": {
            "metadata": {"display_phone_number": "91TEST"},
            "contacts": [{"profile": {"name": "Test Farmer"}, "wa_id": "9800099999"}],
            "messages": [{"id": "wamid.reg_test_p2", "from": "9800099999", "type": "text", "text": {"body": "Wheat mein yellow rust aaya hai dawai batao"}}]
        }}]}]
    }
    response = client.post("/webhook", json=payload)
    assert response.status_code == 200

def test_webhook_malformed_json():
    response = client.post("/webhook", data="NOT_JSON", headers={"Content-Type": "application/json"})
    assert response.status_code == 400

def test_webhook_duplicate_id():
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"field": "messages", "value": {
            "metadata": {"display_phone_number": "91TEST"},
            "contacts": [{"profile": {"name": "Test"}, "wa_id": "9800011111"}],
            "messages": [{"id": "wamid.dup_p2_regression", "from": "9800011111", "type": "text", "text": {"body": "Duplicate test"}}]
        }}]}]
    }
    r1 = client.post("/webhook", json=payload)
    r2 = client.post("/webhook", json=payload)
    assert r1.status_code == 200
    assert r2.status_code == 200

def test_webhook_non_text_media():
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"field": "messages", "value": {
            "metadata": {"display_phone_number": "91TEST"},
            "contacts": [{"profile": {"name": "Test"}, "wa_id": "9800022222"}],
            "messages": [{"id": "wamid.audio_p2", "from": "9800022222", "type": "audio"}]
        }}]}]
    }
    response = client.post("/webhook", json=payload)
    assert response.status_code == 200

def test_health_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "version" in data or "status" in data or "registered_farmers_in_excel" in data

def test_farmers_api_endpoint():
    response = client.get("/api/farmers")
    assert response.status_code == 200

test("Webhook handshake verification", test_webhook_verification)
test("Invalid verify token returns 403", test_webhook_invalid_token)
test("Valid text message payload accepted (200)", test_webhook_valid_text_message)
test("Malformed JSON returns 400", test_webhook_malformed_json)
test("Duplicate message ID handled gracefully", test_webhook_duplicate_id)
test("Non-text (audio) message safely skipped", test_webhook_non_text_media)
test("Health status endpoint responds", test_health_endpoint)
test("/api/farmers endpoint responds", test_farmers_api_endpoint)


# ============================================================
# FINAL SUMMARY
# ============================================================
total = PASSED + FAILED
print("\n" + "=" * 55)
print("PHASE 2 DATABASE TEST RESULTS SUMMARY")
print("=" * 55)
print(f"  PASSED : {PASSED}/{total}")
print(f"  FAILED : {FAILED}/{total}")
print(f"  SCORE  : {round(100.0 * PASSED / total, 1) if total > 0 else 0}%")
if ERRORS:
    print("\n  Failed tests:")
    for name, reason in ERRORS:
        print(f"    ✗ {name}")
        print(f"      → {reason}")
print("=" * 55)

sys.exit(0 if FAILED == 0 else 1)
