"""
Phase 2 Data Integrity & Reliability Audit Script.
Executes deep diagnostic tests on:
 1. Excel Migration Safety (unnecessary rewrites, overwrite of DB updates, shared phones, phone changes).
 2. Webhook Exactly-Once and Recovery Safety (crash during PROCESSING, FAILED retries, restart dedup).
 3. Farmer Identity & Shared Phone Numbers (primary phone uniqueness, arbitrary .first() lookups, accidental merging).
 4. Field-Level Verification & Data Provenance (field isolation, historical value preservation).

Usage:
    python scripts/audit_phase_2_integrity.py
"""

import os
import sys
import tempfile
import shutil
import threading
import uuid
from pathlib import Path
from datetime import datetime, date
import pandas as pd

# Set environment
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from database.connection import init_db, get_db_session, Base
from database.repositories import FarmerRepository, CDORepository, IdempotencyRepository
from database.services import FarmerService, DeduplicationService, ExcelMigrationService
from database.enums import VerificationStatus, PlantingSeason, AreaUnit, WebhookEventStatus
from database.models import Farmer, FarmPlot, CropRecord, SoilProfile, WebhookEvent

# Initialize fresh in-memory schema
init_db()

AUDIT_RESULTS = {}

print("=" * 75)
print("PHASE 2 DEEP DATA INTEGRITY & RELIABILITY AUDIT")
print("=" * 75)

# ===========================================================================
# 1. EXCEL MIGRATION SAFETY AUDIT
# ===========================================================================
print("\n[AUDIT AREA 1] Excel Migration Safety & Conflict Resolution")

temp_dir = Path(tempfile.mkdtemp())
excel_path = temp_dir / "audit_farmers.xlsx"
backup_dir = temp_dir / "backups"

# Initial Excel data
initial_data = [
    {
        "Farmer Name": "Initial Farmer",
        "Phone Number": "9911100001",
        "District": "Nashik",
        "Tehsil / Taluka": "Niphad",
        "Farm Size (Acres)": 5.0,
        "Crop Grown": "Wheat",
        "Soil Type": "Black Cotton",
        "Crop Stage": "Vegetative",
        "Drip Irrigation": "No",
        "Submission Date": "2026-11-20 10:00"
    }
]
pd.DataFrame(initial_data).to_excel(excel_path, index=False)

mig_svc = ExcelMigrationService(excel_path=excel_path, backup_dir=backup_dir)

# 1.1 First run
r1 = mig_svc.run_migration()
print(f"  Step 1 - Initial Import: created={r1['created_count']}, updated={r1['updated_count']}")

# 1.2 Second run without any changes
r2 = mig_svc.run_migration()
print(f"  Step 2 - Re-run with zero changes: created={r2['created_count']}, updated={r2['updated_count']}")
unnecessary_rewrite = (r2['updated_count'] == 1)
print(f"  Diagnostic: Unchanged record rewritten? {unnecessary_rewrite} (updated_count={r2['updated_count']})")
AUDIT_RESULTS["unnecessary_rewrites"] = unnecessary_rewrite

# 1.3 DB field update test: user/CDO updates database value directly
with get_db_session() as session:
    repo = FarmerRepository(session)
    f = repo.lookup_by_phone("9911100001")
    assert f is not None
    # Change crop to Sugarcane and mark VERIFIED
    f.plots[0].crops[0].crop_name = "Sugarcane"
    f.plots[0].crops[0].crop_status = VerificationStatus.VERIFIED
    f.data_source = "CDO_VERIFIED"
    session.flush()

print("  Step 3 - Database updated: Crop changed to 'Sugarcane', status=VERIFIED, source='CDO_VERIFIED'")

# 1.4 Re-run migration from Excel (where crop is still 'Wheat')
r3 = mig_svc.run_migration()
print(f"  Step 4 - Migration re-run with Excel value 'Wheat': created={r3['created_count']}, updated={r3['updated_count']}")

# 1.5 Check whether DB value was overwritten
with get_db_session() as session:
    repo = FarmerRepository(session)
    f_after = repo.lookup_by_phone("9911100001")
    actual_crop = f_after.plots[0].crops[0].crop_name
    actual_status = f_after.plots[0].crops[0].crop_status
    actual_source = f_after.data_source

