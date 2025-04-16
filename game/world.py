"""
Manages the game world's loaded state, including rooms and areas.
"""
import time
import math
import logging
import json
import aiosqlite
import config
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from . import database
from .room import Room
from .character import Character # Assuming character class is defined
from .mob import Mob
from . import utils
#from .definitions import abilities as ability_defs
#from . import combat

log = logging.getLogger(__name__)

class World:
    """
    Holds the currently loaded game world data (areas, rooms)
    and potentially runtime state (active players, mobs) later.
    """
    def __init__(self, db_conn: aiosqlite.Connection):
        # --- Store db_conn ---
        self.db_conn: aiosqlite.Connection = db_conn # <<< Store connection
        # Store raw area data for now, could be Area objects later
        self.areas: Dict[int, aiosqlite.Row] = {}
        self.rooms: Dict[int, Room] = {}
        self.races: Dict[int, aiosqlite.Row] = {}
        self.classes: Dict[int, aiosqlite.Row] = {}
        self.active_characters: Dict[int, Character] = {} # Add this {character_dbid: Character_object
        self.item_templates: Dict[int, aiosqlite.Row] = {}
        # Add containers for active players/mobs later if needed
        log.info("World object initialized.")

    async def build(self): # <<< REMOVED db_conn parameter from signature
        """
        Loads areas, rooms, races, classes, items, spawns mobs using self.db_conn.
        Now uses the connection stored on the World instance.

        Returns:
            True if successful, False otherwise.
        """
        log.info("Building world state from database...")
        # --- V V V Use self.db_conn internally V V V ---
        db_conn = self.db_conn # Get the connection stored during __init__
        if not db_conn: # Safety check
            log.critical("World object has no valid db_conn to build from!")
            return False
        # --- ^ ^ ^ ---

        load_success = True

        # --- Load Areas ---
        try:
            area_rows = await database.load_all_areas(db_conn) # Use local db_conn var
            if area_rows is None: load_success = False; log.error("Failed to load areas.")
            else: self.areas = {row['id']: row for row in area_rows}
            log.info("Loaded %d areas.", len(self.areas))
        except Exception as e: load_success = False; log.exception(...)

        # --- Load Races ---
        if load_success:
            try:
                race_rows = await database.load_all_races(db_conn) # Use local db_conn var
                if race_rows is None: load_success = False; log.error("Failed to load races.")
                else: self.races = {row['id']: row for row in race_rows}
                log.info("Loaded %d races.", len(self.races))
            except Exception as e: load_success = False; log.exception(...)

        # --- Load Classes ---
        if load_success:
            try:
                class_rows = await database.load_all_classes(db_conn) # Use local db_conn var
                if class_rows is None: load_success = False; log.error("Failed to load classes.")
                else: self.classes = {row['id']: row for row in class_rows}
                log.info("Loaded %d classes.", len(self.classes))
            except Exception as e: load_success = False; log.exception(...)

        # --- Load Item Templates ---
        if load_success:
            try:
                item_rows = await database.load_all_item_templates(db_conn) # Use local db_conn var
                if item_rows is None: load_success = False; log.error("Failed to load items.")
                else: self.item_templates = {row['id']: row for row in item_rows}
                log.info("Loaded %d item templates.", len(self.item_templates))
            except Exception as e: load_success = False; log.exception(...)

        # --- Load Rooms & Initial Items/Coins/Mobs and OBJECTS ---
        if load_success:
            try:
                room_rows = await database.load_all_rooms(db_conn) # Use local db_conn var
                if not room_rows:
                    log.error("Failed to load rooms or no rooms found.")
                    load_success = False
                else:
                    self.rooms = {}
                    initial_mob_count = 0
                    item_load_count = 0
                    coin_load_count = 0

                    # First Pass: Create Room objects
                    for row_data in room_rows:
                        room_dict = dict(row_data)
                        try:
                            if room_dict['area_id'] not in self.areas: continue
                            room = Room(db_data=room_dict)
                            self.rooms[room.dbid] = room
                        except Exception as room_e:
                            log.exception("Failed to instantiate Room object for dbid %d: %s", room_dict.get('id','?'), room_e)
                            load_success = False

                    # Second Pass: Load initial items/coins into Room cache
                    log.info("Loading initial items and coinage for %d rooms...", len(self.rooms))
                    for room_id, room in self.rooms.items():
                        try:
                            item_ids = await database.load_items_for_room(db_conn, room_id) # Use local db_conn
                            if item_ids is not None: room.items = item_ids; item_load_count += len(item_ids)
                            else: load_success = False; log.error(...)

                            coinage = await database.load_coinage_for_room(db_conn, room_id) # Use local db_conn
                            if coinage is not None: room.coinage = coinage; coin_load_count += (1 if coinage > 0 else 0)
                            else: load_success = False; log.error(...)

                            loaded_objects = await database.load_objects_for_room(db_conn, room_id)
                            if loaded_objects is not None:
                                temp_objects = []
                                for obj_row in loaded_objects:
                                    obj_dict = dict(obj_row)
                                    # PArse keywords JSON string into list
                                    try: obj_dict['keywords'] = json.loads(obj_dict.get('keywords', '[]') or '[]')
                                    except json.JSONDecodeError: obj_dict['keywords'] = []
                                    temp_objects.append(obj_dict)
                                room.objects = temp_objects # Assign parsed list
                            else: load_success = False; log.error("Failed loading objects for Room %d", room_id)
                        except Exception as load_e: load_success = False; log.exception(...)
                    log.info("Loaded initial state for %d rooms (%d items, %d coin piles > 0).", len(self.rooms), item_load_count, coin_load_count)

                    # Third Pass: Spawn initial mobs
                    log.info("Spawning initial mobs...")
                    for room_id, room in self.rooms.items():
                        if room.spawners:
                            for template_id_str, spawn_info in room.spawners.items():
                                try:
                                    template_id = int(template_id_str)
                                    max_present = spawn_info.get("max_present", 1)
                                    # Load template using local db_conn
                                    mob_template = await database.load_mob_template(db_conn, template_id)
                                    if mob_template:
                                        mob_template_dict = dict(mob_template)
                                        for _ in range(max_present):
                                            mob_instance = Mob(mob_template_dict, room)
                                            room.add_mob(mob_instance)
                                            initial_mob_count += 1
                                    else: log.warning(...)
                                except Exception as spawn_e: log.error(...)
                    log.info("Spawned %d initial mobs.", initial_mob_count)
                    log.info("Loaded and instantiated %d rooms.", len(self.rooms)) # Moved log here

            except Exception as e:
                log.exception("Exception loading rooms/mobs: %s", e)
                load_success = False


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
        """
        from . import combat
        from .definitions import abilities as ability_defs # Also needed here
        # Use a list copy in case characters disconnect during iteration
        active_chars = self.get_active_characters_list()
        if not active_chars:
            return
        # log.debug("updating roundtime for %d characters (dt=%.3f)", len(active_chars)
        for char in active_chars:
            if char.roundtime > 0:
                new_roundtime = char.roundtime - dt
                char.roundtime = max(0.0, new_roundtime) # Decrease, clamp at 0

                if char.roundtime == 0.0 and char.casting_info:
                    # Store info and clear state immediately to prevent re-entry
                    info = char.casting_info
                    char.casting_info = None
                    ability_key = info.get("key")
                    log.debug("Character %s finished casting/using '%s'. Resolving effect.",
                            char.name, ability_key)
                    
                    ability_data = ability_defs.get_ability_data(ability_key)
                    if not ability_data:
                        log.error("Finished casting unknown ability key '%s' for %s.", ability_key, char.name)
                        continue

                    # Check and Deduct Cost
                    cost = ability_data.get("cost", 0)
                    if char.essence >= cost:
                        if cost > 0: char.essence -= cost # Deduce cost now

                        # Resolve the actual effect
                        try:
                            # Pass relevant info to central resolver
                            await combat.resolve_ability_effect(
                                char, info.get("target_id"), info.get("target_type"),
                                ability_data, self
                            )
                        except Exception as e:
                            log.exception("Error resolving ability effect '%s' for %s: %s",
                                        ability_key, char.name, e)
                            await char.send("Something went wrong as your action finished.")
                            # Don't apply post-cast RT on error? Or apply small one? Apply small one.
                            char.roundtime = 0.5
                            continue # Skip normal post-cast RT
                        # Apply post-cast roundtime (recover) + armor penalty
                        base_rt = ability_data.get("roundtime", 1.0)
                        total_av = char.get_total_av(self) # Pass world
                        rt_penalty = math.floor(total_av / 20) * 1.0
                        final_rt = base_rt + rt_penalty
                        char.roundtime = final_rt
                        log.debug("Applied %.1fs post-cast RT to %s for %s (Base: %.1f, AV Pen: %.1f)",
                                final_rt, char.name, ability_key, base_rt, rt_penalty)
                        if rt_penalty > 0:
                            await char.send(f"Recovering from your action takes longer in armor (+{rt_penalty:.1f}s).")

                    else: # Not enough essence
                        log.info("Character %s fizzled '%s' due to insufficient essence.", char.name, ability_key)
                        await char.send(f"You lose focus ({ability_data['name']}) - not enough essence!")
                        char.roundtime = 0.5 # Small fizzle roundtime


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
                        # TODO: Implement actual permadeath later special status can't select character to play
                        await char.send("{R*** Your soul feels irrevocably severed! ***{x") # Color later
                except Exception:
                    log.exception("Error decrementing spiritual tether for %s:", char.name, exc_info=True)

                await self.respawn_character(char)

    async def respawn_character(self, character: Character):
        """Handles moving character to respawn point and resetting state."""
        log.info("Processing respawn for %s...", character.name)

        # 1. Determine Respawn Location (Room 1 for V1)
        respawn_room_id = getattr(config, 'DEFAULT_RESPAWN_ROOM_ID', 1)
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

    async def update_effects(self, dt: float):
        """
        Called by the game ticker to check for and remove expired effects
        on active characters and mobs.
        """
        from .definitions import abilities as ability_defs
        current_time = time.monotonic()
        participants = list(self.active_characters.values())
        for room in self.rooms.values():
            participants.extend(list(room.mobs)) # Include mobs from all rooms

        if not participants: return

        for participant in participants:
            if hasattr(participant, 'effects') and participant.effects:
                #Iterate over a copy of keys as we might modify the dict
                expired_effects = []
                for effect_key, effect_data in list(participant.effects.items()):
                    if effect_data.get("ends_at", 0) <= current_time:
                        expired_effects.append(effect_key)

                if expired_effects:
                    log.debug("Removing expired effects %s from %s", expired_effects, participant.name)
                    for key in expired_effects:
                        effect_data_removed = participant.effects.get(key)
                        del participant.effects[key] # Remove expired effect

                        ability_data = ability_defs.get_ability_data(key)
                        if ability_data:
                            target_name = participant.name.capitalize()
                            msg_self = ability_data.get('expire_msg_self')
                            msg_room = ability_data.get('expire_msg_room')

                            if msg_self and isinstance(participant, Character):
                                try:
                                    await participant.send(msg_self.format(target_name=target_name))
                                except KeyError as e: log.warning(...)

                            # Format and send room message
                            if msg_room and hasattr(participant, 'location') and participant.location:
                                try:
                                    await participant.location.broadcast(
                                        f"\r\n{msg_room.format(target_name=target_name)}\r\n",
                                        exclude={participant} # Exclude the person whose effect wore off
                                    )
                                except KeyError as e: log.warning(...)

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
                    log.info("Character %s XP Pool empty. Sending absorption complete message.", char.name)
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

    async def update_regen(self, dt: float):
        """ Calls update_regen for all active characters. """
        # log.debug("World: Updating Character Regen...") # Can be verbose
        for char in self.get_active_characters_list():
            try:
                # Check if character is in a node room
                is_in_node = char.location and "NODE" in char.location.flags
                char.update_regen(dt, is_in_node) # Call Character's method
            except Exception:
                log.exception("Error updating regen for %s", char.name)