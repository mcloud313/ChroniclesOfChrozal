"""
Manages the game world's loaded state, including rooms and areas.
"""

import logging
import aiosqlite
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from . import database
from .room import Room
from .character import Character # Assuming character class is defined

log = logging.getLogger(__name__)

class World:
    """
    Holds the currently loaded game world data (areas, rooms)
    and potentially runtime state (active players, mobs) later.
    """
    def __init__(self):
        # Store raw area data for now, could be Area objects later
        self.areas: Dict[int, aiosqlite.Row] = {}
        self.rooms: Dict[int, Room] = {}
        self.races: Dict[int, aiosqlite.Row] = {}
        self.classes: Dict[int, aiosqlite.Row] = {}
        self.active_characters: Dict[int, Character] = {} # Add this {character_dbid: Character_object
        self.item_templates: Dict[int, aiosqlite.Row] = {}
        # Add containers for active players/mobs later if needed
        log.info("World object initialized.")

    async def build(self, db_conn: aiosqlite.Connection):
        """
        Loads areas and rooms from the database and populates the world.

        Args: 
            db_conn: An active database connection.

        Returns:
            True if successful, False otherwise.
        """
        log.info("Building world state from database...")
        load_success = True

        try:
            item_rows = await database.load_all_item_templates(db_conn)
            if item_rows is None:
                log.error("Failed to load item templates from database.")
                load_success = False
            else:
                self.item_templates = {row['id']: row for row in item_rows}
                log.info("Loaded %d item templates.", len(self.item_templates))
        except Exception as e:
            log.exception("Exception loading item templates: %s", e, exc_info=True)
            load_success = False

        # 1. Load Areas
        try:
            area_rows = await database.load_all_areas(db_conn)
            if area_rows is None:
                log.error("Failed to load areas from database.")
                load_success = False
            else:
                self.areas = {row['id']: row for row in area_rows}
                log.info("Loaded %d areas.", len(self.areas))
        except Exception as e:
            log.exception("Exception loading areas: %s", e, exc_info=True)
            load_success = False

        # 1 - A Load Races
        if load_success:
            try:
                race_rows = await database.load_all_races(db_conn)
                if race_rows is None:
                    log.error("Failed to load races from database.")
                    load_success = False
                else:
                    self.races = {row['id']: row for row in race_rows}
                    log.info("Loaded %d races.", len(self.races))
            except Exception as e:
                log.exception("Exception loading races: %s", e, exc_info=True)
                load_success = False

        # 1 - B Load Classes
        if load_success:
            try:
                class_rows = await database.load_all_classes(db_conn)
                if class_rows is None:
                    log.error("Failed to load classes from database.")
                    load_success = False
                else:
                    self.classes = {row['id']: row for row in class_rows}
                    log.info("Loaded %d classes.", len(self.classes))
            except Exception as e:
                log.exception("Exception loading classes: %s", e, exc_info=True)
                load_success = False

        # 2. Load Rooms (only proceed if areas loaded somewhat successfully)
        if load_success:
            try:
                room_rows = await database.load_all_rooms(db_conn)
                if room_rows is None:
                    log.error("Failed to load rooms from database.")
                    load_success = False
                else:
                    count = 0
                    for row in room_rows:
                        try:
                            # Check if the room's area exists
                            if row['area_id'] not in self.areas:
                                log.warning("Room %d references non-existent area %d. Skipping ", row['id'], row['area_id'])
                                continue
                            #Create room object
                            room = Room(db_data=row)
                            self.rooms[room.dbid] = room
                            count += 1
                        except Exception as e:
                            log.exception("Failed to instantiate Room object for dbid %d: %s", row['id'], e, exc_info=True)
                            load_success = False # Mark load as failed if any room fails.
                    log.info("Loaded and instantiated %d rooms.", count)
            except Exception as e:
                log.exception("Exception loading rooms: %s", e, exc_info=True)
                load_success = False
                
        # Update final log message
        if load_success:
            log.info("World build complete. %d Areas, %d Races, %d Classes, %d Item Templates, %d Rooms loaded.",
                    len(self.areas), len(self.races), len(self.classes), len(self.item_templates), len(self.rooms))
        else:
            log.error("World build failed. Check previous errors.")

        return load_success
    
    def get_room(self, room_id: int) -> Optional[Room]:
        """Safely retrieves a room object by its ID."""
        return self.rooms.get(room_id)
    
    def get_area(self, area_id: int) -> Optional[aiosqlite.Row]:
        """Safely retrieves area data by its ID"""
        # Returns the raw row data for now
        return self.areas.get(area_id)
    
    def get_race_name(self, race_id: Optional[int]) -> str:
        """Safely retrieves a Race name by its ID."""
        if race_id is None: return "Unknown"
        race_data = self.races.get(race_id)
        return race_data['name'] if race_data else "Unknown"

    def get_class_name(self, class_id: Optional[int]) -> str:
        """Safely retrieves a Class name by its ID."""
        if class_id is None: return "Unknown"
        class_data = self.classes.get(class_id)
        return class_data['name'] if class_data else "Unknown"

    def get_item_template(self, template_id: int) -> Optional[aiosqlite.Row]:
        """Safely retrieves Item Template data by its ID."""
        return self.item_templates.get(template_id)

    def add_active_character(self, character: Character):
        """Adds a character to the active list."""
        if character.dbid in self.active_characters:
            log.warning("Character %s (ID: %s) already in active list!", character.name, character.dbid)
        self.active_characters[character.dbid] = character
        log.debug("Character %s added to active list.", character.name)

    def remove_active_character(self, character_id: int):
        """Removes a character from the active list."""
        character = self.active_characters.pop(character_id, None)
        if character:
            log.debug("Character %s removed from active list.", getattr(character, 'name', character_id))
        else:
            log.warning("Attempted to remove non-existent active character ID: %s", character_id)
        # Return the removed character object if needed elsewhere
        return character
    
    def get_active_character(self, character_id: int) -> Optional[Character]:
        """Gets an active character by their ID"""
        return self.active_characters.get(character_id)
    
    def get_active_characters_list(self) -> list[Character]:
        """Returns a list of currently active characters."""
        # Return a copy of the values (the character objects)
        return list(self.active_characters.values())
    
    async def update_roundtimes(self, dt: float):
        """
        Called by the game ticker to decrease active roundtime for characters

        ARGS:
            dt: Delta time (seconds) since the last tick
        """
        # Use a list copy in case characters disconnect during iteration
        active_chars = self.get_active_characters_list()
        if not active_chars:
            return
        # log.debug("updating roundtime for %d characters (dt=%.3f)", len(active_chars)
        for char in active_chars:
            if char.roundtime > 0:
                new_roundtime = char.roundtime - dt
                char.roundtime = max(0.0, new_roundtime) # Decrease, clamp at 0