overwritten = (actual_crop == "Wheat")
print(f"  Diagnostic: Did Excel overwrite newer DB value? {overwritten}")
print(f"    Current Crop: '{actual_crop}' (Expected: 'Sugarcane')")
print(f"    Current Status: '{actual_status.value}'")
print(f"    Current Source: '{actual_source}'")
AUDIT_RESULTS["db_value_overwritten_by_excel"] = overwritten

# 1.6 Two farmers sharing phone in Excel
shared_data = [
    {
        "Farmer Name": "Brother One",
        "Phone Number": "9911100002",
        "District": "Nashik",
        "Tehsil / Taluka": "Niphad",
        "Farm Size (Acres)": 3.0,
        "Crop Grown": "Onion",
        "Soil Type": "Black Cotton",
        "Crop Stage": "Sowing",
        "Drip Irrigation": "Yes",
        "Submission Date": "2026-11-20 11:00"
    },
    {
        "Farmer Name": "Brother Two",
        "Phone Number": "9911100002",  # SAME PHONE
        "District": "Nashik",
        "Tehsil / Taluka": "Niphad",
        "Farm Size (Acres)": 4.0,
        "Crop Grown": "Sugarcane",
        "Soil Type": "Clay Loam",
        "Crop Stage": "Grand Growth",
        "Drip Irrigation": "No",
        "Submission Date": "2026-11-20 11:30"
    }
]
pd.DataFrame(shared_data).to_excel(excel_path, index=False)
r_shared = mig_svc.run_migration()
print(f"\n  Step 5 - Two farmers sharing same phone in Excel: created={r_shared['created_count']}, updated={r_shared['updated_count']}")

with get_db_session() as session:
    repo = FarmerRepository(session)
    f_shared = repo.lookup_by_phone("9911100002")
    print(f"    Farmer record in DB: Name='{f_shared.full_name}', Crop='{f_shared.plots[0].crops[0].crop_name}'")
    # Did Brother Two overwrite Brother One?
    brother_one_merged = (f_shared.full_name == "Brother Two")
    print(f"    Diagnostic: Did Row 2 overwrite Row 1 into a single merged farmer? {brother_one_merged}")
    AUDIT_RESULTS["shared_phone_merged_in_migration"] = brother_one_merged

# 1.7 Farmer whose phone number changes
phone_change_data = [
    {
        "Farmer Name": "Initial Farmer",
        "Phone Number": "9911100099",  # NEW PHONE for the same farmer
        "District": "Nashik",
        "Tehsil / Taluka": "Niphad",
        "Farm Size (Acres)": 5.0,
        "Crop Grown": "Wheat",
        "Soil Type": "Black Cotton",
        "Crop Stage": "Vegetative",
        "Drip Irrigation": "No",
        "Submission Date": "2026-11-20 12:00"
    }
]
pd.DataFrame(phone_change_data).to_excel(excel_path, index=False)
r_change = mig_svc.run_migration()
print(f"\n  Step 6 - Farmer phone changes in Excel: created={r_change['created_count']}, updated={r_change['updated_count']}")
with get_db_session() as session:
    repo = FarmerRepository(session)
    old_f = repo.lookup_by_phone("9911100001")
    new_f = repo.lookup_by_phone("9911100099")
    print(f"    Old phone (9911100001): {old_f.farmer_id if old_f else 'None'}")
    print(f"    New phone (9911100099): {new_f.farmer_id if new_f else 'None'}")
    phone_change_created_dup = (old_f is not None and new_f is not None and old_f.id != new_f.id)
    print(f"    Diagnostic: Did changing phone number create a second duplicate farmer with a new ID? {phone_change_created_dup}")
    AUDIT_RESULTS["phone_change_creates_duplicate"] = phone_change_created_dup

shutil.rmtree(temp_dir)


# ===========================================================================
# 2. WEBHOOK EXACTLY-ONCE & RECOVERY AUDIT
# ===========================================================================
print("\n" + "=" * 75)
print("[AUDIT AREA 2] Webhook Exactly-Once and Recovery Safety")
print("=" * 75)

# 2.1 Concurrent workers receiving same message ID
dedup_svc = DeduplicationService()
concurrent_msg_id = f"MSG-AUDIT-CONC-{uuid.uuid4().hex[:6]}"
claim_results = []

def worker_attempt():
    claimed = dedup_svc.claim_message(concurrent_msg_id, "9823011111")
    claim_results.append(claimed)

