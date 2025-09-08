# game/room.py
"""
Defines the Room class. Represents a Room in the game world.
"""
import json
import logging
import asyncio
import textwrap
from typing import Set, Dict, Any, Optional, List, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from .character import Character
    from .mob import Mob
    from .world import World

log = logging.getLogger(__name__)

class Room:
    """Represents a single location in the game world."""
    def __init__(self, db_data: Dict[str, Any]):
        self.dbid: int = db_data['id']
        self.area_id: int = db_data['area_id']
        self.name: str = db_data['name']
        self.description: str = db_data['description']
        
        # --- FIX: Robustly load JSONB data ---
        # This logic handles data that may be a string or already a Python object.
        
        exits_data = db_data.get('exits') or {}
        self.exits: Dict[str, Any] = json.loads(exits_data) if isinstance(exits_data, str) else exits_data
        
        flags_data = db_data.get('flags') or []
        self.flags: Set[str] = set(json.loads(flags_data) if isinstance(flags_data, str) else flags_data)
        
        spawners_data = db_data.get('spawners') or {}
        spawners_dict = json.loads(spawners_data) if isinstance(spawners_data, str) else spawners_data
        self.spawners: Dict[int, Dict[str, Any]] = {int(k): v for k, v in spawners_dict.items()}
        
        # Runtime attributes, populated by World.build()
        self.characters: Set['Character'] = set()
        self.mobs: Set['Mob'] = set()
        self.items: List[int] = []
        self.objects: List[Dict[str, Any]] = []
        self.coinage: int = db_data.get('coinage', 0)
        
    def add_character(self, character: 'Character'):
        """Adds a character object to the room."""
        self.characters.add(character)
    
    def remove_character(self, character: 'Character'):
        """Removes a character object from the room."""
        self.characters.discard(character)

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

        other_chars = sorted([c.name for c in self.characters if c != looker])
        if other_chars:
            output_lines.append("Also Here: " + ", ".join(other_chars) + ".")

        mob_counts = {}
        for mob in self.mobs:
            if mob.is_alive():
                mob_counts[mob.name] = mob_counts.get(mob.name, 0) + 1
        if mob_counts:
            formatted_mob_list = [f"{name.capitalize()}" + (f" (x{count})" if count > 1 else "") for name, count in sorted(mob_counts.items())]
            output_lines.append("Visible Creatures: " + ", ".join(formatted_mob_list) + ".")

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

    async def check_respawn(self, current_time: float):
        """Checks dead mobs in the room and respawns them if their timer has elapsed."""
        for mob in self.mobs:
            if not mob.is_alive() and mob.time_of_death and (current_time - mob.time_of_death) >= mob.respawn_delay:
                mob.respawn()
                await self.broadcast(f"\r\nA {mob.name} suddenly appears!\r\n")
    
    async def mob_ai_tick(self, dt: float, world: 'World'):
        """Calls the AI tick method for all living mobs in the room."""
        living_mobs = [mob for mob in self.mobs if mob.is_alive()]
        tasks = [mob.simple_ai_tick(dt, world) for mob in living_mobs]
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    log.exception("Room %d: Exception in AI tick for mob '%s'", self.dbid, getattr(living_mobs[i], 'name', '?'))

    async def add_item(self, item_template_id: int, world: 'World') -> bool:
        """Adds an item to the room's cache and the database."""
        status = await world.db_manager.execute_query("INSERT INTO room_items (room_id, item_template_id) VALUES ($1, $2)", self.dbid, item_template_id)
        if "INSERT 0 1" in status:
            self.items.append(item_template_id)
            return True
        return False
        
    async def remove_item(self, item_template_id: int, world: 'World') -> bool:
        """Removes ONE item instance from the room's cache and the database."""
        if item_template_id not in self.items:
            return False
        
        status = await world.db_manager.execute_query("DELETE FROM room_items WHERE id = (SELECT id FROM room_items WHERE room_id = $1 AND item_template_id = $2 LIMIT 1)", self.dbid, item_template_id)
        if "DELETE 1" in status:
            try:
                self.items.remove(item_template_id)
                return True
            except ValueError:
                return False
        return False
        
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