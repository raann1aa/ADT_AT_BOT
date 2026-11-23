"""
Excel Migration and Two-Way Synchronization Service.
Safely migrates legacy farmer profile Excel spreadsheets into the relational database
with automatic timestamped backups, full idempotency, and detailed migration reporting.
"""

import os
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
import pandas as pd

from database.connection import get_db_session, BASE_DIR
from database.repositories import FarmerRepository, CDORepository
from database.models import Farmer, FarmPlot, CropRecord, SoilProfile, District
from database.enums import VerificationStatus, AreaUnit, PlantingSeason

logger = logging.getLogger("ExcelMigrationService")

DEFAULT_EXCEL_PATH = BASE_DIR / "data" / "farmer_profiles.xlsx"
DEFAULT_BACKUP_DIR = BASE_DIR / "data" / "backups"


class ExcelMigrationService:
    """Handles backup, migration, verification, and reverse export for Excel profiles."""

    def __init__(self, excel_path: Optional[Path] = None, backup_dir: Optional[Path] = None):
        self.excel_path = Path(excel_path or DEFAULT_EXCEL_PATH)
        self.backup_dir = Path(backup_dir or DEFAULT_BACKUP_DIR)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_timestamped_backup(self) -> Path:
        """
        Creates an immutable, timestamped copy of the Excel file before any migration or modification.
        Example: data/backups/farmer_profiles_backup_20261123_104500.xlsx
        """
        if not self.excel_path.exists():
            raise FileNotFoundError(f"Source Excel file not found for backup: {self.excel_path}")

        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{self.excel_path.stem}_backup_{timestamp_str}{self.excel_path.suffix}"
        backup_path = self.backup_dir / backup_filename

        shutil.copy2(self.excel_path, backup_path)
        logger.info(f"Created timestamped backup at: {backup_path}")
        return backup_path

    def run_migration(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Performs safe, idempotent ingestion of Excel data into the relational database.
        Returns a comprehensive report detailing total scanned, created, updated, and skipped rows.
        """
        if not self.excel_path.exists():
            return {
                "status": "error",
                "message": f"Source file {self.excel_path} does not exist.",
                "total_scanned": 0,
                "created_count": 0,
                "updated_count": 0,
                "skipped_count": 0,
                "error_count": 0,
                "errors": [f"File not found: {self.excel_path}"]
            }

        # 1. Create mandatory backup before processing
        backup_file = self.create_timestamped_backup()

        df = pd.read_excel(self.excel_path)
        total_scanned = len(df)
        created_count = 0
        updated_count = 0
        skipped_count = 0
        error_count = 0
        errors = []

        logger.info(f"Starting Excel migration for {total_scanned} records from {self.excel_path}...")

        with get_db_session() as session:
            farmer_repo = FarmerRepository(session)
            cdo_repo = CDORepository(session)

            for index, row in df.iterrows():
                row_idx = index + 2  # Excel 1-based row header offset
                try:
                    # Clean and validate phone number
                    raw_phone = str(row.get("Phone Number", "")).strip()
                    clean_phone = farmer_repo.normalize_phone(raw_phone)
                    if not clean_phone or len(clean_phone) < 10:
                        skipped_count += 1
                        logger.warning(f"Row {row_idx}: Invalid phone '{raw_phone}'. Skipping.")
                        continue

                    # Extract fields with safe defaults
                    raw_name = str(row.get("Farmer Name", "")).strip()
                    farmer_name = raw_name if raw_name and raw_name.lower() != "nan" else "किसान भाई"
                    
                    raw_district = str(row.get("District", "")).strip()
                    district_name = raw_district if raw_district and raw_district.lower() != "nan" else "General"

                    raw_tehsil = str(row.get("Tehsil / Taluka", "")).strip()
                    tehsil_name = raw_tehsil if raw_tehsil and raw_tehsil.lower() != "nan" else None

                    raw_crop = str(row.get("Crop Grown", "")).strip()
                    crop_name = raw_crop if raw_crop and raw_crop.lower() != "nan" else "General"

                    raw_soil = str(row.get("Soil Type", "")).strip()
                    soil_name = raw_soil if raw_soil and raw_soil.lower() != "nan" else "Black Cotton"

                    raw_stage = str(row.get("Crop Stage", "")).strip()
                    growth_stage = raw_stage if raw_stage and raw_stage.lower() != "nan" else "Vegetative"

                    try:
                        farm_size = float(row.get("Farm Size (Acres)", 3.0))
                    except (ValueError, TypeError):
                        farm_size = 3.0

                    raw_drip = str(row.get("Drip Irrigation", "")).strip().lower()
                    has_drip = raw_drip in ("yes", "true", "1", "y")

                    # Parse submission timestamp if present
                    submission_date_val = row.get("Submission Date")
                    created_timestamp = None
                    if pd.notna(submission_date_val):
                        try:
                            if isinstance(submission_date_val, datetime):
                                created_timestamp = submission_date_val
                            else:
                                created_timestamp = pd.to_datetime(str(submission_date_val)).to_pydatetime()
                        except Exception:
                            created_timestamp = datetime.now()

                    # Find or create District
                    district = cdo_repo.get_or_create_district(district_name)

                    # Check for existing farmer by phone (Idempotency check)
                    existing_farmer = farmer_repo.lookup_by_phone(clean_phone)

                    if existing_farmer:
                        # Update existing farmer
                        existing_farmer.full_name = farmer_name
                        existing_farmer.district_id = district.id
                        if tehsil_name:
                            existing_farmer.tehsil = tehsil_name
                        existing_farmer.data_source = "EXCEL_MIGRATION"
                        existing_farmer.last_updated_at = datetime.now()

                        # Update or create plot
                        if existing_farmer.plots:
                            plot = existing_farmer.plots[0]
                            plot.land_area = farm_size
                            plot.has_drip_irrigation = has_drip
                            plot.last_updated_at = datetime.now()

                            if plot.crops:
                                crop = plot.crops[0]
                                crop.crop_name = crop_name
                                crop.growth_stage = growth_stage
                                crop.last_updated_at = datetime.now()
                            else:
                                farmer_repo.add_crop_to_plot(
                                    farm_plot_id=plot.id,
                                    crop_name=crop_name,
                                    growth_stage=growth_stage,
                                    crop_status=VerificationStatus.UNVERIFIED,
                                    data_source="EXCEL_MIGRATION"
                                )

                            if plot.soil_profiles:
                                soil = plot.soil_profiles[0]
                                soil.soil_type = soil_name
                                soil.last_updated_at = datetime.now()
                            else:
                                farmer_repo.add_soil_profile(
                                    farm_plot_id=plot.id,
                                    soil_type=soil_name,
                                    soil_type_status=VerificationStatus.UNVERIFIED,
                                    data_source="EXCEL_MIGRATION"
                                )
                        else:
                            plot = farmer_repo.add_plot(
                                farmer_id=existing_farmer.id,
                                plot_identifier="PLOT-1",
                                land_area=farm_size,
                                area_unit=AreaUnit.ACRES,
                                has_drip_irrigation=has_drip,
                                area_status=VerificationStatus.UNVERIFIED,
                                data_source="EXCEL_MIGRATION"
                            )
                            farmer_repo.add_crop_to_plot(
                                farm_plot_id=plot.id,
                                crop_name=crop_name,
                                growth_stage=growth_stage,
                                crop_status=VerificationStatus.UNVERIFIED,
                                data_source="EXCEL_MIGRATION"
                            )
                            farmer_repo.add_soil_profile(
                                farm_plot_id=plot.id,
                                soil_type=soil_name,
                                soil_type_status=VerificationStatus.UNVERIFIED,
                                data_source="EXCEL_MIGRATION"
                            )

                        updated_count += 1

                    else:
                        # Create new Farmer record
                        farmer_id = farmer_repo.generate_next_farmer_id()
                        new_farmer = farmer_repo.create_farmer(
                            farmer_id=farmer_id,
                            full_name=farmer_name,
                            primary_phone=clean_phone,
                            tehsil=tehsil_name,
                            district_id=district.id,
                            preferred_language="mr",
                            name_status=VerificationStatus.UNVERIFIED,
                            data_source="EXCEL_MIGRATION",
                            supplied_by="SYSTEM"
                        )
                        if created_timestamp:
                            new_farmer.created_at = created_timestamp

                        # Create Plot
                        plot = farmer_repo.add_plot(
                            farmer_id=new_farmer.id,
                            plot_identifier="PLOT-1",
                            land_area=farm_size,
                            area_unit=AreaUnit.ACRES,
                            has_drip_irrigation=has_drip,
                            area_status=VerificationStatus.UNVERIFIED,
                            data_source="EXCEL_MIGRATION",
                            supplied_by="SYSTEM"
                        )

                        # Create Crop Record
                        farmer_repo.add_crop_to_plot(
                            farm_plot_id=plot.id,
                            crop_name=crop_name,
                            growth_stage=growth_stage,
                            crop_status=VerificationStatus.UNVERIFIED,
                            data_source="EXCEL_MIGRATION",
                            supplied_by="SYSTEM"
                        )

                        # Create Soil Profile
                        farmer_repo.add_soil_profile(
                            farm_plot_id=plot.id,
                            soil_type=soil_name,
                            soil_type_status=VerificationStatus.UNVERIFIED,
                            data_source="EXCEL_MIGRATION",
                            supplied_by="SYSTEM"
                        )

                        created_count += 1

                except Exception as e:
                    error_count += 1
                    err_msg = f"Row {row_idx} error: {str(e)}"
                    errors.append(err_msg)
                    logger.error(err_msg)

            if dry_run:
                session.rollback()
                logger.info("Dry-run requested: database changes rolled back.")
            else:
                session.commit()
                logger.info("Excel migration transaction committed.")

        return {
            "status": "success" if error_count == 0 else "completed_with_errors",
            "backup_file": str(backup_file),
            "total_scanned": total_scanned,
            "created_count": created_count,
            "updated_count": updated_count,
            "skipped_count": skipped_count,
            "error_count": error_count,
            "errors": errors
        }

    def export_database_to_excel(self, output_path: Optional[Path] = None) -> Path:
        """
        Exports all farmer profiles in the relational database back into an Excel sheet
        matching the exact schema of data/farmer_profiles.xlsx for full two-way compatibility.
        """
        target_path = Path(output_path or self.excel_path)
        rows = []

        with get_db_session() as session:
            farmer_repo = FarmerRepository(session)
            farmers = farmer_repo.list_all(limit=1000)

            for f in farmers:
                district_name = f.district.name if f.district else "General"
                tehsil_name = f.tehsil or ""
                farm_size = 3.0
                crop_name = "General"
                soil_name = "Black Cotton"
                crop_stage = "Vegetative"
                drip = "Yes"
                sub_date = f.created_at.strftime("%Y-%m-%d %H:%M") if f.created_at else datetime.now().strftime("%Y-%m-%d %H:%M")

                if f.plots:
                    plot = f.plots[0]
                    farm_size = float(plot.land_area)
                    drip = "Yes" if plot.has_drip_irrigation else "No"
                    if plot.crops:
                        crop = plot.crops[0]
                        crop_name = crop.crop_name
                        crop_stage = crop.growth_stage or "Vegetative"
                    if plot.soil_profiles:
                        soil = plot.soil_profiles[0]
                        soil_name = soil.soil_type or "Black Cotton"

                rows.append({
                    "Farmer Name": f.full_name,
                    "Phone Number": f.primary_phone,
                    "District": district_name,
                    "Tehsil / Taluka": tehsil_name,
                    "Farm Size (Acres)": farm_size,
                    "Crop Grown": crop_name,
                    "Soil Type": soil_name,
                    "Crop Stage": crop_stage,
                    "Drip Irrigation": drip,
                    "Submission Date": sub_date
                })

        df = pd.DataFrame(rows)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_excel(target_path, index=False)
        logger.info(f"Exported {len(rows)} farmer records to {target_path}")
        return target_path
