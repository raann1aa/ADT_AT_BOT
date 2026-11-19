"""
Group Manager for Multi-District WhatsApp Groups.
Maps group identifiers to district metadata, crops, and languages.
"""

from typing import Dict, Optional, List
from form_automation.models import DistrictGroup
from form_automation.form_broadcast import DEFAULT_DISTRICT_GROUPS

class WhatsAppGroupManager:
    """Manages the directory of registered district WhatsApp groups."""

    def __init__(self, groups: Optional[List[DistrictGroup]] = None):
        self._groups_by_id: Dict[str, DistrictGroup] = {}
        for g in groups or DEFAULT_DISTRICT_GROUPS:
            self._groups_by_id[g.group_id] = g

    def register_group(self, group: DistrictGroup) -> None:
        """Registers a new district group."""
        self._groups_by_id[group.group_id] = group

    def get_group(self, group_id: str) -> Optional[DistrictGroup]:
        """Resolves a group ID to its DistrictGroup configuration."""
        return self._groups_by_id.get(group_id)

    def get_all_groups(self) -> List[DistrictGroup]:
        """Returns all registered groups."""
        return list(self._groups_by_id.values())

    def get_district_for_group(self, group_id: str) -> str:
        """Helper to get district name for a group, defaulting to 'General'."""
        g = self.get_group(group_id)
        return g.district if g else "General"
