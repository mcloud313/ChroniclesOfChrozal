"""
Manages the game world's loaded state, including rooms and areas.
"""

import logging
from typing import Dict, Any, Optional

import aiosqlite

# Import the database functions and Room class using relative paths
from . import database
from .room import Room

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
        # Add containers for active players/mobs later if needed
        # self.active_characters: Dict[int, Character] = {}

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
                
        if load_success:
            log.info("World build complete. %d Areas, %d Rooms loaded.", len(self.areas), len(self.rooms))
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
    
# --- Add methods later for managing active entities ---
# def add_active_character(self, character: Character): ...
# def remove_active_character(self, character_id: int): ...
# def get_active_character(self, character_id: int) -> Optional[Character]: ...