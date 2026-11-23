"""
Farmer Repository.
Handles CRUD, eager loading, phone normalization, multi-plot associations,
and field verification status tracking for agricultural producers.
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, date

from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import select, func, or_

from database.models import (
    Farmer, FarmerContact, FarmPlot, CropRecord, SoilProfile, District, Division, Factory, CDO
)
from database.enums import VerificationStatus, PlantingSeason, AreaUnit

logger = logging.getLogger("FarmerRepository")


class FarmerRepository:
    """Data access repository for Farmers and their agricultural holdings."""

    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def normalize_phone(phone: str) -> str:
        """
        Normalizes phone number to standard 10-digit Indian mobile format.
        Strips country codes, whitespaces, plus signs, and leading zeros.
        """
        if not phone:
            return ""
        digits = "".join(filter(str.isdigit, str(phone)))
        if len(digits) >= 10:
            return digits[-10:]
        return digits

    def get_by_id(self, farmer_id: int) -> Optional[Farmer]:
        """Fetch farmer by internal database primary key."""
        stmt = (
            select(Farmer)
            .options(
                joinedload(Farmer.district),
                joinedload(Farmer.division),
                joinedload(Farmer.factory),
                joinedload(Farmer.assigned_cdo),
                selectinload(Farmer.contacts),
                selectinload(Farmer.plots).selectinload(FarmPlot.crops),
                selectinload(Farmer.plots).selectinload(FarmPlot.soil_profiles),
            )
            .where(Farmer.id == farmer_id)
        )
        return self.session.scalars(stmt).first()

    def get_by_farmer_id(self, farmer_code: str) -> Optional[Farmer]:
        """Fetch farmer by stable business identifier (e.g. 'FARM-00001')."""
        stmt = (
            select(Farmer)
            .options(
                joinedload(Farmer.district),
                joinedload(Farmer.division),
                joinedload(Farmer.factory),
                joinedload(Farmer.assigned_cdo),
                selectinload(Farmer.contacts),
                selectinload(Farmer.plots).selectinload(FarmPlot.crops),
                selectinload(Farmer.plots).selectinload(FarmPlot.soil_profiles),
            )
            .where(Farmer.farmer_id == farmer_code)
        )
        return self.session.scalars(stmt).first()

    def lookup_by_phone(self, raw_phone: str) -> Optional[Farmer]:
        """
        Looks up a registered farmer by mobile number.
        Searches both primary phone and alternate contact records.
        """
        clean_phone = self.normalize_phone(raw_phone)
        if not clean_phone:
            return None

        # 1. Search primary phone
        stmt = (
            select(Farmer)
            .options(
                joinedload(Farmer.district),
                joinedload(Farmer.division),
                joinedload(Farmer.factory),
                joinedload(Farmer.assigned_cdo),
                selectinload(Farmer.contacts),
                selectinload(Farmer.plots).selectinload(FarmPlot.crops),
                selectinload(Farmer.plots).selectinload(FarmPlot.soil_profiles),
            )
            .where(Farmer.primary_phone == clean_phone)
        )
        farmer = self.session.scalars(stmt).first()
        if farmer:
            return farmer

        # 2. Search alternate contacts
        contact_stmt = (
            select(FarmerContact)
            .where(FarmerContact.phone_number == clean_phone)
        )
        contact = self.session.scalars(contact_stmt).first()
        if contact and contact.farmer_id:
            return self.get_by_id(contact.farmer_id)

        return None

    def create_farmer(
        self,
        farmer_id: str,
        full_name: str,
        primary_phone: str,
        alternate_phone: Optional[str] = None,
        village: Optional[str] = None,
        tehsil: Optional[str] = None,
        district_id: Optional[int] = None,
        division_id: Optional[int] = None,
        factory_id: Optional[int] = None,
        assigned_cdo_id: Optional[int] = None,
        preferred_language: str = "mr",
        name_status: VerificationStatus = VerificationStatus.UNVERIFIED,
        data_source: str = "USER_INPUT",
        supplied_by: str = "SYSTEM"
    ) -> Farmer:
        """Creates a new farmer master record."""
        clean_phone = self.normalize_phone(primary_phone)
        farmer = Farmer(
            farmer_id=farmer_id,
            full_name=full_name.strip(),
            primary_phone=clean_phone,
            alternate_phone=self.normalize_phone(alternate_phone) if alternate_phone else None,
            village=village.strip() if village else None,
            tehsil=tehsil.strip() if tehsil else None,
            district_id=district_id,
            division_id=division_id,
            factory_id=factory_id,
            assigned_cdo_id=assigned_cdo_id,
            preferred_language=preferred_language,
            name_status=name_status,
            village_status=VerificationStatus.VERIFIED if village else VerificationStatus.MISSING,
            tehsil_status=VerificationStatus.VERIFIED if tehsil else VerificationStatus.MISSING,
            data_source=data_source,
            supplied_by=supplied_by
        )
        self.session.add(farmer)
        self.session.flush()
        return farmer

    def add_plot(
        self,
        farmer_id: int,
        plot_identifier: str,
        land_area: float,
        area_unit: AreaUnit = AreaUnit.ACRES,
        has_drip_irrigation: Optional[bool] = None,
        water_source: Optional[str] = None,
        village: Optional[str] = None,
        area_status: VerificationStatus = VerificationStatus.UNVERIFIED,
        data_source: str = "EXCEL_MIGRATION",
        supplied_by: str = "SYSTEM"
    ) -> FarmPlot:
        """Adds a new farm plot to an existing farmer."""
        plot = FarmPlot(
            farmer_id=farmer_id,
            plot_identifier=plot_identifier,
            land_area=land_area,
            area_unit=area_unit,
            has_drip_irrigation=has_drip_irrigation,
            water_source=water_source,
            village=village,
            area_status=area_status,
            irrigation_status=VerificationStatus.VERIFIED if has_drip_irrigation is not None else VerificationStatus.MISSING,
            data_source=data_source,
            supplied_by=supplied_by
        )
        self.session.add(plot)
        self.session.flush()
        return plot

    def add_crop_to_plot(
        self,
        farm_plot_id: int,
        crop_name: str,
        crop_variety: Optional[str] = None,
        planting_date: Optional[date] = None,
        planting_season: Optional[PlantingSeason] = None,
        growth_stage: Optional[str] = None,
        is_current: bool = True,
        crop_status: VerificationStatus = VerificationStatus.UNVERIFIED,
        data_source: str = "EXCEL_MIGRATION",
        supplied_by: str = "SYSTEM"
    ) -> CropRecord:
        """Attaches a crop record to a farm plot."""
        crop = CropRecord(
            farm_plot_id=farm_plot_id,
            crop_name=crop_name.strip(),
            crop_variety=crop_variety.strip() if crop_variety else None,
            planting_date=planting_date,
            planting_season=planting_season,
            growth_stage=growth_stage.strip() if growth_stage else None,
            is_current=is_current,
            crop_status=crop_status,
            variety_status=VerificationStatus.VERIFIED if crop_variety else VerificationStatus.MISSING,
            planting_date_status=VerificationStatus.VERIFIED if planting_date else VerificationStatus.MISSING,
            season_status=VerificationStatus.VERIFIED if planting_season else VerificationStatus.MISSING,
            stage_status=VerificationStatus.VERIFIED if growth_stage else VerificationStatus.MISSING,
            data_source=data_source,
            supplied_by=supplied_by
        )
        self.session.add(crop)
        self.session.flush()
        return crop

    def add_soil_profile(
        self,
        farm_plot_id: int,
        soil_type: Optional[str] = None,
        soil_fertility: Optional[str] = None,
        ph_level: Optional[float] = None,
        ec_level: Optional[float] = None,
        organic_carbon_pct: Optional[float] = None,
        nitrogen_n_kg_ha: Optional[float] = None,
        phosphorus_p_kg_ha: Optional[float] = None,
        potassium_k_kg_ha: Optional[float] = None,
        soil_health_card_number: Optional[str] = None,
        soil_type_status: VerificationStatus = VerificationStatus.UNVERIFIED,
        data_source: str = "EXCEL_MIGRATION",
        supplied_by: str = "SYSTEM"
    ) -> SoilProfile:
        """Attaches a soil analysis profile to a farm plot."""
        has_npk = any(x is not None for x in (nitrogen_n_kg_ha, phosphorus_p_kg_ha, potassium_k_kg_ha))
        profile = SoilProfile(
            farm_plot_id=farm_plot_id,
            soil_type=soil_type.strip() if soil_type else None,
            soil_fertility=soil_fertility.strip() if soil_fertility else None,
            ph_level=ph_level,
            ec_level=ec_level,
            organic_carbon_pct=organic_carbon_pct,
            nitrogen_n_kg_ha=nitrogen_n_kg_ha,
            phosphorus_p_kg_ha=phosphorus_p_kg_ha,
            potassium_k_kg_ha=potassium_k_kg_ha,
            soil_health_card_number=soil_health_card_number.strip() if soil_health_card_number else None,
            soil_type_status=soil_type_status if soil_type else VerificationStatus.MISSING,
            fertility_status=VerificationStatus.VERIFIED if soil_fertility else VerificationStatus.MISSING,
            npk_status=VerificationStatus.VERIFIED if has_npk else VerificationStatus.MISSING,
            data_source=data_source,
            supplied_by=supplied_by
        )
        self.session.add(profile)
        self.session.flush()
        return profile

    def add_contact(
        self,
        farmer_id: int,
        phone_number: str,
        contact_name: Optional[str] = None,
        relationship_type: Optional[str] = None,
        is_primary: bool = False,
        notes: Optional[str] = None
    ) -> FarmerContact:
        """Adds an alternate contact number for a farmer."""
        clean_phone = self.normalize_phone(phone_number)
        contact = FarmerContact(
            farmer_id=farmer_id,
            contact_name=contact_name.strip() if contact_name else None,
            phone_number=clean_phone,
            relationship_type=relationship_type,
            is_primary=is_primary,
            notes=notes
        )
        self.session.add(contact)
        self.session.flush()
        return contact

    def list_all(self, limit: int = 100, offset: int = 0) -> List[Farmer]:
        """Lists farmers with pagination and eager relationships."""
        stmt = (
            select(Farmer)
            .options(
                joinedload(Farmer.district),
                joinedload(Farmer.division),
                joinedload(Farmer.factory),
                joinedload(Farmer.assigned_cdo),
                selectinload(Farmer.contacts),
                selectinload(Farmer.plots).selectinload(FarmPlot.crops),
                selectinload(Farmer.plots).selectinload(FarmPlot.soil_profiles),
            )
            .order_by(Farmer.id)
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.scalars(stmt).unique())

    def count(self) -> int:
        """Returns total number of registered farmers."""
        stmt = select(func.count(Farmer.id))
        return self.session.scalar(stmt) or 0

    def generate_next_farmer_id(self) -> str:
        """Generates a sequential stable farmer identifier (e.g. 'FARM-00008')."""
        stmt = select(func.count(Farmer.id))
        total = (self.session.scalar(stmt) or 0) + 1
        return f"FARM-{total:05d}"
