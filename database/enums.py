"""
Database Enums for Farmer Support and Agronomic Automation System.
Defines standardized categorical values for verification status, seasons,
issue lifecycle, and role hierarchies.
"""

from enum import Enum

class VerificationStatus(str, Enum):
    """Data provenance verification state for farmer/farm fields."""
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    MISSING = "MISSING"
    NEEDS_CORRECTION = "NEEDS_CORRECTION"


class PlantingSeason(str, Enum):
    """
    Standard planting seasons in Indian agriculture,
    with comprehensive coverage for Maharashtra sugarcane cycles.
    """
    SURU = "SURU"                  # Jan - Feb planting (Sugarcane)
    ADSALI = "ADSALI"              # July - Aug planting (Sugarcane 16-18 month crop)
    PRE_SEASONAL = "PRE_SEASONAL"  # Oct - Nov planting (Sugarcane)
    KHARIF = "KHARIF"              # Monsoon season (June - Oct)
    RABI = "RABI"                  # Winter season (Oct - March)
    SUMMER = "SUMMER"              # Summer season (March - June)
    OTHER = "OTHER"


class AreaUnit(str, Enum):
    """Units of measurement for land holdings."""
    ACRES = "ACRES"
    GUNTHAS = "GUNTHAS"            # 40 Gunthas = 1 Acre
    HECTARES = "HECTARES"          # 1 Hectare ≈ 2.47 Acres
    BIGHA = "BIGHA"


class IssuePriority(str, Enum):
    """Priority level for agronomic queries and field complaints."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"          # Crop failure risk, widespread pest infestation


class IssueStatus(str, Enum):
    """Lifecycle tracking for farmer queries and escalations."""
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    ESCALATED_CDO = "ESCALATED_CDO"
    ESCALATED_AGRONOMIST = "ESCALATED_AGRONOMIST"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class TaskTargetRole(str, Enum):
    """Target stakeholder role assigned to follow-up tasks."""
    FARMER = "FARMER"
    CDO = "CDO"
    AGRONOMIST = "AGRONOMIST"
    COORDINATOR = "COORDINATOR"


class TaskStatus(str, Enum):
    """Execution status for follow-up coordination tasks."""
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    OVERDUE = "OVERDUE"
    CANCELLED = "CANCELLED"


class WebhookEventStatus(str, Enum):
    """Processing state for webhook message deduplication & idempotency."""
    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DUPLICATE = "DUPLICATE"