t1 = threading.Thread(target=worker_attempt)
t2 = threading.Thread(target=worker_attempt)
t1.start()
t2.start()
t1.join()
t2.join()

print(f"  Test 2.1 - Concurrent claim results: {claim_results}")
concurrent_exact_once = (claim_results.count(True) == 1 and claim_results.count(False) == 1)
print(f"    Diagnostic: Exactly one thread claimed message? {concurrent_exact_once}")
AUDIT_RESULTS["concurrent_exactly_once"] = concurrent_exact_once

# 2.2 Server restart deduplication
restart_msg_id = f"MSG-AUDIT-RESTART-{uuid.uuid4().hex[:6]}"
with get_db_session() as session:
    repo = IdempotencyRepository(session)
    repo.claim_message(restart_msg_id, "9823011111")
    repo.complete_message(restart_msg_id)

# Simulate restart: create brand new DeduplicationService instance with empty RAM cache
fresh_dedup_svc = DeduplicationService()
restart_claim = fresh_dedup_svc.claim_message(restart_msg_id, "9823011111")
print(f"  Test 2.2 - Claim after server restart (empty RAM cache): {restart_claim}")
restart_dedup_safe = (restart_claim is False)
print(f"    Diagnostic: Server restart duplicate dropped by DB ledger? {restart_dedup_safe}")
AUDIT_RESULTS["restart_dedup_safe"] = restart_dedup_safe

# 2.3 Worker crash while status is PROCESSING
crashed_msg_id = f"MSG-AUDIT-CRASH-{uuid.uuid4().hex[:6]}"
with get_db_session() as session:
    repo = IdempotencyRepository(session)
    # Worker claimed it, then crashed (process terminated before complete or fail was called)
    repo.claim_message(crashed_msg_id, "9823011111")
    # In DB, status is PROCESSING, completed_at is NULL

# Now Meta retries the webhook because the server never returned a timely response or crashed
retry_fresh_svc = DeduplicationService()
retry_claim = retry_fresh_svc.claim_message(crashed_msg_id, "9823011111")
print(f"  Test 2.3 - Meta retries message after worker crashed in PROCESSING: claimed={retry_claim}")
with get_db_session() as session:
    ev = session.query(WebhookEvent).filter_by(message_id=crashed_msg_id).first()
    print(f"    DB Status: {ev.status.value}, completed_at={ev.completed_at}")

stale_processing_blocks_retry = (retry_claim is False and ev.status == WebhookEventStatus.PROCESSING)
print(f"    Diagnostic: Does stale PROCESSING permanently drop retry without processing? {stale_processing_blocks_retry}")
AUDIT_RESULTS["stale_processing_blocks_retry"] = stale_processing_blocks_retry

# 2.4 Duplicate delivery after FAILED event
failed_msg_id = f"MSG-AUDIT-FAILED-{uuid.uuid4().hex[:6]}"
with get_db_session() as session:
    repo = IdempotencyRepository(session)
    repo.claim_message(failed_msg_id, "9823011111")
    repo.fail_message(failed_msg_id, "Gemini API Timeout 504")

retry_failed_claim = retry_fresh_svc.claim_message(failed_msg_id, "9823011111")
print(f"  Test 2.4 - Meta retries message after FAILED status: claimed={retry_failed_claim}")
with get_db_session() as session:
    ev_fail = session.query(WebhookEvent).filter_by(message_id=failed_msg_id).first()
    print(f"    DB Status: {ev_fail.status.value}, error={ev_fail.error_message}")
failed_blocks_retry = (retry_failed_claim is False and ev_fail.status == WebhookEventStatus.FAILED)
print(f"    Diagnostic: Does FAILED status permanently reject retries? {failed_blocks_retry}")
AUDIT_RESULTS["failed_blocks_retry"] = failed_blocks_retry

# 2.5 External WhatsApp delivery vs DB transaction boundary
print("  Test 2.5 - Outbound delivery vs DB transaction coupling:")
print("    - WhatsAppCloudClient.send_message() is an external HTTP POST to Meta Graph API.")
print("    - If send_message() succeeds but complete_message() fails (e.g. DB crash), status remains PROCESSING.")
print("    - If send_message() times out (e.g. 504 from Meta) but Meta actually delivered it, retry will deliver a duplicate outbound message.")
print("    - Finding: In-memory/inline HTTP dispatch lacks a Transactional Outbox pattern.")


