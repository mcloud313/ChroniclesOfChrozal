# game/item.py
"""
Represents an Item instance in the game world.
Loads data from an item template.
"""
import json
import logging
from typing import Dict, Any, Optional, Set, List, Union

log = logging.getLogger(__name__)

class Item:
    """
    Represents an item instance, based on an item_template row from the DB.
    """
    def __init__(self, template_data: Dict[str, Any]):
        """
        Initializes an Item from a dictionary of template data.
        """
        if not template_data:
            raise ValueError("Cannot initialize Item with empty template_data.")

        self._data = template_data
        self.template_id: int = self._data['id']
        self.name: str = self._data['name']
        self.description: str = self._data['description']
        self.item_type: str = self._data['type'].upper()
        self.damage_type: Optional[str] = self._data['damage_type']

        # Load stats JSON, providing defaults for key attributes
        try:
            stats_str = self._data.get('stats') or '{}'
            self._stats_dict: Dict[str, Any] = json.loads(stats_str)
        except (json.JSONDecodeError, TypeError):
            log.warning("Item template %d (%s): Could not decode stats JSON.", self.template_id, self.name)
            self._stats_dict = {}

        # Load flags JSON into a set
        try:
            flags_str = self._data.get('flags') or '[]'
            flags_list = json.loads(flags_str)
            self.flags: Set[str] = {flag.upper() for flag in flags_list}
        except (json.JSONDecodeError, TypeError):
            log.warning("Item template %d (%s): Could not decode flags JSON.", self.template_id, self.name)
            self.flags = set()

    # --- Properties for easy access to common stats ---
    @property
    def weight(self) -> int:
        return self._stats_dict.get("weight", 1)

    @property
    def value(self) -> int:
        return self._stats_dict.get("value", 0)

    @property
    def wear_location(self) -> Optional[Union[str, List[str]]]:
        return self._stats_dict.get("wear_location")

    @property
    def speed(self) -> float:
        return self._stats_dict.get("speed", 1.0)

    @property
    def damage_base(self) -> int:
        return self._stats_dict.get("damage_base", 0)

    @property
    def damage_rng(self) -> int:
        return self._stats_dict.get("damage_rng", 0)

    @property
    def armor(self) -> int:
        return self._stats_dict.get("armor", 0)
        
    @property
    def block_chance(self) -> float:
        # BUG FIX: Safely handle missing value, preventing a crash.
        return self._stats_dict.get("block_chance", 0.0)

    def has_flag(self, flag_name: str) -> bool:
        """Check if the item has a specific flag (case-insensitive)."""
        return flag_name.upper() in self.flags

    def __repr__(self) -> str:
        return f"<Item {self.template_id}: '{self.name}'>"

    def __str__(self) -> str:
        return self.name