"""
Database Package for Agricultural Automation System.
Exposes database models, connection session management, and enumeration types.
"""

from .connection import (
    engine,
    SessionFactory,
    Base,
    get_db,
    get_db_session,
    init_db,
    check_connection,
    DATABASE_URL
)

from .enums import (
    VerificationStatus,
    PlantingSeason,
    AreaUnit,
    IssuePriority,
    IssueStatus,
    TaskTargetRole,
    TaskStatus,
    WebhookEventStatus
)

from .models import (
    District,
    Division,
    Factory,
    CDO,
    Agronomist,
    Farmer,
    FarmerContact,
    FarmPlot,
    CropRecord,
    SoilProfile,
    ConversationSession,
    Issue,
    FollowUpTask,
    WebhookEvent,
    AuditLog
)

__all__ = [
    "engine",
    "SessionFactory",
    "Base",
    "get_db",
    "get_db_session",
    "init_db",
    "check_connection",
    "DATABASE_URL",
    "VerificationStatus",
    "PlantingSeason",
    "AreaUnit",
    "IssuePriority",
    "IssueStatus",
    "TaskTargetRole",
    "TaskStatus",
    "WebhookEventStatus",
    "District",
    "Division",
    "Factory",
    "CDO",
    "Agronomist",
    "Farmer",
    "FarmerContact",
    "FarmPlot",
    "CropRecord",
    "SoilProfile",
    "ConversationSession",
    "Issue",
    "FollowUpTask",
    "WebhookEvent",
    "AuditLog"
]
