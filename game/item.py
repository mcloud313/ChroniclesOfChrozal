# game/item.py
"""
Represents an Item instance in the game world.
Loads data from an item template.
"""
import json
import logging
from typing import Dict, Any, Optional, Set, List, Union 
import aiosqlite 

log = logging.getLogger(__name__)

class Item:
    """
    Represents an item instance, based on an item_template row from the DB.
    For V1, instances primarily hold template data. Unique instance IDs deferred.   
    """
    def __init__(self, template_data: aiosqlite.Row):
        """
        Initialize Item from a database row (aiosqlite.row or dict)
        """
        if not template_data:
            raise ValueError("Cannot initialize Item with empty template_data.")

        self.template_id: int = template_data['id']
        self.name: str = template_data['name']
        self.description: str = template_data['description']
        self.item_type: str = template_data['type'] # e.g. WEAPON, ARMOR,
        self.damage_type: Optional[str] = template_data['damage_type']

        # Load stats JSON, providing defaults for key attributes
        try:
            # Ensure stats is treated as string if loaded from DB before json.loads
            stats_str = template_data['stats'] or '{}'
            if isinstance(stats_str, bytes): # Handle potential blob
                stats_str = stats_str.decode('utf-8')
            self._stats_dict: Dict[str, Any] = json.loads(stats_str)
        except (json.JSONDecodeError, TypeError):
            log.warning("Item template %d (%s): Could not decode stats JSON: %r",
                        self.template_id, self.name, template_data.get('stats', '{}'))
            self._stats_dict: Dict[str, Any] = {}

        # Load flags JSON into a set
        try:
            flags_str = template_data['flags'] or '[]'
            if isinstance(flags_str, bytes):
                flags_str = flags_str.decode('utf-8')
            flags_list = json.loads(flags_str)
            # Assign flags within the try block
            self.flags: Set[str] = set(flag.upper() for flag in flags_list)
        except (json.JSONDecodeError, TypeError): # <<< Added colon here
            log.warning("Item template %d (%s): Could not decode flags JSON: %r",
                        self.template_id, self.name, template_data.get('flags', '[]'))
            # Assign fallback value INSIDE and INDENTED under the except block
            self.flags = set()
    # --- Properties for easy access to common stats ---

    @property
    def weight(self) -> int:
        return self._stats_dict.get("weight", 1) #Default Weight 1

    @property
    def value(self) -> int:
        return self._stats_dict.get("value", 0) # Default value 0

    @property
    def wear_location(self) -> Optional[Union[str, List[str]]]:
        # Can be a single string slot or list of slots
        return self._stats_dict.get("wear_location")

    @property
    def speed(self) -> float:
        # Roundtime applied when used/wielded/worn etc.
        return self._stats_dict.get("speed", 1.0) # Default 1 second

    @property
    def damage_base(self) -> int:
        return self._stats_dict.get("damage_base", 0)

    @property
    def damage_rng(self) -> int:
        # e.g., if rng is 5, damage is base + random(1 to 5)
        return self._stats_dict.get("damage_rng", 0)

    @property
    def armor(self) -> int:
        return self._stats_dict.get("armor", 0)

    # --- Utility methods ---

    def has_flag(self, flag_name: str) -> bool:
        """Check if the item has a specific flag (case-insensitive)."""
        return flag_name.upper() in self.flags

    def __repr__(self) -> str:
        return f"<Item {self.template_id}: '{self.name}'>"

    def __str__(self) -> str:
        # Simple representation, examine command will show more
        return self.name