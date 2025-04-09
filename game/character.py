# game/character.py
"""
Represents a character in the game world, controlled by a player account.
Holds in-game state, attributes, and connection information.
"""

import asyncio
import json
import logging
import aiosqlite
from typing import TYPE_CHECKING, Optional, Dict, Any
from . import database
from . import utils

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

    def __init__(self, writer: asyncio.StreamWriter, db_data: Dict[str, Any], player_is_admin: bool = False):
        """
        Initializes a Character object from database data and network writer.

        Args:
            writer: the asyncio streamwriter associated with the player's connection.
            db_data: a dictionary-like object (e.g., aiosqlite.Row) containing character
            data from the 'characters' table.
        """
        self.writer: asyncio.StreamWriter = writer # Network connection

        # --- Data loaded from DB ---
        self.writer: asyncio.StreamWriter = writer
        self.is_admin: bool = player_is_admin  
        self.dbid: int = db_data['id']
        self.player_id: int = db_data['player_id'] # Link to Player account
        self.first_name: str = db_data['first_name']
        self.last_name: str = db_data['last_name']
        self.sex: str = db_data['sex']
        self.race_id: Optional[int] = db_data['race_id'] # Store ID
        self.class_id: Optional[int] = db_data['class_id'] # Store ID
        self.level: int = db_data['level']
        self.hp: int = db_data['hp']
        self.max_hp: int = db_data['max_hp']
        self.essence: int = db_data['essence']
        self.max_essence: int = db_data['max_essence']
        self.xp_pool: int = db_data['xp_pool'] # Unabsorbed XP
        self.xp_total: int = db_data['xp_total'] # Current level progress
        self.description: str = db_data['description']

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
        self.location: Optional['Room'] = None

        # Roundtime attribute
        self.roundtime: float = 0.0 # Time until next action possible

        # Add basic derived name property
        self.name = f"{self.first_name} {self.last_name}"
        self.calculate_initial_derived_attributes()

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

    async def save(self, db_conn: aiosqlite.Connection):
        """
        Gathers essential character data and saves it to the database.

        Args:
            db_conn: An active aiosqlite connection.
        """
        # Define V1 data to save
        data_to_save = {
            "location_id": self.location_id,
            "hp": self.hp,
            "essence": self.essence,
            "xp_pool": self.xp_pool,
            "xp_total": self.xp_total,
            # Add stats/skills later if they need frequent saving
            # Add inventory/equipment/coinage when implemented
        }

        # Only proceed if there's actually data to save
        if not data_to_save:
            log.warning("Character %s: No data generated to save.", self.name)
            return

        log.debug("Attempting save for character %s (ID: %s)... Data: %s", self.name, self.dbid, data_to_save)
        try:
            # Call the database function (which should now be the dynamic one)
            rowcount = await database.save_character_data(db_conn, self.dbid, data_to_save)

            # Log the outcome based on rowcount
            if rowcount is None:
                # This indicates an error occurred within execute_query/save_character_data
                log.error("Save FAILED for character %s (ID: %s), DB function returned None.", self.name, self.dbid)
            elif rowcount == 1:
                # This is the ideal, expected outcome
                log.info("Successfully saved character %s (ID: %s). 1 row affected.", self.name, self.dbid)
            elif rowcount == 0:
                # This means the WHERE id = ? clause didn't match any rows
                log.warning("Attempted to save character %s (ID: %s), but no rows were updated (ID not found in DB?).", self.name, self.dbid)
            else:
                # Handles the unexpected rowcount=2 (or other non-zero values)
                # Log as info for now, not warning, due to the unresolved issue
                log.info("Save attempt for character %s (ID: %s) completed. DB rowcount reported: %s.",
                        self.name, self.dbid, rowcount)

        except Exception as e:
            # Catch any other unexpected errors during the save process
            # Log the actual exception object 'e'
            log.exception("Unexpected error saving character %s (ID: %s): %s", self.name, self.dbid, e, exc_info=True)

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
    
    def calculate_initial_derived_attributes(self):
        """
        Calculates Max HP/Essence based on current stats and sets current HP/Essence.
        Should be called after stats are loaded/set during __init__ or level up.
        """
        # Get base stats, defaulting to 10 if somehow missing after creation
        # (Shouldn't happen with proper creation sequence)
        might = self.stats.get("might", 10)
        vitality = self.stats.get("vitality", 10)
        agility = self.stats.get("agility", 10)
        intellect = self.stats.get("intellect", 10)
        aura = self.stats.get("aura", 10)
        persona = self.stats.get("persona", 10)

        # Calculate modifiers using the utility function
        mig_mod = utils.calculate_modifier(might)
        vit_mod = utils.calculate_modifier(vitality)
        agi_mod = utils.calculate_modifier(agility)
        int_mod = utils.calculate_modifier(intellect)
        aur_mod = utils.calculate_modifier(aura)
        per_mod = utils.calculate_modifier(persona)

        # Calculate Max HP/Essence based on formulas
        # TODO: Incorporate Level/Race/Class bonuses later
        self.max_hp = 10 + vit_mod
        self.max_essence = aur_mod + per_mod

        # Ensure HP/Essence aren't higher than the new Max values
        # And set current HP/Essence to Max upon initialization/level up usually
        self.hp = self.max_hp
        self.essence = self.max_essence

        log.debug("Character %s: Derived attributes calculated: MaxHP=%d, MaxEssence=%d",
                self.name, self.max_hp, self.max_essence)

    def __repr__(self) -> str:
            return f"<Character {self.dbid}: '{self.first_name} {self.last_name}'>"

    def __str__(self) -> str:
            loc_id = getattr(self.location, 'dbid', self.location_id) # Show current or last known dbid
            return f"Character(id={self.dbid}, name='{self.first_name} {self.last_name}', loc={loc_id})"