"""
Data models for Farmer Form Submissions and Multi-District Registry.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field

class FarmerFormSubmission(BaseModel):
    """Represents a single submission from the weekly Google Form."""
    farmer_name: str = Field(..., description="Full name of farmer")
    phone_number: str = Field(..., description="Mobile number (e.g. +919876543210 or 9876543210)")
    district: str = Field(..., description="District name (e.g. Nashik, Indore, Ludhiana)")
    area_tehsil: str = Field("", description="Sub-district / Block / Tehsil / Taluka")
    farm_size_acres: float = Field(..., description="Total farm area in acres")
    crop_grown: str = Field(..., description="Primary crop currently on the farm")
    soil_type: str = Field("Black Cotton", description="Type of soil (Black Cotton, Alluvial, Red, Sandy Loam)")
    sowing_stage: str = Field("Vegetative", description="Current stage (Sowing, Vegetative, Flowering, Fruiting)")
    has_drip_irrigation: bool = Field(True, description="Whether farm has micro-irrigation installed")
    submission_timestamp: datetime = Field(default_factory=datetime.now)

    def clean_phone(self) -> str:
        """Normalizes phone number to standard 10-digit format without country code/spaces."""
        digits = "".join(filter(str.isdigit, self.phone_number))
        if len(digits) > 10:
            return digits[-10:]
        return digits

class DistrictGroup(BaseModel):
    """Represents a WhatsApp group representing a specific agricultural district."""
    group_id: str
    group_name: str
    district: str
    state: str
    primary_crops: List[str]
    default_language: str = "Hindi"
    active_form_link: str = "https://forms.gle/WeeklyFarmerSurvey"
