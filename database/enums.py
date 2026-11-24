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
    NOT_PROVIDED = "NOT_PROVIDED"
    UNKNOWN = "UNKNOWN"
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"


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


class OutboxMessageStatus(str, Enum):
    """Delivery status for transactional outbox queue."""
    PENDING = "PENDING"
    DISPATCHED = "DISPATCHED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"


class ConversationState(str, Enum):
    """Lifecycle stage of farmer dialog state machine."""
    IDLE = "IDLE"
    AWAITING_FIELD_INPUT = "AWAITING_FIELD_INPUT"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    ESCALATED = "ESCALATED"
    RESOLVED = "RESOLVED"


class AgriculturalIntent(str, Enum):
    """
    Granular 13-category agricultural intent taxonomy for KrishiBot.
    Provides precise routing across the entire sugarcane and multi-crop lifecycle.
    """
    CROP_DISEASE_PEST = "CROP_DISEASE_PEST"                 # Pests, fungal/bacterial diseases, symptoms & controls
    FERTILIZER_NUTRITION = "FERTILIZER_NUTRITION"           # NPK dosages, micro-nutrients, fertigation, deficiency
    IRRIGATION_WATER = "IRRIGATION_WATER"                   # Drip irrigation schedule, water frequency, drought stress
    VARIETY_SELECTION = "VARIETY_SELECTION"                 # Cane varieties (Co 86032, CoM 0265, etc.), seed sets
    PLANTING_SOWING = "PLANTING_SOWING"                     # Sowing methods, spacing, seasons (Suru, Adsali, Pre-seasonal)
    HARVESTING_POST_HARVEST = "HARVESTING_POST_HARVEST"     # Cane maturity, brix, ratoon (खोडवा) management, cutting
    WEATHER_CLIMATE = "WEATHER_CLIMATE"                     # Rainfall, frost advisory, temperature fluctuations
    GOVERNMENT_SCHEME_SUBSIDY = "GOVERNMENT_SCHEME_SUBSIDY" # Drip subsidy, PM-Kisan, Soil Health Card, crop insurance
    CDO_COORDINATION_INQUIRY = "CDO_COORDINATION_INQUIRY"   # Requesting field officer inspection, factory slip/registration
    FARMER_PROFILE_UPDATE = "FARMER_PROFILE_UPDATE"         # Farmer providing farm area, planting date, soil type
    GENERAL_GREETING = "GENERAL_GREETING"                   # Namaste, Ram Ram, respectful greetings
    DISTRESS_EMERGENCY = "DISTRESS_EMERGENCY"               # Critical crop loss, fire, flood, acute emergency
    OFF_TOPIC_OTHER = "OFF_TOPIC_OTHER"                     # Unrelated forwards, jokes, out-of-domain chatter

