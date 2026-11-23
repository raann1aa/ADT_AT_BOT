"""
Relational Database Models for Agricultural Communication and Coordination System.
Provides normalized entities for Farmers, Multi-Plot Land Holdings, Crops,
Soil Health Cards, Sugar Factories, CDOs, Agronomists, Issues, and Audit Logs.
"""

from datetime import datetime, date
from typing import Optional, List

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Date, DateTime,
    Text, ForeignKey, Enum as SQLEnum, Index, UniqueConstraint, func
)
from sqlalchemy.orm import relationship

from .connection import Base
from .enums import (
    VerificationStatus, PlantingSeason, AreaUnit,
    IssuePriority, IssueStatus, TaskTargetRole, TaskStatus, WebhookEventStatus
)


# ---------------------------------------------------------------------------
# 1. Geographic & Administrative Hierarchy
# ---------------------------------------------------------------------------

class District(Base):
    """Agricultural administrative district (e.g., Nashik, Ahmednagar, Pune)."""
    __tablename__ = "districts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    state = Column(String(100), nullable=False, default="Maharashtra")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    divisions = relationship("Division", back_populates="district", cascade="all, delete-orphan")
    farmers = relationship("Farmer", back_populates="district")

    def __repr__(self):
        return f"<District(id={self.id}, name='{self.name}', state='{self.state}')>"


