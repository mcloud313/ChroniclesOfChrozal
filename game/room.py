# game/room.py
"""
Defines the Room class.
Represents a Room in the game world.
"""
import time
import json
import logging
import asyncio
from typing import Set, Dict, Any, Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .character import Character
    from .mob import Mob
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

        #Load exits (JSON string -> dict)
        try:
            self.exits: Dict[str, int] = json.loads(db_data['exits'] or '{}')
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
        log.debug(f"Character {getattr(character, 'name', 'Unknown')} entered Room {self.dbid} ({self.name})")
    
    def remove_character(self, character: Any):
        """Removes a character object from the room"""
        self.characters.discard(character) # discard doesn't raise error if not found
        log.debug(f"Character {getattr(character, 'name', 'Unknown')} left Room {self.dbid} ({self.name})")

    def get_look_string(self, looker_character: Any) -> str:
        """
        Generates the formatted string describing the room, including sorted exits.
        """
        # --- Room Name ---
        output = f"--- {self.name} --- [{self.dbid}]\n\r" # Using \n\r standard newline

        # --- Description ---
        # Consider wrapping long descriptions later
        output += f"{self.description}\n\r"

        # --- Exits ---
        # Define standard order
        std_directions = ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest", "up", "down"]
        visible_std_exits = []
        visible_special_exits = []

        for exit_name in sorted(self.exits.keys()):
            # TODO: Add check here later if exits can be hidden/secret
            if exit_name in std_directions:
                visible_std_exits.append(exit_name.capitalize()) # Capitalize for display
            else:
                visible_special_exits.append(exit_name.title()) # Capitalize words (e.g., "Hole", "Climb Up")

        # Sort standard exits according to our defined order
        visible_std_exits.sort(key=lambda x: std_directions.index(x.lower()) if x.lower() in std_directions else 99)

        exit_list = visible_std_exits + visible_special_exits # Combine lists

        if exit_list:
            output += f"[Exits: {', '.join(exit_list)}]\n\r"
        else:
            output += "[Exits: none]\n\r"

        # --- Characters ---
        other_character_names = [
            getattr(char, 'name', 'Someone')
            for char in self.characters
            if char != looker_character
        ]
        if other_character_names:
            output += "Also here: " + ", ".join(sorted(other_character_names)) + ".\n\r" # Sort names

        living_mob_names = [
            mob.name.capitalize() # Get capitalized name from Mob object
            for mob in self.mobs
            if mob.is_alive() # Only show living mobs
        ]
        if living_mob_names:
            # Add before or after players? After seems common.
            # Could group identical mobs later (e.g., "Three giant rats")
            output += "Visible creatures: " + ", ".join(sorted(living_mob_names)) + ".\n\r"

        # Add Items on Ground
        if self.items:
            # NEed world access to get names! Passworld to this method?
            # For now, just show IDs as a placeholder. Will fix when integrating World.
            # Alternative: The command calls this, then fetches names itself? Yes, better.
            # Command 'look' will get this string, then separately get item names for IDs in room.items
            output += "You also see:\n\r"
            # Group identical items later? For now, just list IDs.
            # We cannot get names here easily without passing 'world'.
            # The 'look' command itself will handle displaying item names.
            # output += ", ".join(f"Item#{item_id}" for item_id in self.items) + ".\n\r"
            output += "Some items lie here.\n\r" # Placeholder text


        return output.strip() # Remove any trailing newline before sending
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

        respawned_count = 0
        for mob in mobs_to_respawn:
            # Check if enough time has passed since death
            if mob.time_of_death and (current_time - mob.time_of_death >= mob.respawn_delay):
                mob.respawn() # Reset mob's state
                # Announce respawn? Optional, can be noisy.
                # await self.broadcast(f"\r\nA {mob.name} suddenly appears!\r\n") # Example broadcast
                respawned_count += 1

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
