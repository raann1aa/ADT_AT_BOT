"""
Excel Sync & Farmer Profile Manager (Relational Database-Integrated).
Syncs Google Form responses stored in Excel/Sheets with the relational database layer,
maintaining an instant phone-number-to-profile lookup for WhatsApp personalizations.
"""

from pathlib import Path
from typing import Optional, Dict, List
import logging
import pandas as pd
from .models import FarmerFormSubmission

from database.connection import init_db

logger = logging.getLogger("ExcelProfileManager")

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_EXCEL_PATH = BASE_DIR / "data" / "farmer_profiles.xlsx"


class ExcelProfileManager:
    """
    Manages reading, caching, and updating farmer profiles.
    Synchronizes between legacy Excel workbooks and the relational database,
    providing fast O(1) in-memory phone lookups for the WhatsApp agent.
    """

    def __init__(self, excel_path: Optional[Path] = None):
        self.excel_path = Path(excel_path or DEFAULT_EXCEL_PATH)
        self.excel_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, FarmerFormSubmission] = {}
        # Lazy imports to break circular dependency chain
        from database.services.farmer_service import FarmerService
        from database.services.excel_migration_service import ExcelMigrationService
        self.farmer_service = FarmerService()
        self.migration_service = ExcelMigrationService(excel_path=self.excel_path)
        
        # Ensure tables exist
        init_db()
        self.ensure_sample_excel_exists()
        self.reload()

    def reload(self) -> int:
        """
        Builds the in-memory phone lookup cache.
        Loads authoritative records from the relational database.
        If the database has zero records, automatically migrates from Excel.
        """
        self._cache.clear()

        # Check DB farmer count
        db_count = self.farmer_service.count_farmers()
        if db_count == 0 and self.excel_path.exists():
            logger.info("Database is empty. Ingesting records from Excel workbook...")
            self.migration_service.run_migration()

        # Populate cache from database
        db_submissions = self.farmer_service.get_all_farmer_submissions()
        for sub in db_submissions:
            self._cache[sub.clean_phone()] = sub

        return len(self._cache)

    def lookup_farmer(self, phone_number: str) -> Optional[FarmerFormSubmission]:
        """Finds a farmer's registered profile by their 10-digit mobile number."""
        if not phone_number:
            return None
        digits = "".join(filter(str.isdigit, phone_number))
        clean_key = digits[-10:] if len(digits) >= 10 else digits
        
        # Check fast cache first
        if clean_key in self._cache:
            return self._cache[clean_key]

        # Query database directly if not yet in cache
        db_sub = self.farmer_service.get_farmer_submission(clean_key)
        if db_sub:
            self._cache[clean_key] = db_sub
            return db_sub

        return None

    def record_submission(self, submission: FarmerFormSubmission) -> None:
        """
        Persists a new Google Form submission into both the relational database
        and the Excel sheet, keeping cache and storage in sync.
        """
        clean_phone = submission.clean_phone()
        self._cache[clean_phone] = submission

        # 1. Persist to relational database
        try:
            self.farmer_service.upsert_from_form_submission(submission)
            logger.info(f"Persisted farmer submission to database for: {submission.farmer_name} ({clean_phone})")
        except Exception as e:
            logger.error(f"Failed to persist submission to database: {e}")

        # 2. Append/Update Excel spreadsheet for external compatibility
        try:
            if self.excel_path.exists():
                df = pd.read_excel(self.excel_path, dtype={"Phone Number": str})
            else:
                df = pd.DataFrame()

            if "Phone Number" in df.columns:
                df["Phone Number"] = df["Phone Number"].astype(str)

            new_row = {
                "Farmer Name": submission.farmer_name,
                "Phone Number": clean_phone,
                "District": submission.district,
                "Tehsil / Taluka": submission.area_tehsil,
                "Farm Size (Acres)": submission.farm_size_acres,
                "Crop Grown": submission.crop_grown,
                "Soil Type": submission.soil_type,
                "Crop Stage": submission.sowing_stage,
                "Drip Irrigation": "Yes" if submission.has_drip_irrigation else "No",
                "Submission Date": submission.submission_timestamp.strftime("%Y-%m-%d %H:%M")
            }

            if "Phone Number" in df.columns:
                df = df[df["Phone Number"] != clean_phone]

            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            df.to_excel(self.excel_path, index=False)
        except Exception as e:
            logger.error(f"Failed to update Excel file: {e}")

    def get_all_farmers(self) -> List[FarmerFormSubmission]:
        """Returns all registered farmers."""
        if not self._cache:
            self.reload()
        return list(self._cache.values())

    def ensure_sample_excel_exists(self) -> None:
        """Generates a sample farmer profile Excel workbook if one does not already exist."""
        if self.excel_path.exists():
            return

        sample_data = [
            {
                "Farmer Name": "Ramesh Patil",
                "Phone Number": "9823011111",
                "District": "Nashik",
                "Tehsil / Taluka": "Niphad",
                "Farm Size (Acres)": 4.5,
                "Crop Grown": "Onion",
                "Soil Type": "Black Cotton",
                "Crop Stage": "Bulb Expansion",
                "Drip Irrigation": "Yes",
                "Submission Date": "2026-11-15 09:30"
            },
            {
                "Farmer Name": "Dnyaneshwar Shinde",
                "Phone Number": "9823022222",
                "District": "Nashik",
                "Tehsil / Taluka": "Yeola",
                "Farm Size (Acres)": 6.0,
                "Crop Grown": "Onion",
                "Soil Type": "Clay Loam",
                "Crop Stage": "Harvesting / Storage",
                "Drip Irrigation": "Yes",
                "Submission Date": "2026-11-15 10:15"
            },
            {
                "Farmer Name": "Suresh Yadav",
                "Phone Number": "9876533333",
                "District": "Indore",
                "Tehsil / Taluka": "Sanwer",
                "Farm Size (Acres)": 5.0,
                "Crop Grown": "Soybean",
                "Soil Type": "Medium Black",
                "Crop Stage": "Pod Filling",
                "Drip Irrigation": "No",
                "Submission Date": "2026-11-15 11:00"
            },
            {
                "Farmer Name": "Harpreet Singh",
                "Phone Number": "9814044444",
                "District": "Ludhiana",
                "Tehsil / Taluka": "Jagraon",
                "Farm Size (Acres)": 10.0,
                "Crop Grown": "Wheat",
                "Soil Type": "Alluvial Loam",
                "Crop Stage": "Crown Root Initiation (CRI)",
                "Drip Irrigation": "No",
                "Submission Date": "2026-11-15 11:45"
            },
            {
                "Farmer Name": "Baldev Singh",
                "Phone Number": "9814055555",
                "District": "Ludhiana",
                "Tehsil / Taluka": "Samrala",
                "Farm Size (Acres)": 8.0,
                "Crop Grown": "Wheat",
                "Soil Type": "Alluvial",
                "Crop Stage": "Tillering",
                "Drip Irrigation": "No",
                "Submission Date": "2026-11-15 12:10"
            },
            {
                "Farmer Name": "Popat Rao",
                "Phone Number": "9890066666",
                "District": "Nashik",
                "Tehsil / Taluka": "Malegaon",
                "Farm Size (Acres)": 3.5,
                "Crop Grown": "Cotton",
                "Soil Type": "Black Cotton",
                "Crop Stage": "Boll Formation",
                "Drip Irrigation": "Yes",
                "Submission Date": "2026-11-15 13:00"
            }
        ]

        df = pd.DataFrame(sample_data)
        df.to_excel(self.excel_path, index=False)
