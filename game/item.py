# game/item.py
"""
Represents a unique instance of an item in the game world.
"""
import json
import logging
from typing import Dict, Any, Optional, Set, List, Union

log = logging.getLogger(__name__)

class Item:
    """
    Represents a unique item instance, combining template data with instance data.
    """
    def __init__(self, instance_data: Dict[str, Any], template_data: Dict[str, Any]):
        """
        Initializes an Item from its unique instance data and shared template data.
        """
        if not instance_data or not template_data:
            raise ValueError("Item requires both instance and template data.")

        # --- Unique Instance Data ---
        self.id: str = instance_data['id'] # The UUID of this specific item
        self.container_id: Optional[str] = instance_data.get('container_id')
        self.condition: int = instance_data.get('condition', 100)
        self.instance_stats: Dict[str, Any] = instance_data.get('instance_stats', {})

        # --- Runtime Attributes ---
        self.contents: Dict[str, 'Item'] = {}

        # --- Shared Template Data ---
        self._template = template_data
        self._template_stats: Dict[str, Any] = {}
        try:
            # Pre-parse the stats JSON from the template for easier access via properties.
            self._template_stats = json.loads(self._template.get('stats', '{}') or '{}')
        except (json.JSONDecodeError, TypeError):
            log.warning("Could not parse stats JSON for item template %s", self._template.get('id'))

    def get_current_weight(self) -> int:
        """Calculates the total weight of all items inside this container."""
        if not self.contents:
            return 0
        return sum(item.weight for item in self.contents.values())

    @property
    def template_id(self) -> int:
        return self._template.get('id', 0)
    
    @property
    def Capacity(self) -> int:
        """The maximum weight this item can hold if it's a container."""
        return self._template_stats.get("capacity", 0)

    @property
    def name(self) -> str:
        # In the future, this could be modified by instance_stats (e.g., "a glowing sword")
        return self._template.get('name', 'an unknown item')

    @property
    def description(self) -> str:
        # This could also be modified by instance_stats (e.g., "It glows faintly.")
        return self._template.get('description', 'It is nondescript.')

    @property
    def item_type(self) -> str:
        return self._template.get('type', 'GENERAL').upper()

    @property
    def damage_type(self) -> Optional[str]:
        return self._template.get('damage_type')

    @property
    def flags(self) -> Set[str]:
        try:
            return set(json.loads(self._template.get('flags', '[]') or '[]'))
        except (json.JSONDecodeError, TypeError):
            return set()

    # --- Properties that pull from the template's stats dictionary ---
    @property
    def weight(self) -> int:
        return self._template_stats.get("weight", 1)

    @property
    def value(self) -> int:
        return self._template_stats.get("value", 0)

    @property
    def wear_location(self) -> Optional[Union[str, List[str]]]:
        return self._template_stats.get("wear_location")

    @property
    def speed(self) -> float:
        return self._template_stats.get("speed", 1.0)

    @property
    def damage_base(self) -> int:
        return self._template_stats.get("damage_base", 0)

    @property
    def damage_rng(self) -> int:
        return self._template_stats.get("damage_rng", 0)

    @property
    def armor(self) -> int:
        return self._template_stats.get("armor", 0)
    
    @property
    def spell_failure(self) -> int:
        """The percentage chance this item adds to spell failure."""
        return self._template_stats.get("spell_failure", 0)
        
    @property
    def block_chance(self) -> float:
        return self._template_stats.get("block_chance", 0.0)

    def has_flag(self, flag_name: str) -> bool:
        """Check if the item has a specific flag (case-insensitive)."""
        return flag_name.upper() in self.flags

    def __repr__(self) -> str:
        return f"<Item {self.id} (Template: {self.template_id})>"