# game/character.py
"""
Represents a character in the game world, controlled by a player account.
Holds in-game state, attributes, and connection information.
"""

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Optional, Dict, Any

# Use TYPE_CHECKING block for Room to avoid circular import errors
# This makes the type checker happy but doesn't cause runtime import issues.
if TYPE_CHECKING:
    from .room import Room

log = logging.getLogger(__name__)

class Character:
    """
    Represents an individual character within the game world.
    """
    # hint network connection type
    writer: asyncio.StreamWriter

def __init__(self, writer: asyncio.StreamWriter, db_data: Dict[str, Any]):
    """
    Initializes a Character object from database data and network writer.

    Args:
        writer: the asyncio streamwriter associated with the player's connection.
        db_data: a dictionary-like object (e.g., aiosqlite.Row) containing character
        data from the 'characters' table.
    """
    self.writer: asyncio.StreamWriter = writer # Network connection

    # --- Data loaded from DB ---
    self.dbid: int = db_data['id']
    self.player_id: int = db_data['player_id'] # Link to Player account
    self.first_name: str = db_data['first_name']
    self.last_name: str = db_data['last_name']
    self.race_id: Optional[int] = db_data['race_id'] # Store ID
    self.class_id: Optional[int] = db_data['class_id'] # Store ID
    self.level: int = db_data['level']
    self.hp: int = db_data['hp']
    self.max_hp: int = db_data['max_hp']
    self.essence: int = db_data['essence']
    self.max_essence: int = db_data['max_essence']
    self.xp_pool: int = db_data['xp_pool'] # Unabsorbed XP
    self.xp_total: int = db_data['xp_total'] # Current level progress

    # Load stats (JSON string -> dict)
    try:
        self.stats: Dict[str, int] = json.loads(db_data['stats'] or '{}')
    except json.JSONDecodeError:
        log.warning("Character %s (%s): Could not decode stats JSON: %s",
                    self.dbid, self.first_name, db_data['stats'])
        self.stats: Dict[str, int] = {} # Default to empty if invalid

    # Load skills (JSON string -> dict)
    try:
        self.skills: Dict[str, int] = json.loads(db_data['skills'] or '{}')
    except json.JSONDecodeError:
        log.warning("Character %s (%s): Could not decode skills JSON: %s",
                    self.dbid, self.first_name, db_data['skills'])
        self.skills: Dict[str, int] = {} # Default to empty if invalid

    self.location_id: int = db_data['location_id'] # Store DB location ID

    # --- Runtime Data ---
    # Location is set AFTER initialization by the world/login manager
    # Use forward reference string 'Room' for type hint if not using TYPE_CHECKING
    self.location: Optional['Room'] = None

    # Add basic derived name property
    self.name = f"{self.first_name} {self.last_name}"

    log.debug("Character object initialized for %s (ID: %s)", self.name, self.dbid)

async def send(self, message: str):
    """
    Sends a message string to the character's connected client.
    Appends a newline characters if not present.

    Args:
        message: the string message to send.
    """
    if not self.writer or self.writer.is_closing():
        log.warning("Attempted to send to closed writer for character %s", self.name)
        # TODO: Handle cleanup / mark character for removal?
        return
    
    # Ensure message ends with standard MUD newline (\r\n) for telnet clients
    if not message.endswith('\r\n'):
        if message.endswith('\n'):
            message = message[:-1] + '\r\n'
        elif message.endswith('\r'):
            message = message[:-1] + '\r\n'
        else:
            message += '\r\n'

    try:
        # Encode message to bytes (UTF-8 is standard)
        self.writer.write(message.encode('utf-8'))
        await self.writer.drain() # Wait until buffer has flushed
        log.debug("Sent to %s: %r", self.name, message)
    except (ConnectionResetError, BrokenPipeError) as e:
        log.warning("Network error sending to character %s: %s. Writer closed.", self.name, e)
        # Connection is likely dead, try to close gracefully
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except Exception:
            pass # Ignore errors during close
        # TODO: Trigger player cleanup logic here (remove from room, save, etc.)
    except Exception as e:
        log.exception("Unexpected error sending to character %s", self.name, exc_info=True)

async def save(self):
    """
    Placeholder for saving character state to the database.
    This would call a function like database.save_character_data().
    """
    # TODO: Implement saving logic
    # 1. collect data to save (location_id, hp, xp, stats, skills, etc.)
    # 2. Call await database.save_character_data(self.dbid, data_dict)
    log.debug("Character save() called for %s (Not implemented yet)", self.name)
    pass # Replace with actual save logic later

def update_location(self, new_location: Optional['Room']):
    """
    Updates the character's current location reference.

    Args:
        new_location: The room object the character is now in, or None.
    """
    # TODO: Maybe trigger saving old room state / loading new? For now just update ref.
    old_loc_id = getattr(self.location, 'dbid', None)
    new_loc_id = getattr(new_location, 'dbid', None)
    self.location = new_location
    if new_location:
        self.location_id = new_location.dbid # Keep db id in sync
    log.debug("Character %s location updated from room %s to room %s",
            self.name, old_loc_id, new_loc_id)
    
def __repr__(self) -> str:
        return f"<Character {self.dbid}: '{self.first_name} {self.last_name}'>"

def __str__(self) -> str:
        loc_id = getattr(self.location, 'dbid', self.location_id) # Show current or last known dbid
        return f"Character(id={self.dbid}, name='{self.first_name} {self.last_name}', loc={loc_id})"