"""
Excel Sync & Farmer Profile Manager.
Syncs Google Form responses stored in Excel/Sheets, maintaining an instant
phone-number-to-profile lookup for WhatsApp personalizations.
"""

from pathlib import Path
from typing import Optional, Dict, List
import pandas as pd
from .models import FarmerFormSubmission

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_EXCEL_PATH = BASE_DIR / "data" / "farmer_profiles.xlsx"

class ExcelProfileManager:
    """
    Manages reading, caching, and updating farmer profiles in Excel.
    Provides fast O(1) in-memory phone lookups for the WhatsApp agent.
    """

    def __init__(self, excel_path: Optional[Path] = None):
        self.excel_path = Path(excel_path or DEFAULT_EXCEL_PATH)
        self.excel_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, FarmerFormSubmission] = {}
        self.ensure_sample_excel_exists()
        self.reload()

    def reload(self) -> int:
        """Reads the Excel sheet and builds the in-memory phone lookup cache."""
        if not self.excel_path.exists():
            return 0

        df = pd.read_excel(self.excel_path)
        self._cache.clear()

        for _, row in df.iterrows():
            phone = str(row.get("Phone Number", "")).strip()
            digits = "".join(filter(str.isdigit, phone))
            clean_phone = digits[-10:] if len(digits) >= 10 else digits

            if not clean_phone:
                continue

            submission = FarmerFormSubmission(
                farmer_name=str(row.get("Farmer Name", "Kisan Bhai")).strip(),
                phone_number=clean_phone,
                district=str(row.get("District", "General")).strip(),
                area_tehsil=str(row.get("Tehsil / Taluka", "")).strip(),
                farm_size_acres=float(row.get("Farm Size (Acres)", 3.0)),
                crop_grown=str(row.get("Crop Grown", "General")).strip(),
                soil_type=str(row.get("Soil Type", "Black Cotton")).strip(),
                sowing_stage=str(row.get("Crop Stage", "Vegetative")).strip(),
                has_drip_irrigation=bool(row.get("Drip Irrigation", True))
            )
            self._cache[clean_phone] = submission

        return len(self._cache)

    def lookup_farmer(self, phone_number: str) -> Optional[FarmerFormSubmission]:
        """Finds a farmer's registered profile by their 10-digit mobile number."""
        if not phone_number:
            return None
        digits = "".join(filter(str.isdigit, phone_number))
        clean_key = digits[-10:] if len(digits) >= 10 else digits
        return self._cache.get(clean_key)

    def record_submission(self, submission: FarmerFormSubmission) -> None:
        """Appends a new Google Form submission to the Excel sheet and updates cache."""
        clean_phone = submission.clean_phone()
        self._cache[clean_phone] = submission

        # Load existing or create new DataFrame
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

        # Remove existing record if phone already present to update cleanly
        if "Phone Number" in df.columns:
            df = df[df["Phone Number"] != clean_phone]
        
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        df.to_excel(self.excel_path, index=False)

    def get_all_farmers(self) -> List[FarmerFormSubmission]:
        """Returns all registered farmers."""
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