class Division(Base):
    """Operational division or taluka cluster within a district."""
    __tablename__ = "divisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, index=True)
    district_id = Column(Integer, ForeignKey("districts.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    district = relationship("District", back_populates="divisions")
    factories = relationship("Factory", back_populates="division")
    cdos = relationship("CDO", back_populates="division")
    farmers = relationship("Farmer", back_populates="division")

    __table_args__ = (
        UniqueConstraint("district_id", "name", name="uq_district_division"),
    )

    def __repr__(self):
        return f"<Division(id={self.id}, name='{self.name}', district_id={self.district_id})>"


class Factory(Base):
    """Sugar factory, cooperative mill, or processing facility affiliated with farmers."""
    __tablename__ = "factories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(150), nullable=False, index=True)
    code = Column(String(50), nullable=False, unique=True, index=True)
    division_id = Column(Integer, ForeignKey("divisions.id", ondelete="SET NULL"), nullable=True)
    phone_number = Column(String(20), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    division = relationship("Division", back_populates="factories")
    cdos = relationship("CDO", back_populates="factory")
    farmers = relationship("Farmer", back_populates="factory")

    def __repr__(self):
        return f"<Factory(id={self.id}, code='{self.code}', name='{self.name}')>"


# ---------------------------------------------------------------------------
# 2. Field Officers & Technical Experts
# ---------------------------------------------------------------------------

class CDO(Base):
    """Cane Development Officer (CDO) managing farmer clusters and field data collection."""
    __tablename__ = "cdos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cdo_code = Column(String(50), nullable=False, unique=True, index=True)
    name = Column(String(150), nullable=False)
    phone_number = Column(String(20), nullable=False, unique=True, index=True)
    email = Column(String(150), nullable=True)
    factory_id = Column(Integer, ForeignKey("factories.id", ondelete="SET NULL"), nullable=True)
    division_id = Column(Integer, ForeignKey("divisions.id", ondelete="SET NULL"), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    factory = relationship("Factory", back_populates="cdos")
    division = relationship("Division", back_populates="cdos")
    assigned_farmers = relationship("Farmer", back_populates="assigned_cdo")
    assigned_issues = relationship("Issue", back_populates="assigned_cdo")

    def __repr__(self):
        return f"<CDO(id={self.id}, code='{self.cdo_code}', name='{self.name}')>"


class Agronomist(Base):
    """Senior Agricultural Specialist / Scientist handling complex crop escalations."""
    __tablename__ = "agronomists"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(150), nullable=False)
    phone_number = Column(String(20), nullable=False, unique=True, index=True)
    email = Column(String(150), nullable=True)
    specialization = Column(String(150), nullable=True)  # e.g., Entomology, Pathology, Sugarcane Nutrition
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    escalated_issues = relationship("Issue", back_populates="assigned_agronomist")

    def __repr__(self):
        return f"<Agronomist(id={self.id}, name='{self.name}', spec='{self.specialization}')>"


# ---------------------------------------------------------------------------
# 3. Farmer Master & Alternate Contacts
# ---------------------------------------------------------------------------

class Farmer(Base):
    """Master record for registered agricultural producer."""
    __tablename__ = "farmers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    farmer_id = Column(String(50), nullable=False, unique=True, index=True)  # e.g. "FARM-00101"
    full_name = Column(String(150), nullable=False, index=True)
    primary_phone = Column(String(20), nullable=False, unique=True, index=True)  # Clean 10-digit or E.164
    alternate_phone = Column(String(20), nullable=True)
    village = Column(String(100), nullable=True, index=True)
    tehsil = Column(String(100), nullable=True, index=True)
    district_id = Column(Integer, ForeignKey("districts.id", ondelete="SET NULL"), nullable=True)
    division_id = Column(Integer, ForeignKey("divisions.id", ondelete="SET NULL"), nullable=True)
    factory_id = Column(Integer, ForeignKey("factories.id", ondelete="SET NULL"), nullable=True)
    assigned_cdo_id = Column(Integer, ForeignKey("cdos.id", ondelete="SET NULL"), nullable=True)
    preferred_language = Column(String(20), default="mr", nullable=False)  # 'mr' (Marathi), 'hi', 'en'

    # Field Verification Statuses
    name_status = Column(SQLEnum(VerificationStatus, native_enum=False), default=VerificationStatus.UNVERIFIED, nullable=False)
    village_status = Column(SQLEnum(VerificationStatus, native_enum=False), default=VerificationStatus.UNVERIFIED, nullable=False)
    tehsil_status = Column(SQLEnum(VerificationStatus, native_enum=False), default=VerificationStatus.UNVERIFIED, nullable=False)

    # Provenance Tracking
    data_source = Column(String(100), default="EXCEL_MIGRATION", nullable=False)
    supplied_by = Column(String(100), default="SYSTEM", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verified_by = Column(String(100), nullable=True)

    # Relationships
    district = relationship("District", back_populates="farmers")
    division = relationship("Division", back_populates="farmers")
    factory = relationship("Factory", back_populates="farmers")
    assigned_cdo = relationship("CDO", back_populates="assigned_farmers")
    contacts = relationship("FarmerContact", back_populates="farmer", cascade="all, delete-orphan")
    plots = relationship("FarmPlot", back_populates="farmer", cascade="all, delete-orphan")
    conversation_sessions = relationship("ConversationSession", back_populates="farmer")
    issues = relationship("Issue", back_populates="farmer")

    def __repr__(self):
        return f"<Farmer(id={self.id}, farmer_id='{self.farmer_id}', name='{self.full_name}', phone='{self.primary_phone}')>"


class FarmerContact(Base):
    """Alternate contacts, family members, or shared mobile access points for a farmer."""
    __tablename__ = "farmer_contacts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    farmer_id = Column(Integer, ForeignKey("farmers.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_name = Column(String(150), nullable=True)
    phone_number = Column(String(20), nullable=False, index=True)
    relationship_type = Column(String(50), nullable=True)  # e.g., 'Self', 'Son', 'Brother', 'Neighbor'
    is_primary = Column(Boolean, default=False, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    farmer = relationship("Farmer", back_populates="contacts")

    def __repr__(self):
        return f"<FarmerContact(farmer_id={self.farmer_id}, phone='{self.phone_number}', relation='{self.relationship_type}')>"


# ---------------------------------------------------------------------------
# 4. Multi-Plot Land Holdings, Crops & Soil Profiles
# ---------------------------------------------------------------------------

class FarmPlot(Base):
    """
    Distinct parcel or land plot owned by a farmer.
    Supports farmers with multiple plots in different locations with distinct crops.
    """
    __tablename__ = "farm_plots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    farmer_id = Column(Integer, ForeignKey("farmers.id", ondelete="CASCADE"), nullable=False, index=True)
    plot_identifier = Column(String(50), nullable=False)  # e.g., "PLOT-1", "GAT-NO-142", "SURVEY-45"
    land_area = Column(Float, nullable=False)             # Numeric acreage or gunthas
    area_unit = Column(SQLEnum(AreaUnit, native_enum=False), default=AreaUnit.ACRES, nullable=False)
    has_drip_irrigation = Column(Boolean, nullable=True)
    water_source = Column(String(100), nullable=True)     # "Well", "Borewell", "Canal", "River"
    village = Column(String(100), nullable=True)          # Specific plot village if different from home

    # Field Verification Status
    area_status = Column(SQLEnum(VerificationStatus, native_enum=False), default=VerificationStatus.UNVERIFIED, nullable=False)
    irrigation_status = Column(SQLEnum(VerificationStatus, native_enum=False), default=VerificationStatus.UNVERIFIED, nullable=False)

    # Provenance Tracking
    data_source = Column(String(100), default="EXCEL_MIGRATION", nullable=False)
    supplied_by = Column(String(100), default="SYSTEM", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verified_by = Column(String(100), nullable=True)

    # Relationships
    farmer = relationship("Farmer", back_populates="plots")
    crops = relationship("CropRecord", back_populates="farm_plot", cascade="all, delete-orphan")
    soil_profiles = relationship("SoilProfile", back_populates="farm_plot", cascade="all, delete-orphan")
    issues = relationship("Issue", back_populates="farm_plot")

    __table_args__ = (
        UniqueConstraint("farmer_id", "plot_identifier", name="uq_farmer_plot"),
    )

    def __repr__(self):
        return f"<FarmPlot(id={self.id}, farmer_id={self.farmer_id}, plot='{self.plot_identifier}', area={self.land_area} {self.area_unit.value})>"


class CropRecord(Base):
    """
    Crop lifecycle record cultivated on a specific plot.
    Maintains planting date, planting season (Suru, Adsali, Kharif, Rabi), and variety.
    """
    __tablename__ = "crop_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    farm_plot_id = Column(Integer, ForeignKey("farm_plots.id", ondelete="CASCADE"), nullable=False, index=True)
    crop_name = Column(String(100), nullable=False, index=True)  # e.g., 'Sugarcane', 'Onion', 'Cotton'
    crop_variety = Column(String(100), nullable=True)            # e.g., 'Co 86032', 'CoM 0265', 'Phule Samarth'
    planting_date = Column(Date, nullable=True)
    planting_season = Column(SQLEnum(PlantingSeason, native_enum=False), nullable=True)
    growth_stage = Column(String(100), nullable=True)            # e.g., 'Germination', 'Tillering', 'Grand Growth'
    is_current = Column(Boolean, default=True, nullable=False)   # Active crop vs historical record

    # Verification Statuses
    crop_status = Column(SQLEnum(VerificationStatus, native_enum=False), default=VerificationStatus.UNVERIFIED, nullable=False)
    variety_status = Column(SQLEnum(VerificationStatus, native_enum=False), default=VerificationStatus.UNVERIFIED, nullable=False)
    planting_date_status = Column(SQLEnum(VerificationStatus, native_enum=False), default=VerificationStatus.UNVERIFIED, nullable=False)
    season_status = Column(SQLEnum(VerificationStatus, native_enum=False), default=VerificationStatus.UNVERIFIED, nullable=False)
    stage_status = Column(SQLEnum(VerificationStatus, native_enum=False), default=VerificationStatus.UNVERIFIED, nullable=False)

    # Provenance Tracking
    data_source = Column(String(100), default="EXCEL_MIGRATION", nullable=False)
    supplied_by = Column(String(100), default="SYSTEM", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verified_by = Column(String(100), nullable=True)

    # Relationships
    farm_plot = relationship("FarmPlot", back_populates="crops")

    def __repr__(self):
        return f"<CropRecord(id={self.id}, plot_id={self.farm_plot_id}, crop='{self.crop_name}', variety='{self.crop_variety}')>"


class SoilProfile(Base):
    """
    Physical and chemical soil parameters for a land plot.
    Stores NPK, pH, EC, organic carbon, and Soil Health Card numbers.
    """
    __tablename__ = "soil_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    farm_plot_id = Column(Integer, ForeignKey("farm_plots.id", ondelete="CASCADE"), nullable=False, index=True)
    soil_type = Column(String(100), nullable=True)              # e.g., 'Black Cotton', 'Medium Black', 'Clay Loam'
    soil_fertility = Column(String(100), nullable=True)         # 'Low', 'Medium', 'High'
    ph_level = Column(Float, nullable=True)                     # Soil reaction (e.g., 7.2)
    ec_level = Column(Float, nullable=True)                     # Electrical Conductivity in dS/m
    organic_carbon_pct = Column(Float, nullable=True)           # Organic Carbon % (e.g., 0.55)
    nitrogen_n_kg_ha = Column(Float, nullable=True)             # Available Nitrogen in kg/ha
    phosphorus_p_kg_ha = Column(Float, nullable=True)           # Available Phosphorus in kg/ha
    potassium_k_kg_ha = Column(Float, nullable=True)            # Available Potassium in kg/ha
    soil_health_card_number = Column(String(100), nullable=True)

    # Verification Statuses
    soil_type_status = Column(SQLEnum(VerificationStatus, native_enum=False), default=VerificationStatus.UNVERIFIED, nullable=False)
    fertility_status = Column(SQLEnum(VerificationStatus, native_enum=False), default=VerificationStatus.UNVERIFIED, nullable=False)
    npk_status = Column(SQLEnum(VerificationStatus, native_enum=False), default=VerificationStatus.UNVERIFIED, nullable=False)

    # Provenance Tracking
    data_source = Column(String(100), default="EXCEL_MIGRATION", nullable=False)
    supplied_by = Column(String(100), default="SYSTEM", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verified_by = Column(String(100), nullable=True)

    # Relationships
    farm_plot = relationship("FarmPlot", back_populates="soil_profiles")

    def __repr__(self):
        return f"<SoilProfile(id={self.id}, plot_id={self.farm_plot_id}, type='{self.soil_type}', pH={self.ph_level})>"


# ---------------------------------------------------------------------------
# 5. Conversation Sessions & Multi-Turn State
# ---------------------------------------------------------------------------

class ConversationSession(Base):
    """
    Session-based state tracker for WhatsApp dialogs.
    Enables missing agronomic field elicitation in Phase 3.
    """
    __tablename__ = "conversation_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), nullable=False, unique=True, index=True)
    farmer_id = Column(Integer, ForeignKey("farmers.id", ondelete="SET NULL"), nullable=True, index=True)
    phone_number = Column(String(20), nullable=False, index=True)
    current_state = Column(String(50), default="IDLE", nullable=False)
    pending_fields = Column(Text, nullable=True)   # JSON string storing missing parameters to collect
    context_data = Column(Text, nullable=True)     # JSON string storing ongoing conversational variables
    last_interaction_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    farmer = relationship("Farmer", back_populates="conversation_sessions")

    def __repr__(self):
        return f"<ConversationSession(session_id='{self.session_id}', phone='{self.phone_number}', state='{self.current_state}')>"


# ---------------------------------------------------------------------------
# 6. Issues, Escalations & Follow-up Tasks
# ---------------------------------------------------------------------------

class Issue(Base):
    """
    Farmer agricultural problem, disease incident, or agronomic grievance.
    Enables coordination between Coordinator, CDO, and Agronomist.
    """
    __tablename__ = "issues"

    id = Column(Integer, primary_key=True, autoincrement=True)
    issue_code = Column(String(50), nullable=False, unique=True, index=True)  # e.g., "ISS-202611-0001"
    farmer_id = Column(Integer, ForeignKey("farmers.id", ondelete="CASCADE"), nullable=False, index=True)
    farm_plot_id = Column(Integer, ForeignKey("farm_plots.id", ondelete="SET NULL"), nullable=True)
    category = Column(String(100), nullable=False, index=True)  # PEST_DISEASE, NUTRIENT, IRRIGATION, etc.
    priority = Column(SQLEnum(IssuePriority, native_enum=False), default=IssuePriority.MEDIUM, nullable=False)
    status = Column(SQLEnum(IssueStatus, native_enum=False), default=IssueStatus.OPEN, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    media_urls = Column(Text, nullable=True)  # JSON-encoded array of media file paths/URLs
    assigned_cdo_id = Column(Integer, ForeignKey("cdos.id", ondelete="SET NULL"), nullable=True)
    assigned_agronomist_id = Column(Integer, ForeignKey("agronomists.id", ondelete="SET NULL"), nullable=True)
    resolution_notes = Column(Text, nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    farmer = relationship("Farmer", back_populates="issues")
    farm_plot = relationship("FarmPlot", back_populates="issues")
    assigned_cdo = relationship("CDO", back_populates="assigned_issues")
    assigned_agronomist = relationship("Agronomist", back_populates="escalated_issues")
    follow_up_tasks = relationship("FollowUpTask", back_populates="issue", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Issue(code='{self.issue_code}', status='{self.status.value}', priority='{self.priority.value}')>"


class FollowUpTask(Base):
    """
    Actionable task generated to obtain missing information or follow up on unresolved issues.
    Assigned to Farmer, CDO, or Agronomist with deadline and reminder tracking.
    """
    __tablename__ = "follow_up_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_code = Column(String(50), nullable=False, unique=True, index=True)  # e.g., "TSK-001"
    issue_id = Column(Integer, ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, index=True)
    target_role = Column(SQLEnum(TaskTargetRole, native_enum=False), nullable=False)
    target_phone = Column(String(20), nullable=True)
    description = Column(Text, nullable=False)
    due_date = Column(DateTime(timezone=True), nullable=True)
    status = Column(SQLEnum(TaskStatus, native_enum=False), default=TaskStatus.PENDING, nullable=False, index=True)
    reminder_count = Column(Integer, default=0, nullable=False)
    last_reminder_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    issue = relationship("Issue", back_populates="follow_up_tasks")

    def __repr__(self):
        return f"<FollowUpTask(code='{self.task_code}', target='{self.target_role.value}', status='{self.status.value}')>"


# ---------------------------------------------------------------------------
# 7. Persistent Message Deduplication & Audit Logs
# ---------------------------------------------------------------------------

class WebhookEvent(Base):
    """
    Persistent idempotency and deduplication ledger.
    Guarantees zero duplicate processing across server restarts and concurrent retries.
    """
    __tablename__ = "webhook_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(String(100), nullable=False, unique=True, index=True)
    sender_phone = Column(String(20), nullable=False, index=True)
    event_type = Column(String(50), default="message", nullable=False)
    payload_hash = Column(String(64), nullable=True)
    status = Column(SQLEnum(WebhookEventStatus, native_enum=False), default=WebhookEventStatus.RECEIVED, nullable=False, index=True)
    retry_count = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<WebhookEvent(msg_id='{self.message_id}', phone='{self.sender_phone}', status='{self.status.value}')>"


class AuditLog(Base):
    """
    Persistent audit trail of incoming queries, actions taken, RAG sources, and latencies.
    Replaces ephemeral in-memory AuditLogger deque.
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    log_id = Column(String(50), nullable=False, unique=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    sender_name = Column(String(150), nullable=True)
    sender_phone = Column(String(20), nullable=False, index=True)
    district = Column(String(100), nullable=True)
    group_id = Column(String(100), nullable=True)
    group_name = Column(String(150), nullable=True)
    incoming_text = Column(Text, nullable=True)
    category = Column(String(50), nullable=False, index=True)
    action = Column(String(50), nullable=False)
    bot_reply = Column(Text, nullable=True)
    rag_sources = Column(Text, nullable=True)  # JSON-encoded list of source references
    processing_time_ms = Column(Float, default=0.0, nullable=False)
    is_escalated = Column(Boolean, default=False, nullable=False)
    resolved = Column(Boolean, default=False, nullable=False)

    def __repr__(self):
        return f"<AuditLog(log_id='{self.log_id}', category='{self.category}', action='{self.action}')>"
