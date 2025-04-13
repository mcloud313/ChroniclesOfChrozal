# game/room.py
"""
Defines the Room class.
Represents a Room in the game world.
"""
import time
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
    import aiosqlite
    

log = logging.getLogger(__name__)

class Room:
    """
    Represents a single location in the game world.
    """
    def __init__(self, db_data: Dict[str, Any]):
        """
        Initializes a Room object from database data. 

        Args:
            db_data: A dictionary-like object (e.g., sqlite3.Row) containing room data
            (id, area_id, name, desc, exits, flags).
        """
        self.dbid: int = db_data['id']
        self.area_id: int = db_data['area_id']
        self.name: str = db_data['name']
        self.description: str = db_data['description']
        self.items: List[int] = []
        self.coinage: int = 0

        #Load exits (JSON string -> dict)
        try:
            # json.loads handles nested dicts/ints automatically
            self.exits: Dict[str, Any] = json.loads(db_data['exits'] or '{}')
        except json.JSONDecodeError:
            log.warning(f"Room {self.dbid}: Could not decode exits JSON: {db_data['exits']}")
            self.exits: Dict[str, int] = {}

        # Load flags (JSON string -> set) - store flags as a list/tuple in JSON
        try:
            # Ensure flags are stored as a list in JSON `[]` not object `{}`
            flags_list = json.loads(db_data['flags'] or '[]')
            self.flags: Set[str] = set(flags_list)
        except json.JSONDecodeError:
            log.warning(f"Room {self.dbid}: Could not decode flags JSON: {db_data['flags']}")
            self.flags: Set[str] = set()

        # Load spawners for MOBs
        try:
            # Example: {"1": {"max_present": 3}} -> MobTemplateID: {details}
            self.spawners: Dict[int, Dict[str, Any]] = json.loads(db_data['spawners'] or '{}')
            # Convert keys from string (JSON standard) to int
            self.spawners = {int(k): v for k, v in self.spawners.items()}
        except (json.JSONDecodeError, TypeError, ValueError):
            log.warning("Room %d: Could not decode spawners JSON: %r", self.dbid, db_data.get('spawners','{}'))
            self.spawners: Dict[int, Dict[str, Any]] = {}


        
        # Runtime attributes
        # Using type 'Any' for now until Character is defined
        self.characters: Set[Any] = set() #Holds character objects currently in room
        self.items: List[int] = [] # Holds item_templates_ids of items on the ground
        self.mobs: Set['Mob'] = set()

    def add_character(self, character: Any):
        """Adds a character object to the room"""
        self.characters.add(character)
        log.debug("ROOM %d STATE: Added %s. Current characters: %s",
            self.dbid, character.name, {c.name for c in self.characters})
    
    def remove_character(self, character: Any):
        """Removes a character object from the room"""
        self.characters.discard(character) # discard doesn't raise error if not found
        log.debug("ROOM %d STATE: Removed %s. Remaining characters: %s",
            self.dbid, character.name, {c.name for c in self.characters})

    def get_look_string(self, looker_character: Any, world: 'World') -> str:
        """
        Generates the formatted string describing the room essentials:
        Name, Area, Description (wrapped), Exits, Characters, Mobs.
        Item/Coin listing is handled by the look command itself.

        Args:
            looker_character: The character performing the look (to exclude from lists).
            world: The World object needed to look up area names.

        Returns:
            Formatted string of the room's appearance.
        """
        # --- Room Name & Area Name ---
        area_name = "Unknown Area"
        area_data = world.get_area(self.area_id)
        if area_data:
            try: # Add try/except for safety in case 'name' column is missing
                area_name = area_data['name'] # Use ['name'] instead of .get('name')
            except KeyError:
                log.warning("Area data for ID %s is missing 'name' key.", self.area_id)

        # Use textwrap for description (width 79 for standard 80-col terminals)
        wrapped_desc = textwrap.fill(self.description, width=79)

        output_lines = [
            f"[{self.name}, {area_name}] [{self.dbid}]", # Added Area Name
            f"{wrapped_desc}", # Wrapped description
        ]

        # --- Exits ---
        std_directions = ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest", "up", "down"]
        visible_std_exits = []
        visible_special_exits = []

        for exit_name in sorted(self.exits.keys()):
            # TODO: Add hidden exit checks later
            lc_exit = exit_name.lower()
            if lc_exit in std_directions:
                visible_std_exits.append(exit_name.capitalize())
            else:
                visible_special_exits.append(exit_name.title())

        visible_std_exits.sort(key=lambda x: std_directions.index(x.lower()) if x.lower() in std_directions else 99)
        exit_list = visible_std_exits + visible_special_exits

        output_lines.append(f"[Exits: {', '.join(exit_list) if exit_list else 'none'}]")

        # --- Characters ---
        other_character_names = sorted([
            getattr(char, 'name', 'Someone')
            for char in self.characters
            if char != looker_character
        ])
        if other_character_names:
            output_lines.append("Also Here: " + ", ".join(other_character_names) + ".")

        # --- Mobs ---
        living_mob_names = sorted([
            mob.name.capitalize() # Use display name
            for mob in self.mobs
            if mob.is_alive()
        ])
        if living_mob_names:
            # Group identical mobs
            mob_counts = {}
            for name in living_mob_names:
                mob_counts[name] = mob_counts.get(name, 0) + 1
            formatted_mob_list = []
            for name, count in mob_counts.items():
                formatted_mob_list.append(f"{name}" + (f" (x{count})" if count > 1 else ""))
            output_lines.append("Visible Creatures: " + ", ".join(formatted_mob_list) + ".")

        # Join all parts with MUD newlines
        return "\n\r".join(output_lines)
    
    async def broadcast(self, message: str, exclude: Optional[Set[Any]] = None):
        """
        Sends a message to all characters in the room, optionally excluding some.

        Args:
            message: The string message to send. MUST include line endings if needed.
            exclude: A set of Character objects to NOT send the message to.
        """
        if exclude is None:
            exclude = set()

        # Make a copy of the set in case it changes during iteration
        characters_to_message = self.characters.copy()
        
        for character in characters_to_message:
            if character not in exclude:
                try:
                    # Assumes character object has a 'send' method
                    await character.send(message)
                except AttributeError:
                    log.error(f"Room {self.dbid}: Tried to broadcast to object without send method: {character} ")
                except Exception as e:
                    # Catch potential errors during send (e.g., connection closed)
                    log.error(f"Room {self.dbid}: Error broadcasting to {getattr(character, 'name', '?')}: {e}", exc_info=True)
                    # Optional: Consider removing character from room if send fails repeatedly?

    def get_character_by_name(self, name: str) -> Optional[Any]:
        """
        Finds the first character in the room matching the given name (case-insensitive)

        Args:
            name: The name to search for.

        Returns: 
            The Character object if found, otherwise None.
        """
        name_lower = name.lower()
        for character in self.characters:
            # Access the first_name attribute instead of name
            first_name = getattr(character, 'first_name', None)
            if first_name and first_name.lower() == name_lower:
                return character
        return None
    
    def __str__(self) -> str:
        return f"Room(dbid={self.dbid}, name='{self.name}')"
    
    def __repr__(self) -> str:
        return f"<Room {self.dbid}: '{self.name}'>"
    
    def add_mob(self, mob: 'Mob'):
        """Adds a Mob instance to the room."""
        self.mobs.add(mob)
        mob.location = self # Ensure mob knows its location
        log.debug("Mob %d (%s) added to Room %d", mob.instance_id, mob.name, self.dbid)

    def get_mob_by_name(self, name_target: str) -> Optional['Mob']:
        """Finds the first mob instance in the room matching name (case-insensitive, partial)."""
        name_lower = name_target.lower()
        for mob in self.mobs:
            # Check if target name is in the mob's full name (e.g., "rat" in "a giant rat")
            if mob.is_alive() and name_lower in mob.name.lower():
                return mob
        return None

    def remove_mob(self, mob: 'Mob'):
        """Removes a Mob instance from the room."""
        self.mobs.discard(mob)
        log.debug("Mob %d (%s) removed from Room %d", mob.instance_id, mob.name, self.dbid)

    # --- Add Respawn Check Method ---
    async def check_respawn(self, current_time: float):
        """Checks dead mobs in the room and respawns them if timer elapsed."""
        # In V1, we just check mobs already in self.mobs that are dead
        mobs_to_respawn = [mob for mob in self.mobs if not mob.is_alive()]

        if not mobs_to_respawn:
            return # No dead mobs to check
        log.debug("Room %d: Checking %d dead mobs for respawn.", self.dbid, len(mobs_to_respawn))

        respawned_count = 0
        for mob in mobs_to_respawn:
            log.debug("RESPAWN CHECK: Mob %d (%s) time_of_death is: %s",
                mob.instance_id, mob.name, mob.time_of_death)
            
            if mob.time_of_death: # Ensure time_of_death is set
                time_since_death = current_time - mob.time_of_death
                respawn_ready = time_since_death >= mob.respawn_delay
                log.debug("Mob %d (%s): Dead for %.1f sec. Needs %d sec. Ready: %s",
                    mob.instance_id, mob.name, time_since_death, mob.respawn_delay, respawn_ready)
                if respawn_ready:
                    mob.respawn() # Reset mob's state
                    respawned_count += 1
                # Announce respawn? Optional, can be noisy.
                    await self.broadcast(f"\r\nA {mob.name} suddenly appears!\r\n") # Example broadcast
                
            else:
                log.warning("Mob %d (%s) is dead but has no time_of_death set!", mob.instance_id, mob.name)
        if respawned_count > 0:
            log.debug("Room %d: Respawned %d mobs.", self.dbid, respawned_count)

    # --- Add Mob AI Tick Method ---
    async def mob_ai_tick(self, dt: float, world: 'World'):
        """Calls the AI tick method for all living mobs in the room."""
        living_mobs = [mob for mob in list(self.mobs) if mob.is_alive()] # Copy list
        if not living_mobs: return

        tasks = [asyncio.create_task(mob.simple_ai_tick(dt, world)) for mob in living_mobs]
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    mob_name = getattr(living_mobs[i], 'name', '?')
                    log.exception("Room %d: Exception in AI tick for mob '%s': %s", self.dbid, mob_name, result, exc_info=result)

    async def add_item(self, item_template_id: int, world: 'World'):
        """Adds item to room cache AND database."""
        db_conn = world.db_conn
        success_id = await database.add_item_to_room(db_conn, self.dbid, item_template_id)
        if success_id:
            self.items.append(item_template_id) # Update cache
            log.debug("Added item template %d to room %d (DB id %s)", item_template_id, self.dbid, success_id)
            return True
        else:
            log.error("Failed to add item template %d to room %d in DB.", item_template_id, self.dbid)
            return False
        
    async def remove_item(self, item_template_id: int, world: 'World') -> bool:
        """Removes ONE item instance from room cache AND database."""
        if item_template_id not in self.items:
            log.warning("Attempted to remove item template %d from room %d, but not found in cache.", item_template_id, self.dbid)
            return False
        db_conn = world.db_conn

        rowcount = await database.remove_item_from_room(db_conn, self.dbid, item_template_id)
        # --- V V V Modified Rowcount Check V V V ---
        # Treat any positive rowcount as likely success due to observed anomaly
        if rowcount is not None and rowcount > 0:
            try:
                self.items.remove(item_template_id) # Remove from cache
                log.debug("Removed item template %d from room %d (DB rowcount: %s)",
                        item_template_id, self.dbid, rowcount) # Log actual count
                return True
            except ValueError:
                log.error("Item template %d existed in cache check but remove failed!", item_template_id)
                return False # State mismatch
        elif rowcount == 0:
            log.error("Failed to remove item template %d from room %d in DB (not found). Cache mismatch?", item_template_id, self.dbid)
            # Force remove from cache if DB says it's not there?
            if item_template_id in self.items: self.items.remove(item_template_id)
            return False
        else: # None (DB error) or unexpected rowcount (like 0 or negative?)
            log.error("Error removing item template %d from room %d in DB (DB function returned: %s).", item_template_id, self.dbid, rowcount)
            return False
        
    async def add_coinage(self, amount: int, world: 'World') -> bool:
        """Adds coinage to room cache AND database."""
        print(f"!!! DEBUG ADD_COINAGE: Received world type: {type(world)}, world object: {repr(world)} !!!")
        if amount <= 0: return False
        db_conn = world.db_conn
        rowcount = await database.update_room_coinage(db_conn, self.dbid, amount)
        if rowcount == 1:
            self.coinage += amount # Update cache
            log.debug("Added %d coinage to room %d (New total: %d)", amount, self.dbid, self.coinage)
            return True
        else:
            log.error("Failed to update coinage for room %d in DB (rowcount: %s).", self.dbid, rowcount)
            return False