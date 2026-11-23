"""
CDO, Agronomist, and Administrative Hierarchy Repository.
Provides lookups and management for Cane Development Officers,
agronomists, sugar factories, divisions, and districts.
"""

import logging
from typing import Optional, List
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select

from database.models import District, Division, Factory, CDO, Agronomist

logger = logging.getLogger("CDORepository")


class CDORepository:
    """Data access repository for field staff and administrative hierarchies."""

    def __init__(self, session: Session):
        self.session = session

    # -----------------------------------------------------------------------
    # Geographic Hierarchy
    # -----------------------------------------------------------------------

    def get_or_create_district(self, name: str, state: str = "Maharashtra") -> District:
        """Finds an existing district by name or creates it."""
        clean_name = name.strip()
        stmt = select(District).where(District.name.ilike(clean_name))
        district = self.session.scalars(stmt).first()
        if not district:
            district = District(name=clean_name, state=state)
            self.session.add(district)
            self.session.flush()
        return district

    def get_or_create_division(self, district_id: int, name: str) -> Division:
        """Finds or creates an administrative division within a district."""
        clean_name = name.strip()
        stmt = select(Division).where(
            Division.district_id == district_id,
            Division.name.ilike(clean_name)
        )
        division = self.session.scalars(stmt).first()
        if not division:
            division = Division(district_id=district_id, name=clean_name)
            self.session.add(division)
            self.session.flush()
        return division

    def get_or_create_factory(
        self,
        name: str,
        code: str,
        division_id: Optional[int] = None,
        phone_number: Optional[str] = None
    ) -> Factory:
        """Finds or creates a sugar factory / cluster mill record."""
        stmt = select(Factory).where(Factory.code == code)
        factory = self.session.scalars(stmt).first()
        if not factory:
            factory = Factory(
                name=name.strip(),
                code=code.strip(),
                division_id=division_id,
                phone_number=phone_number
            )
            self.session.add(factory)
            self.session.flush()
        return factory

    # -----------------------------------------------------------------------
    # Field Officers (CDO)
    # -----------------------------------------------------------------------

    def get_cdo_by_code(self, cdo_code: str) -> Optional[CDO]:
        """Fetch CDO by employee code."""
        stmt = (
            select(CDO)
            .options(joinedload(CDO.factory), joinedload(CDO.division))
            .where(CDO.cdo_code == cdo_code)
        )
        return self.session.scalars(stmt).first()

    def get_cdo_by_phone(self, phone: str) -> Optional[CDO]:
        """Fetch CDO by registered mobile number."""
        clean_phone = "".join(filter(str.isdigit, phone))[-10:]
        stmt = (
            select(CDO)
            .options(joinedload(CDO.factory), joinedload(CDO.division))
            .where(CDO.phone_number == clean_phone)
        )
        return self.session.scalars(stmt).first()

    def create_cdo(
        self,
        cdo_code: str,
        name: str,
        phone_number: str,
        email: Optional[str] = None,
        factory_id: Optional[int] = None,
        division_id: Optional[int] = None
    ) -> CDO:
        """Registers a new Cane Development Officer."""
        clean_phone = "".join(filter(str.isdigit, phone_number))[-10:]
        cdo = CDO(
            cdo_code=cdo_code.strip(),
            name=name.strip(),
            phone_number=clean_phone,
            email=email.strip() if email else None,
            factory_id=factory_id,
            division_id=division_id,
            is_active=True
        )
        self.session.add(cdo)
        self.session.flush()
        return cdo

    def list_cdos_by_factory(self, factory_id: int) -> List[CDO]:
        """Returns all CDOs attached to a specific factory."""
        stmt = select(CDO).where(CDO.factory_id == factory_id, CDO.is_active.is_(True))
        return list(self.session.scalars(stmt).all())

    # -----------------------------------------------------------------------
    # Agronomists (Technical Specialists)
    # -----------------------------------------------------------------------

    def create_agronomist(
        self,
        name: str,
        phone_number: str,
        email: Optional[str] = None,
        specialization: Optional[str] = None
    ) -> Agronomist:
        """Registers a senior agronomist or entomology/pathology specialist."""
        clean_phone = "".join(filter(str.isdigit, phone_number))[-10:]
        agronomist = Agronomist(
            name=name.strip(),
            phone_number=clean_phone,
            email=email.strip() if email else None,
            specialization=specialization.strip() if specialization else None,
            is_active=True
        )
        self.session.add(agronomist)
        self.session.flush()
        return agronomist

    def get_agronomist_by_phone(self, phone: str) -> Optional[Agronomist]:
        """Fetch agronomist by phone."""
        clean_phone = "".join(filter(str.isdigit, phone))[-10:]
        stmt = select(Agronomist).where(Agronomist.phone_number == clean_phone)
        return self.session.scalars(stmt).first()

    def list_agronomists_by_specialization(self, keyword: str) -> List[Agronomist]:
        """Lists active agronomists matching a specific specialization keyword."""
        stmt = select(Agronomist).where(
            Agronomist.is_active.is_(True),
            Agronomist.specialization.ilike(f"%{keyword}%")
        )
        return list(self.session.scalars(stmt).all())
