# game/item.py
"""
Represents a unique instance of an item in the game world.
"""
from __future__ import annotations
import json
import logging
from typing import Dict, Any, Optional, Set, List, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from .character import Character
    from .room import Room

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
        self.last_moved_at = instance_data.get('last_moved_at')
        self.room: Optional[Room] = None

        # FIX: Properly handle instance_stats which might be a string or None
        stats_data = instance_data.get('instance_stats')
        if isinstance(stats_data, str):
            try:
                self.instance_stats: Dict[str, Any] = json.loads(stats_data)
            except (json.JSONDecodeError, TypeError):
                self.instance_stats: Dict[str, Any] = {}
        elif isinstance(stats_data, dict):
            self.instance_stats: Dict[str, Any] = stats_data
        else:
            self.instance_stats: Dict[str, Any] = {}
        
        self.instance_stats.setdefault('is_open', False)

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

    def get_total_contents_weight(self) -> int:
        """Calculates the total weight of all items inside this container."""
        if not self.contents:
            return 0
        # FIX: Recursively get the weight of items in sub-containers
        return sum(item.get_total_weight() for item in self.contents.values())

    def get_total_weight(self) -> int:
        """Calculates the item's own weight plus the weight of its contents."""
        return self.weight + self.get_total_contents_weight()

    @property
    def template_id(self) -> int:
        return self._template.get('id', 0)
    
    @property
    def capacity(self) -> int:
        """The maximum weight this item can hold if it's a container."""
        return self._template_stats.get("capacity", 0)

    @property
    def name(self) -> str:
        return self._template.get('name', 'an unknown item')

    @property
    def description(self) -> str:
        return self._template.get('description', 'It is nondescript.')

    @property
    def item_type(self) -> str:
        return self._template.get('type', 'GENERAL').upper()

    @property
    def damage_type(self) -> Optional[str]:
        return self._template.get('damage_type')

    @property
    def flags(self) -> Set[str]:
        flags_data = self._template.get('flags')
        # FIX: Check for both string and list/set types for flags
        if isinstance(flags_data, str):
            try:
                return set(json.loads(flags_data or '[]'))
            except (json.JSONDecodeError, TypeError):
                return set()
        elif isinstance(flags_data, (list, set)):
            return set(flags_data)
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
        return self._template_stats.get("spell_failure", 0)
        
    @property
    def block_chance(self) -> float:
        return self._template_stats.get("block_chance", 0.0)
    
    @property
    def is_open(self) -> bool:
        return self.instance_stats.get('is_open', False)
    
    @property
    def unlocks(self) -> List[str]:
        return self._template_stats.get("unlocks", [])

    def has_flag(self, flag_name: str) -> bool:
        return flag_name.upper() in self.flags

    def is_equipped(self, character: 'Character') -> bool:
        """Checks if the item is equipped by the given character."""
        return self.id in [item.id for item in character._equipped_items.values() if item]

    def is_in_container(self) -> bool:
        """Checks if the item is inside another item."""
        return self.container_id is not None

    def __repr__(self) -> str:
        return f"<Item {self.id} (Template: {self.template_id})>"