# game/room.py
import json
import logging
import time
import asyncio
import textwrap
from .item import Item
from typing import Set, Dict, Any, Optional, List, Union, TYPE_CHECKING

# FIX: Import Mob for check_respawn
if TYPE_CHECKING:
    from .character import Character
    from .mob import Mob
    from .world import World
    from .database import DatabaseManager

from .mob import Mob # <-- ADD THIS IMPORT

log = logging.getLogger(__name__)

class Room:
    """Represents a single location in the game world."""
    def __init__(self, db_data: Dict[str, Any]):
        self.dbid: int = db_data['id']
        self.area_id: int = db_data['area_id']
        self.name: str = db_data['name']
        self.description: str = db_data['description']
        
        # FIX: Simplified __init__. Exits and Objects are now loaded by world.py after creation.
        # This ensures the data structures are correct from the start.
        self.exits: Dict[str, Any] = {}
        self.objects: List[Dict[str, Any]] = []

        # This logic for flags and spawners is correct as they are still on the rooms table.
        flags_data = db_data.get('flags') or []
        self.flags: Set[str] = set(json.loads(flags_data) if isinstance(flags_data, str) else flags_data)
        
        spawners_data = db_data.get('spawners') or {}
        spawners_dict = json.loads(spawners_data) if isinstance(spawners_data, str) else spawners_data
        self.spawners: Dict[int, Dict[str, Any]] = {int(k): v for k, v in spawners_dict.items()}

        buy_filter_data = db_data.get('shop_buy_filter')
        self.shop_buy_filter = json.loads(buy_filter_data) if isinstance(buy_filter_data, str) else buy_filter_data
        self.shop_sell_modifier: float = db_data.get('shop_sell_modifier', 0.5)
        
        # Runtime attributes
        self.characters: Set['Character'] = set()
        self.mobs: Set['Mob'] = set()
        self.coinage: int = db_data.get('coinage', 0)
        self.item_instance_ids: List[str] = []
        
    def add_character(self, character: 'Character'):
        """Adds a character object to the room."""
        self.characters.add(character)
    
    def remove_character(self, character: 'Character'):
        """Removes a character object from the room."""
        self.characters.discard(character)

    def get_item_instance_by_name(self, item_name: str, world: 'World') -> Optional['Item']:
        name_lower = item_name.lower()
        for instance_id in self.item_instance_ids:
            item_object = world.get_item_object(instance_id)
            if item_object and name_lower in item_object.name.lower():
                return item_object
        return None

    def get_look_string(self, looker: 'Character', world: 'World') -> str:
        """Generates the formatted string describing the room's appearance."""
        area_name = "Unknown Area"
        if area_data := world.get_area(self.area_id):
            area_name = area_data.get('name', f"Area {self.area_id}")

        wrapped_desc = textwrap.fill(self.description, width=79)
        output_lines = [
            f"[{self.name}, {area_name}] [{self.dbid}]",
            wrapped_desc,
            f"[Exits: {', '.join(sorted(self.exits.keys())) if self.exits else 'none'}]"
        ]

        if not looker.can_see():
            return "It is pitch black..."

        other_chars = sorted([c.name for c in self.characters if c != looker])
        if other_chars:
            output_lines.append("Also Here: " + ", ".join(other_chars) + ".")

        mob_counts = {}
        for mob in self.mobs:
            if mob.is_alive() and not mob.is_hidden: # Add "and not mob.is_hidden"
                mob_counts[mob.name] = mob_counts.get(mob.name, 0) + 1
        if mob_counts:
            formatted_mob_list = [f"{name.capitalize()}" + (f" (x{count})" if count > 1 else "") for name, count in sorted(mob_counts.items())]
            output_lines.append("Visible Creatures: " + ", ".join(formatted_mob_list) + ".")

        if self.item_instance_ids:
            item_names = []
            for instance_id in self.item_instance_ids:
                item = world.get_item_object(instance_id)
                if item:
                    item_names.append(item.name)
            # if item_names:
            #     output_lines.append("On the ground: " + ", ".join(sorted(item_names)) + ".")

        if self.objects:
            object_names = sorted([obj.get('name', 'an object') for obj in self.objects])
            output_lines.append("Objects of interest: " + ", ".join(object_names) + ".")

        return "\r\n".join(output_lines)
    
    async def broadcast(self, message: str, exclude: Optional[Set[Union['Character', 'Mob']]] = None):
        """Sends a message to all characters in the room, optionally excluding some."""
        tasks = [
            char.send(message, add_newline=False) 
            for char in self.characters 
            if not exclude or char not in exclude
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def get_character_by_name(self, name: str) -> Optional['Character']:
        """Finds the first character in the room matching their first name (case-insensitive)."""
        name_lower = name.lower()
        for character in self.characters:
            if name_lower == character.first_name.lower():
                return character
        return None
    
    def add_mob(self, mob: 'Mob'):
        self.mobs.add(mob)
        mob.location = self

    def remove_mob(self, mob: 'Mob'):
        self.mobs.discard(mob)

    def get_mob_by_name(self, name_target: str) -> Optional['Mob']:
        """Finds the first living mob instance in the room matching a partial name."""
        name_lower = name_target.lower()
        for mob in self.mobs:
            if mob.is_alive() and name_lower in mob.name.lower():
                return mob
        return None
    
    async def save(self, db_manager: "DatabaseManager"):
        """Saves the room's dynamic state to the database."""
        # This is simple for now but can be expanded for other dynamic state.
        # The main thing we care about is coinage on the ground.
        # Item instance locations are saved separately when they move.
        await db_manager.execute_query(
            "UPDATE rooms SET coinage = $1 WHERE id = $2",
            self.coinage, self.dbid
        )

    async def check_respawn(self, world: "World"):
        """
        Checks for dead mobs in the room and respawns them if their timer has elapsed.
        """
        current_time = time.monotonic()
        # Iterate over a copy of the set as respawning modifies it
        for mob in list(self.mobs):
            if not mob.is_alive() and mob.time_of_death:
                if (current_time - mob.time_of_death) >= mob.respawn_delay:
                    # Instead of creating a new mob, we reset the state of the existing one.
                    mob.respawn()
                    await self.broadcast(f"\r\nA {mob.name} appears!\r\n")
                        
    async def mob_ai_tick(self, dt: float, world: 'World'):
        """Calls the AI tick method for all living mobs in the room."""
        living_mobs = [mob for mob in self.mobs if mob.is_alive()]
        if not living_mobs:
            return

        tasks = [mob.simple_ai_tick(dt, world) for mob in living_mobs]
    
        # Run all AI ticks concurrently and log any that fail
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                mob_name = getattr(living_mobs[i], 'name', 'Unknown Mob')
                log.exception("Room %d: Exception in AI tick for mob '%s'", self.dbid, mob_name)
        
    async def add_coinage(self, amount: int, world: 'World') -> bool:
        """Adds or removes coinage from the room's cache and the database."""
        if amount == 0: return True
        
        status = await world.db_manager.execute_query("UPDATE rooms SET coinage = GREATEST(0, coinage + $1) WHERE id = $2", amount, self.dbid)
        if "UPDATE 1" in status:
            self.coinage = max(0, self.coinage + amount)
            return True
        return False

    def get_object_by_keyword(self, keyword: str) -> Optional[Dict[str, Any]]:
        """Finds the first object in the room matching a keyword (case-insensitive)."""
        keyword_lower = keyword.lower()
        for obj_data in self.objects:
            if keyword_lower in (obj_data.get("keywords") or []):
                return obj_data
        return None

    def __repr__(self) -> str:
        return f"<Room {self.dbid}: '{self.name}'>"