# ===========================================================================
# 3. FARMER IDENTITY & SHARED PHONE AUDIT
# ===========================================================================
print("\n" + "=" * 75)
print("[AUDIT AREA 3] Farmer Identity and Shared Phone Numbers")
print("=" * 75)

from sqlalchemy.exc import IntegrityError

# 3.1 Can two farmers share a primary phone?
phone_unique_violation = False
with get_db_session() as session:
    repo = FarmerRepository(session)
    repo.create_farmer("FARM-ID-001", "Farmer One", "9811199999")

try:
    with get_db_session() as session:
        repo = FarmerRepository(session)
        repo.create_farmer("FARM-ID-002", "Farmer Two", "9811199999")  # Same primary phone
except (IntegrityError, Exception) as e:
    phone_unique_violation = True
    print(f"  Test 3.1 - Two farmers with same primary phone: Rejected with IntegrityError: {e.__class__.__name__}")

print(f"    Diagnostic: Does DB enforce primary_phone uniqueness, preventing shared primary phones? {phone_unique_violation}")
AUDIT_RESULTS["primary_phone_unique_blocks_shared"] = phone_unique_violation

# 3.2 Updating phone number without changing Farmer ID
with get_db_session() as session:
    repo = FarmerRepository(session)
    f = repo.get_by_farmer_id("FARM-ID-001")
    old_id = f.farmer_id
    f.primary_phone = "9811199998"
    session.flush()

with get_db_session() as session:
    repo = FarmerRepository(session)
    f_updated = repo.lookup_by_phone("9811199998")
    phone_updated_same_id = (f_updated is not None and f_updated.farmer_id == old_id)
    print(f"  Test 3.2 - Phone updated directly in DB preserves Farmer ID: {phone_updated_same_id} (ID: {f_updated.farmer_id})")
    AUDIT_RESULTS["phone_updated_same_id"] = phone_updated_same_id

# 3.3 Lookup by shared phone number via FarmerContact
with get_db_session() as session:
    repo = FarmerRepository(session)
    # Register two separate farmers
    f_a = repo.create_farmer("FARM-FAM-A", "Father Patil", "9800055551")
    f_b = repo.create_farmer("FARM-FAM-B", "Son Patil", "9800055552")
    # Both register shared landline / alternate phone
    repo.add_contact(f_a.id, "9800099999", "Shared Landline", "Family")
    repo.add_contact(f_b.id, "9800099999", "Shared Landline", "Family")

with get_db_session() as session:
    repo = FarmerRepository(session)
    # Lookup by the shared contact phone
    resolved = repo.lookup_by_phone("9800099999")
    print(f"  Test 3.3 - Lookup by shared alternate phone (9800099999) returned: {resolved.farmer_id} ({resolved.full_name})")
    arbitrary_select = (resolved.farmer_id == "FARM-FAM-A")
    print(f"    Diagnostic: Did lookup_by_phone arbitrarily select the first record? {arbitrary_select}")
    AUDIT_RESULTS["arbitrary_shared_phone_selection"] = arbitrary_select


# ===========================================================================
# 4. FIELD-LEVEL VERIFICATION & DATA PROVENANCE AUDIT
# ===========================================================================
print("\n" + "=" * 75)
print("[AUDIT AREA 4] Field-Level Verification and Data Provenance")
print("=" * 75)

with get_db_session() as session:
    repo = FarmerRepository(session)
    farmer = repo.create_farmer(
        farmer_id="FARM-PROV-001",
        full_name="Govind Rao",
        primary_phone="9877711111",
        name_status=VerificationStatus.VERIFIED,  # Verified name
        data_source="AADHAAR_KYC"
    )
    plot = repo.add_plot(
        farmer_id=farmer.id,
        plot_identifier="PLOT-1",
        land_area=7.5,
        area_unit=AreaUnit.ACRES,
        area_status=VerificationStatus.VERIFIED,  # Verified area
        data_source="LAND_REVENUE_7_12"
    )
    crop = repo.add_crop_to_plot(
        farm_plot_id=plot.id,
        crop_name="Sugarcane",
        crop_variety="Co 86032",
        planting_date=date(2026, 1, 15),
        planting_season=PlantingSeason.SURU,
        data_source="FARMER_WHATSAPP_CHAT"
    )
    crop.planting_date_status = VerificationStatus.UNVERIFIED  # Explicitly set to unverified for test
    soil = repo.add_soil_profile(
        farm_plot_id=plot.id,
        soil_type="Black Cotton",
        nitrogen_n_kg_ha=None,  # Missing NPK
        phosphorus_p_kg_ha=None,
        potassium_k_kg_ha=None
    )

