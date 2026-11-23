"""
Farmer Domain Service.
Provides high-level lookup, synchronization, and backward-compatible model
conversion between the relational database layer and the AI agent/gateway.
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from sqlalchemy.orm import Session

from database.connection import get_db_session
from database.repositories import FarmerRepository, CDORepository
from database.models import Farmer, FarmPlot, CropRecord, SoilProfile
from database.enums import VerificationStatus, AreaUnit, PlantingSeason

logger = logging.getLogger("FarmerService")


class FarmerService:
    """Orchestrates farmer profile queries and updates using the relational database."""

    def __init__(self, session: Optional[Session] = None):
        self._external_session = session

    def _get_session_context(self):
        """Helper to manage external vs new database session."""
        if self._external_session:
            class DummyContext:
                def __init__(self, s): self.s = s
                def __enter__(self): return self.s
                def __exit__(self, *args): pass
            return DummyContext(self._external_session)
        return get_db_session()

    def get_farmer_profile_by_phone(self, phone_number: str) -> Optional["FarmerProfile"]:
        """
        Looks up registered farmer by phone and returns a legacy FarmerProfile
        instance for immediate use in the FarmerAgent.
        """
        from agent.farmer_agent import FarmerProfile
        with self._get_session_context() as session:
            repo = FarmerRepository(session)
            farmer = repo.lookup_by_phone(phone_number)
            if not farmer:
                return None

            district_name = farmer.district.name if farmer.district else "General"
            
            # Extract first active plot details if available
            crop_name = "General"
            soil_name = "Black Cotton"
            farm_size_str = "3 Acres"

            if farmer.plots:
                primary_plot = farmer.plots[0]
                farm_size_str = f"{primary_plot.land_area} {primary_plot.area_unit.value.capitalize()}"
                if primary_plot.crops:
                    crop_name = primary_plot.crops[0].crop_name
                if primary_plot.soil_profiles:
                    soil_name = primary_plot.soil_profiles[0].soil_type or "Medium Black"

            return FarmerProfile(
                name=farmer.full_name,
                phone=farmer.primary_phone,
                district=district_name,
                crop=crop_name,
                soil_type=soil_name,
                farm_size=farm_size_str
            )

    def get_farmer_submission(self, phone_number: str) -> Optional["FarmerFormSubmission"]:
        """
        Looks up registered farmer and returns a FarmerFormSubmission model
        for full backward compatibility with Google Form automation.
        """
        from form_automation.models import FarmerFormSubmission
        with self._get_session_context() as session:
            repo = FarmerRepository(session)
            farmer = repo.lookup_by_phone(phone_number)
            if not farmer:
                return None

            district_name = farmer.district.name if farmer.district else "General"
            tehsil_name = farmer.tehsil or ""
            farm_size = 3.0
            crop_name = "General"
            soil_name = "Black Cotton"
            crop_stage = "Vegetative"
            drip = True

            if farmer.plots:
                plot = farmer.plots[0]
                farm_size = float(plot.land_area)
                drip = bool(plot.has_drip_irrigation) if plot.has_drip_irrigation is not None else True
                if plot.crops:
                    crop = plot.crops[0]
                    crop_name = crop.crop_name
                    crop_stage = crop.growth_stage or "Vegetative"
                if plot.soil_profiles:
                    soil = plot.soil_profiles[0]
                    soil_name = soil.soil_type or "Black Cotton"

            return FarmerFormSubmission(
                farmer_name=farmer.full_name,
                phone_number=farmer.primary_phone,
                district=district_name,
                area_tehsil=tehsil_name,
                farm_size_acres=farm_size,
                crop_grown=crop_name,
                soil_type=soil_name,
                sowing_stage=crop_stage,
                has_drip_irrigation=drip,
                submission_timestamp=farmer.created_at or datetime.now()
            )

    def get_all_farmer_submissions(self) -> List["FarmerFormSubmission"]:
        """Returns all registered farmers formatted as FarmerFormSubmission objects."""
        from form_automation.models import FarmerFormSubmission
        submissions = []
        with self._get_session_context() as session:
            repo = FarmerRepository(session)
            farmers = repo.list_all(limit=500)
            for f in farmers:
                district_name = f.district.name if f.district else "General"
                tehsil_name = f.tehsil or ""
                farm_size = 3.0
                crop_name = "General"
                soil_name = "Black Cotton"
                crop_stage = "Vegetative"
                drip = True

                if f.plots:
                    plot = f.plots[0]
                    farm_size = float(plot.land_area)
                    drip = bool(plot.has_drip_irrigation) if plot.has_drip_irrigation is not None else True
                    if plot.crops:
                        crop = plot.crops[0]
                        crop_name = crop.crop_name
                        crop_stage = crop.growth_stage or "Vegetative"
                    if plot.soil_profiles:
                        soil = plot.soil_profiles[0]
                        soil_name = soil.soil_type or "Black Cotton"

                submissions.append(FarmerFormSubmission(
                    farmer_name=f.full_name,
                    phone_number=f.primary_phone,
                    district=district_name,
                    area_tehsil=tehsil_name,
                    farm_size_acres=farm_size,
                    crop_grown=crop_name,
                    soil_type=soil_name,
                    sowing_stage=crop_stage,
                    has_drip_irrigation=drip,
                    submission_timestamp=f.created_at or datetime.now()
                ))
        return submissions

    def upsert_from_form_submission(self, submission: "FarmerFormSubmission") -> Farmer:
        """
        Synchronizes a Google Form submission directly into the relational database.
        If the farmer exists, updates their profile, plot, and crop records.
        If not, creates a new farmer record.
        """
        with self._get_session_context() as session:
            farmer_repo = FarmerRepository(session)
            cdo_repo = CDORepository(session)

            clean_phone = submission.clean_phone()
            district = cdo_repo.get_or_create_district(submission.district)

            existing_farmer = farmer_repo.lookup_by_phone(clean_phone)
            if existing_farmer:
                # Update existing profile
                existing_farmer.full_name = submission.farmer_name
                existing_farmer.district_id = district.id
                existing_farmer.tehsil = submission.area_tehsil
                existing_farmer.data_source = "GOOGLE_FORM"
                existing_farmer.supplied_by = "FARMER"
                existing_farmer.last_updated_at = datetime.now()

                # Update or add plot
                if existing_farmer.plots:
                    plot = existing_farmer.plots[0]
                    plot.land_area = submission.farm_size_acres
                    plot.has_drip_irrigation = submission.has_drip_irrigation
                    plot.data_source = "GOOGLE_FORM"
                    plot.last_updated_at = datetime.now()

                    # Update crop
                    if plot.crops:
                        crop = plot.crops[0]
                        crop.crop_name = submission.crop_grown
                        crop.growth_stage = submission.sowing_stage
                        crop.last_updated_at = datetime.now()
                    else:
                        farmer_repo.add_crop_to_plot(
                            farm_plot_id=plot.id,
                            crop_name=submission.crop_grown,
                            growth_stage=submission.sowing_stage,
                            data_source="GOOGLE_FORM",
                            supplied_by="FARMER"
                        )

                    # Update soil
                    if plot.soil_profiles:
                        soil = plot.soil_profiles[0]
                        soil.soil_type = submission.soil_type
                        soil.last_updated_at = datetime.now()
                    else:
                        farmer_repo.add_soil_profile(
                            farm_plot_id=plot.id,
                            soil_type=submission.soil_type,
                            data_source="GOOGLE_FORM",
                            supplied_by="FARMER"
                        )
                else:
                    plot = farmer_repo.add_plot(
                        farmer_id=existing_farmer.id,
                        plot_identifier="PLOT-1",
                        land_area=submission.farm_size_acres,
                        has_drip_irrigation=submission.has_drip_irrigation,
                        data_source="GOOGLE_FORM",
                        supplied_by="FARMER"
                    )
                    farmer_repo.add_crop_to_plot(
                        farm_plot_id=plot.id,
                        crop_name=submission.crop_grown,
                        growth_stage=submission.sowing_stage,
                        data_source="GOOGLE_FORM",
                        supplied_by="FARMER"
                    )
                    farmer_repo.add_soil_profile(
                        farm_plot_id=plot.id,
                        soil_type=submission.soil_type,
                        data_source="GOOGLE_FORM",
                        supplied_by="FARMER"
                    )
                session.flush()
                return existing_farmer

            else:
                # Create brand new farmer record
                farmer_id = farmer_repo.generate_next_farmer_id()
                new_farmer = farmer_repo.create_farmer(
                    farmer_id=farmer_id,
                    full_name=submission.farmer_name,
                    primary_phone=clean_phone,
                    tehsil=submission.area_tehsil,
                    district_id=district.id,
                    data_source="GOOGLE_FORM",
                    supplied_by="FARMER"
                )
                plot = farmer_repo.add_plot(
                    farmer_id=new_farmer.id,
                    plot_identifier="PLOT-1",
                    land_area=submission.farm_size_acres,
                    has_drip_irrigation=submission.has_drip_irrigation,
                    data_source="GOOGLE_FORM",
                    supplied_by="FARMER"
                )
                farmer_repo.add_crop_to_plot(
                    farm_plot_id=plot.id,
                    crop_name=submission.crop_grown,
                    growth_stage=submission.sowing_stage,
                    data_source="GOOGLE_FORM",
                    supplied_by="FARMER"
                )
                farmer_repo.add_soil_profile(
                    farm_plot_id=plot.id,
                    soil_type=submission.soil_type,
                    data_source="GOOGLE_FORM",
                    supplied_by="FARMER"
                )
                session.flush()
                return new_farmer

    def count_farmers(self) -> int:
        """Returns total registered farmer count."""
        with self._get_session_context() as session:
            repo = FarmerRepository(session)
            return repo.count()
