# game/room.py
"""
Defines the Room class.
Represents a Room in the game world.
"""
import json
import logging
from typing import Set, Dict, Any, Optional

# Since character class doesn't exist yet, we use a foward reference string
# Or just use 'Any' for now if type hitning isn't strictly needed yet.
# from typing import TYPE_CHECKING
# if TYPE_CHECKING:
#   from .character import Character # Assuming character.py will exist

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
        self.dbid int = db_data['id']
        self.area_id int = db_data['area_id']
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
        
        # Runtime attributes
        # Using type 'Any' for now until Character is defined
        self.characters Set[Any] = set() #Holds character objects currently in room

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
        Generates the formatted string describing the room for a looking character.

        ArgS:
            looker_character: The character object looking at the room.

        returns: 
            A formatted string describing the room.
        """
        # TODO: Add logic based on flags (darkness, weather) and looker abilities (infravision)
        if "dark" in self.flags: # Example flag usage
            # Simplistic dark check - assumes no light source yet
            pass # return "It is pitch black..."

        # --- Room Name ---
        output = f"---{self.name} --- [{self.dbid}]\n" # Show room ID for debugging/building

        # --- Description ---
        output += f"{self.description}\n"

        # --- Exits ---
        visible_exits = sorted(self.exits.keys())
        if visible_exits:
            output += f"[Exits: {', '.join(visible_exits)}]\n"
        else:
            output += "[Exits: none]\n"

        # --- Characters ---
        # Get names of OTHER characters present 
        other_character_names = [ 
            getattr(char, 'name', 'Someone') # Use getattr for safety until Character defined
            for char in self.characters
            if char != looker_character
        ]

        if other_character_names:
            output += "Also here: " + ", ".join(other_character_names) + ".\n"
        # Consider adding NPCs/Mobs here later too

        return output
    
    def broadcast(self, message: str, exclude: Optional[Set[Any]] = None):
        """
        Sends a message to all characters in the room, optionally excluding some.

        Args:
            message: The string message to send.
            exclude: A set of characters objects to NOT send the message to.
                Defaults to None (send to all).
        """
        if exclude is None:
            exclude = set()

        # Make a copy of the set in case it changes during iteration
        characters_to_message = self.characters.copy()
        
        for character in characters_to_message:
            if character not in exclude:
                try:
                    # Assumes character object has a 'send' method
                    getattr(character, 'send')(message)
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
            first_name = getattr(character, 'first_name' None)
            if first_name and first_name.lower() == name_lower:
                return character
        return None
    
    def __str__(self) -> str:
        return f"Room(dbid={self.dbid}, name='{self.name}')"
    
    def __repr__(self) -> str:
        return f"<Room {self.dbid}: '{self.name}'>"