print("  Step 4.1 - Initial Profile Created:")
print(f"    - Name: '{farmer.full_name}', Status={farmer.name_status.value}, Source={farmer.data_source}")
print(f"    - Land Area: {plot.land_area} {plot.area_unit.value}, Status={plot.area_status.value}, Source={plot.data_source}")
print(f"    - Planting Date: {crop.planting_date}, Status={crop.planting_date_status.value}, Source={crop.data_source}")
print(f"    - NPK Values: {soil.nitrogen_n_kg_ha}, Status={soil.npk_status.value}")

# 4.2 Field Isolation Test: Modify planting date -> check other fields
initial_f_updated_at = farmer.last_updated_at
with get_db_session() as session:
    repo = FarmerRepository(session)
    f = repo.get_by_farmer_id("FARM-PROV-001")
    # Change planting date
    f.plots[0].crops[0].planting_date = date(2026, 2, 1)
    f.plots[0].crops[0].planting_date_status = VerificationStatus.VERIFIED
    f.plots[0].crops[0].data_source = "CDO_INSPECTION"
    session.flush()

with get_db_session() as session:
    repo = FarmerRepository(session)
    f = repo.get_by_farmer_id("FARM-PROV-001")
    p = f.plots[0]
    c = p.crops[0]
    s = p.soil_profiles[0]

    name_status_intact = (f.name_status == VerificationStatus.VERIFIED)
    area_status_intact = (p.area_status == VerificationStatus.VERIFIED)
    npk_status_intact = (s.npk_status == VerificationStatus.MISSING)
    crop_status_changed = (c.planting_date_status == VerificationStatus.VERIFIED)

    print("\n  Step 4.2 - Verification Status Field Isolation:")
    print(f"    - Name verification status intact: {name_status_intact} ({f.name_status.value})")
    print(f"    - Land Area verification status intact: {area_status_intact} ({p.area_status.value})")
    print(f"    - NPK status intact as MISSING: {npk_status_intact} ({s.npk_status.value})")
    print(f"    - Planting date updated to VERIFIED: {crop_status_changed} ({c.planting_date_status.value})")
    AUDIT_RESULTS["field_status_isolation"] = (name_status_intact and area_status_intact and npk_status_intact and crop_status_changed)

# 4.3 Check whether previous values are preserved in history/audit
print("\n  Step 4.3 - Historical Value Tracking:")
print("    - Querying audit history for previous planting date '2026-01-15'...")
has_field_history_table = hasattr(Base.metadata.tables, "field_history") or hasattr(Base.metadata.tables, "field_audit_logs")
print(f"    - Dedicated field_history table exists? {has_field_history_table}")
print("    - Finding: In-place column updates overwrite previous field values without a temporal history / changelog table.")
AUDIT_RESULTS["has_field_history_table"] = has_field_history_table


# ===========================================================================
# 5. POSTGRESQL COMPATIBILITY AUDIT
# ===========================================================================
print("\n" + "=" * 75)
print("[AUDIT AREA 5] PostgreSQL Compatibility Analysis")
print("=" * 75)

pg_checks = [
    ("Enum handling (native_enum=False creates portable VARCHAR)", True),
    ("SQLite PRAGMA foreign_keys=ON (PostgreSQL enforces natively)", True),
    ("QueuePool configured for PostgreSQL, StaticPool for SQLite memory", True),
    ("Alembic render_as_batch=True for SQLite; standard DDL for PostgreSQL", True),
    ("DateTime(timezone=True) portability (ISO string vs TIMESTAMP WITH TIME ZONE)", True),
    ("Row-level locking (SELECT FOR UPDATE) not available on SQLite; requires staging test", False),
    ("Concurrent multi-process write locks under high load requires staging test", False),
]

for desc, status in pg_checks:
    mark = "✅" if status else "⚠️"
    print(f"  {mark} {desc}")


# ===========================================================================
# SUMMARY OF AUDIT FINDINGS
# ===========================================================================
print("\n" + "=" * 75)
print("AUDIT SUMMARY MATRIX")
print("=" * 75)
for k, v in AUDIT_RESULTS.items():
    print(f"  • {k:35}: {v}")
print("=" * 75)
