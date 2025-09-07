# game/room.py
"""
Defines the Room class.
Represents a Room in the game world.
"""
import json
import logging
import asyncio
import textwrap
from typing import Set, Dict, Any, Optional, List, TYPE_CHECKING
from . import database

if TYPE_CHECKING:
    from .character import Character
    from .mob import Mob
    from .world import World

log = logging.getLogger(__name__)

class Room:
    """
    Represents a single location in the game world.
    """
    def __init__(self, db_data: Dict[str, Any]):
        """
        Initializes a Room object from database data.
        """
        self.dbid: int = db_data['id']
        self.area_id: int = db_data['area_id']
        self.name: str = db_data['name']
        self.description: str = db_data['description']
        self.objects: List[Dict[str, Any]] = []
        self.items: List[int] = []
        self.coinage: int = 0

        # Load exits (JSON string -> dict)
        try:
            self.exits: Dict[str, Any] = json.loads(db_data.get('exits') or '{}')
        except json.JSONDecodeError:
            log.warning("Room %d: Could not decode exits JSON: %s", self.dbid, db_data.get('exits'))
            self.exits: Dict[str, Any] = {}

        # Load flags (JSON string -> set)
        try:
            flags_list = json.loads(db_data.get('flags') or '[]')
            self.flags: Set[str] = set(flags_list)
        except json.JSONDecodeError:
            log.warning("Room %d: Could not decode flags JSON: %s", self.dbid, db_data.get('flags'))
            self.flags: Set[str] = set()

        # Load spawners for MOBs
        try:
            spawners_dict = json.loads(db_data.get('spawners') or '{}')
            # Convert keys from string (JSON standard) to int for consistency
            self.spawners: Dict[int, Dict[str, Any]] = {int(k): v for k, v in spawners_dict.items()}
        except (json.JSONDecodeError, TypeError, ValueError):
            log.warning("Room %d: Could not decode/process spawners JSON: %r", self.dbid, db_data.get('spawners'))
            self.spawners: Dict[int, Dict[str, Any]] = {}

        # Runtime attributes
        self.characters: Set['Character'] = set()
        self.mobs: Set['Mob'] = set()

    def add_character(self, character: 'Character'):
        """Adds a character object to the room."""
        self.characters.add(character)
        log.debug("ROOM %d STATE: Added %s. Current characters: %s",
            self.dbid, character.name, {c.name for c in self.characters})
    
    def remove_character(self, character: 'Character'):
        """Removes a character object from the room."""
        self.characters.discard(character)
        log.debug("ROOM %d STATE: Removed %s. Remaining characters: %s",
            self.dbid, character.name, {c.name for c in self.characters})

    def get_look_string(self, looker: 'Character', world: 'World') -> str:
        """
        Generates the formatted string describing the room's appearance.
        """
        # --- Room Name & Area Name ---
        area_name = "Unknown Area"
        area_data = world.get_area(self.area_id)
        if area_data:
            area_name = area_data.get('name', f"Area {self.area_id}")

        wrapped_desc = textwrap.fill(self.description, width=79)
        output_lines = [
            f"[{self.name}, {area_name}] [{self.dbid}]",
            f"{wrapped_desc}",
        ]

        # --- Exits ---
        std_dirs = ["north", "south", "east", "west", "up", "down", "northeast", "northwest", "southeast", "southwest"]
        visible_exits = sorted([exit_name for exit_name in self.exits.keys()]) # Basic sort for now
        output_lines.append(f"[Exits: {', '.join(visible_exits) if visible_exits else 'none'}]")

        # --- Characters ---
        other_chars = sorted([c.name for c in self.characters if c != looker])
        if other_chars:
            output_lines.append("Also Here: " + ", ".join(other_chars) + ".")

        # --- Mobs ---
        living_mobs = [mob for mob in self.mobs if mob.is_alive()]
        if living_mobs:
            mob_counts = {}
            for mob in living_mobs:
                mob_counts[mob.name] = mob_counts.get(mob.name, 0) + 1
            
            formatted_mob_list = []
            for name, count in sorted(mob_counts.items()):
                formatted_mob_list.append(f"{name.capitalize()}" + (f" (x{count})" if count > 1 else ""))
            output_lines.append("Visible Creatures: " + ", ".join(formatted_mob_list) + ".")

        # --- Objects ---
        if self.objects:
            object_names = sorted([obj.get('name', 'an object') for obj in self.objects])
            output_lines.append("Objects of interest: " + ", ".join(object_names) + ".")

        return "\r\n".join(output_lines)
    
    async def broadcast(self, message: str, exclude: Optional[Set['Character']] = None):
        """Sends a message to all characters in the room, optionally excluding some."""
        if exclude is None:
            exclude = set()

        # Create a list of tasks to run concurrently
        tasks = []
        for character in self.characters:
            if character not in exclude:
                tasks.append(character.send(message, add_newline=False))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def get_character_by_name(self, name: str) -> Optional['Character']:
        """Finds the first character in the room matching the given name (case-insensitive)."""
        name_lower = name.lower()
        for character in self.characters:
            if character.first_name and name_lower == character.first_name.lower():
                return character
        return None
    
    def add_mob(self, mob: 'Mob'):
        """Adds a Mob instance to the room."""
        self.mobs.add(mob)
        mob.location = self
        log.debug("Mob %d (%s) added to Room %d.", mob.instance_id, mob.name, self.dbid)

    def remove_mob(self, mob: 'Mob'):
        """Removes a Mob instance from the room."""
        self.mobs.discard(mob)
        log.debug("Mob %d (%s) removed from Room %d.", mob.instance_id, mob.name, self.dbid)

    def get_mob_by_name(self, name_target: str) -> Optional['Mob']:
        """Finds the first living mob instance in the room matching a partial name."""
        name_lower = name_target.lower()
        for mob in self.mobs:
            if mob.is_alive() and name_lower in mob.name.lower():
                return mob
        return None

    async def check_respawn(self, current_time: float):
        """Checks dead mobs in the room and respawns them if their timer has elapsed."""
        mobs_to_respawn = [mob for mob in self.mobs if not mob.is_alive() and mob.time_of_death]
        if not mobs_to_respawn:
            return

        for mob in mobs_to_respawn:
            if (current_time - mob.time_of_death) >= mob.respawn_delay:
                mob.respawn()
                await self.broadcast(f"\r\nA {mob.name} suddenly appears!\r\n")
    
    async def mob_ai_tick(self, dt: float, world: 'World'):
        """Calls the AI tick method for all living mobs in the room."""
        living_mobs = [mob for mob in self.mobs if mob.is_alive()]
        if not living_mobs:
            return

        tasks = [mob.simple_ai_tick(dt, world) for mob in living_mobs]
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    mob_name = getattr(living_mobs[i], 'name', '?')
                    log.exception("Room %d: Exception in AI tick for mob '%s'", self.dbid, mob_name)

    async def add_item(self, item_template_id: int, world: 'World') -> bool:
        """Adds an item to the room's cache and the database."""
        success_id = await database.add_item_to_room(world.db_conn, self.dbid, item_template_id)
        if success_id:
            self.items.append(item_template_id)
            return True
        else:
            log.error("Failed to add item template %d to room %d in DB.", item_template_id, self.dbid)
            return False
        
    async def remove_item(self, item_template_id: int, world: 'World') -> bool:
        """Removes ONE item instance from the room's cache and the database."""
        if item_template_id not in self.items:
            log.warning("Attempted to remove item %d from room %d cache, but it wasn't there.", item_template_id, self.dbid)
            return False

        rowcount = await database.remove_item_from_room(world.db_conn, self.dbid, item_template_id)
        
        if rowcount is not None and rowcount > 0:
            try:
                self.items.remove(item_template_id)
                log.debug("Removed item %d from room %d (DB rowcount: %s).", item_template_id, self.dbid, rowcount)
                return True
            except ValueError:
                log.error("DB said item %d was removed from room %d, but it was not in cache to remove!", item_template_id, self.dbid)
                return False # State mismatch
        else:
            log.error("Failed to remove item %d from room %d in DB (rowcount: %s).", item_template_id, self.dbid, rowcount)
            return False
        
    async def add_coinage(self, amount: int, world: 'World') -> bool:
        """Adds or removes coinage from the room's cache and the database."""
        if amount == 0:
            return True
        
        # This debug log replaces the old print() statement.
        log.debug("Updating coinage for room %d by %d from current %d.", self.dbid, amount, self.coinage)
        
        if amount < 0 and abs(amount) > self.coinage:
            log.warning("Attempted to remove %d coinage from Room %d, but only %d is present.", abs(amount), self.dbid, self.coinage)
            return False

        rowcount = await database.update_room_coinage(world.db_conn, self.dbid, amount)
        if rowcount is not None and rowcount > 0:
            self.coinage = max(0, self.coinage + amount)
            log.debug("Updated coinage in room %d. New total: %d.", self.dbid, self.coinage)
            return True
        else:
            log.error("Failed to update coinage for room %d in DB (DB rowcount: %s).", self.dbid, rowcount)
            return False

    def get_object_by_keyword(self, keyword: str) -> Optional[Dict[str, Any]]:
        """Finds the first object in the room matching a keyword (case-insensitive)."""
        keyword_lower = keyword.lower()
        log.debug("Room %d: Searching objects for keyword '%s'.", self.dbid, keyword_lower)
        
        for obj_data in self.objects:
            keywords = obj_data.get("keywords", [])
            log.debug(" -> Checking object '%s' with keywords: %s", obj_data.get("name"), keywords) # Added detailed log
            if keyword_lower in keywords:
                log.debug(" --> Match found!")
                return obj_data
                
        log.debug(" -> No object matched keyword '%s'.", keyword_lower)
        return None

    def __str__(self) -> str:
        return f"Room(dbid={self.dbid}, name='{self.name}')"
    
    def __repr__(self) -> str:
        return f"<Room {self.dbid}: '{self.name}'>"