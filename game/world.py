"""
Manages the game world's loaded state, including rooms and areas.
"""
import time
import logging
import aiosqlite
import config
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from . import database
from .room import Room
from .character import Character # Assuming character class is defined
from .mob import Mob
from . import utils

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

                            if room.spawners:
                                for template_id_str, spawn_info in room.spawners.items():
                                    try:
                                        template_id = int(template_id_str)
                                        max_present = spawn_info.get("max_present", 1)
                                        # initial_spawn = spawn_info.get("initial_spawn", max_present) #Optional
                                        mob_template = await database.load_mob_template(db_conn, template_id)
                                        if mob_template:
                                            mob_template_dict = dict(mob_template)
                                            # Spawn initial mobs up to max_present
                                            initial_mob_count = 0
                                            for _ in range(max_present):
                                                mob_instance = Mob(mob_template_dict, room)
                                                room.add_mob(mob_instance)
                                                initial_mob_count += 1
                                        else:
                                            log.warning("Room %d spawner references non-existent mob template ID %d.", room.dbid, template_id)
                                    except (ValueError, KeyError, TypeError) as spawn_e:
                                        log.error("Room %d: Error processing spawner data '%s': %s", room.dbid, spawn_info, spawn_e)
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

    async def update_mob_ai(self, dt: float):
        """Ticks AI for all mobs in all loaded rooms."""
        log.debug("World: Updating Mob AI...")
        # Use asyncio.gather for concurrency? Maybe not needed if AI is simple.
        # Let's iterate sequentially for simplicity/predictability first.
        # log.debug("World ticking mob AI...") # Can be very verbose
        for room in list(self.rooms.values()): # Iterate copy
            try:
                await room.mob_ai_tick(dt, self)
            except Exception:
                log.exception("Error ticking AI in Room %d", room.dbid, exc_info=True)

    async def update_respawns(self, dt: float):
        log.debug("World: Checking Respawns...")
        """Checks for and processes mob respawns in all loaded rooms."""
        # log.debug("World checking mob respawns...") # Can be verbose
        current_time = time.monotonic()
        for room in list(self.rooms.values()):
            try:
                await room.check_respawn(current_time)
            except Exception:
                log.exception("Error checking respawns in Room %d", room.dbid, exc_info=True)

    async def update_death_timers(self, dt: float):
        """
        Called by the ticker to check DYING charcters and transition them to DEAD.
        """
        current_time = time.monotonic()
        # Iterate over a copy as respawn modifies the active list
        dying_chars = [char for char in self.get_active_characters_list() if char.status == 'DYING']

        if not dying_chars: return

        log.debug("World: Checking death timers for %d characters...", len(dying_chars))

        for char in dying_chars:
            if char.death_timer_ends_at is None:
                log.error("Character %s is DYING but has no death_timer_ends_at set!", char.name)
                # Set a default timer or move to DEAD? Let's move to DEAD for safety.
                char.status = "DEAD"
                char.death_timer_ends_at = None # Clear just in case
                log.info("Character %s moved to DEAD state due to missing timer.", char.name)
                await self.respawn_character(char) # Trigger respawn immediately
                continue

            if current_time >= char.death_timer_ends_at:
                log.info("Character %s death timer expired.", char.name)
                char.status = "DEAD"
                char.death_timer_ends_at = None # Clear timer

                # Decrement Spiritual Tether
                try:
                    initial_tether = char.spiritual_tether
                    char.spiritual_tether = max(0, initial_tether - 1)
                    log.info("Character %s tether decreased from %d to %d.",
                            char.name, initial_tether, char.spiritual_tether)
                    await char.send("{RYour connection to the living world weakens...{x")
                    
                    # Check for permanent death (V1 just logs)
                    if char.spiritual_tether <= 0:
                        log.critical("!!! PERMANENT DEATH: Character %s (%s, ID: %s) has reached 0 spiritual tether!",
                                    char.name, getattr(char.player, 'username', '?'), char.dbid)
                        # TODO: Implement actual permadeath later (delete char? special state?)
                        await char.send("{R*** Your soul feels irrevocably severed! ***{x") # Color later
                except Exception:
                    log.exception("Error decrementing spiritual tether for %s:", char.name, exc_info=True)

                await self.respawn_character(char)

    async def respawn_character(self, character: Character):
        """Handles moving character to respawn point and resetting state."""
        log.info("Processing respawn for %s...", character.name)

        # 1. Determine Respawn Location (Room 1 for V1)
        respawn_room_id = 1 # TODO: Make configurable or based on player choices later
        respawn_room = self.get_room(respawn_room_id)

        if not respawn_room:
            log.critical("!!! Respawn Room ID %d not found! Cannot respawn %s.", respawn_room_id, character.name)
            # What to do here? Leave them dead? Disconnect? Log critical error.
            await character.send("Your soul cannot find its way back... (Respawn room missing!)")
            # Maybe try default room 1 again? Assume room 1 must exist.
            respawn_room = self.get_room(1)
            if not respawn_room: return # Give up if Room 1 is missing

        # 2. Remove from current location (if any)
        old_room = character.location
        if old_room and old_room != respawn_room:
            log.debug("Removing %s from old room %d before respawn.", character.name, old_room.dbid)
            # Announce departure? "The body of X fades away..."
            # await old_room.broadcast(f"\r\n{character.name}'s form fades away...\r\n", exclude={character})
            old_room.remove_character(character)

        # 3. Move to Respawn Room & Reset State
        character.update_location(respawn_room)
        respawn_room.add_character(character)
        character.respawn() # Calls method on Character object to reset vitals/status

        # 4. Notify Player
        await character.send("{WYou feel yourself drawn back to the mortal plane...{x") # Color later
        # Send look of the respawn room
        look_string = respawn_room.get_look_string(character)
        await character.send(look_string)
        # Optionally broadcast arrival in respawn room? Might be spammy.

    async def update_xp_absorption(self, dt: float):
        """
        Called by the game ticker to process XP pool absorption for character in nodes.

        Args:
            dt: Delta time (Seconds) since the last tick.
        """
        # Use configured rate per second, adjust by delta time
        absorb_rate = getattr(config, 'XP_ABSORB_RATE_PER_SEC', 10)
        xp_to_process_this_tick = absorb_rate * dt

        chars_in_nodes = [
            char for char in self.get_active_characters_list()
            if char.location and "NODE" in char.location.flags and char.xp_pool > 0
        ]

        if not chars_in_nodes:
            return

        # log.debug("Processing XP absorption for %d characters.", len(chars_in_nodes)) # Optiona verbose log
        for char in chars_in_nodes:
            absorb_amount = min(char.xp_pool, xp_to_process_this_tick)
            # Ensure we don't absorb tiny fractions if dt is small? Or allow float? Allow float for now.
            absorb_amount = round(absorb_amount, 3) # Round to avoid tiny floats if needed

            if absorb_amount > 0:
                char.xp_pool -= absorb_amount
                char.xp_total += absorb_amount
                log.debug("Character %s absorbed %.2f XP (Pool: %.2f, Total: %.2f)",
                    char.name, absorb_amount, char.xp_pool, char.xp_total)
                
                # Simple message when pool becomes empty
                if char.xp_pool <= 0:
                    char.xp_pool = 0 #Ensures it doesn't go negative
                    try:
                        await char.send("You feel you have asborbed all you can for now.")
                    except Exception: pass
                
                # Check for level up eligibility
                needed_for_next = utils.xp_needed_for_level(char.level + 1)
                if char.xp_total >= needed_for_next and char.level < config.MAX_LEVEL:
                    # Optional: Send prompt only once per eligibility? Need another flag?
                    # Let's defer the actual prompt/check to the ADVANCE command (Task 2)
                    # or maybe the score command can show "(Ready to Advance!)"
                    pass