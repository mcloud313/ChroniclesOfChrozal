# game/world.py
"""
Manages the game world's loaded state, including rooms, mobs, and active players.
This class also contains the core callback functions for the game ticker.
"""
import time
import logging
import json
import aiosqlite
import asyncio  # <-- FIX: Added missing import
import config   # <-- FIX: Added missing import
from typing import Dict, Any, Optional, List, Union

from . import database
from .room import Room
from .character import Character
from .mob import Mob
from . import utils
from .definitions import abilities as ability_defs
from . import combat

log = logging.getLogger(__name__)

class World:
    """
    Holds the currently loaded game world data and orchestrates ticker-driven updates.
    """
    def __init__(self, db_conn: aiosqlite.Connection):
        self.db_conn: aiosqlite.Connection = db_conn
        self.areas: Dict[int, aiosqlite.Row] = {}
        self.rooms: Dict[int, Room] = {}
        self.races: Dict[int, aiosqlite.Row] = {}
        self.classes: Dict[int, aiosqlite.Row] = {}
        self.item_templates: Dict[int, aiosqlite.Row] = {}
        self.mob_templates: Dict[int, aiosqlite.Row] = {} # Added for consistency
        self.active_characters: Dict[int, Character] = {}
        log.info("World object initialized.")

    async def build(self):
        """
        Loads all game data from the database to build the live world state.
        This includes areas, rooms, templates, and initial mob spawns.
        """
        log.info("Building world state from database...")
        db_conn = self.db_conn
        if not db_conn:
            log.critical("World object has no valid db_conn to build from!")
            return False

        load_success = True
        try:
            # --- Load Template Data First ---
            log.info("Loading templates...")
            self.areas = {row['id']: row for row in await database.load_all_areas(db_conn) or []}
            self.races = {row['id']: row for row in await database.load_all_races(db_conn) or []}
            self.classes = {row['id']: row for row in await database.load_all_classes(db_conn) or []}
            self.item_templates = {row['id']: row for row in await database.load_all_item_templates(db_conn) or []}
            self.mob_templates = {row['id']: row for row in await database.get_mob_templates(db_conn) or []} # Use get_mob_templates
            log.info("Loaded %d areas, %d races, %d classes, %d item templates, %d mob templates.",
                     len(self.areas), len(self.races), len(self.classes), len(self.item_templates), len(self.mob_templates))

            # --- Load Rooms & Initial State ---
            log.info("Loading rooms and their initial state...")
            room_rows = await database.load_all_rooms(db_conn)
            if not room_rows:
                log.error("Failed to load rooms or no rooms found in database.")
                return False

            # First Pass: Instantiate all Room objects.
            for row_data in room_rows:
                try:
                    room = Room(dict(row_data))
                    self.rooms[room.dbid] = room
                except Exception as e:
                    log.exception("Failed to instantiate Room object for dbid %d: %s", row_data.get('id', '?'), e)
                    load_success = False
            if not load_success: return False

            # Second Pass: Populate rooms with items, objects, and mobs.
            for room in self.rooms.values():
                room.items = await database.load_items_for_room(db_conn, room.dbid) or []
                room.coinage = await database.load_coinage_for_room(db_conn, room.dbid) or 0
                
                loaded_objects = await database.load_objects_for_room(db_conn, room.dbid)
                if loaded_objects:
                    temp_objects = []
                    for obj_row in loaded_objects:
                        obj_dict = dict(obj_row)
                        try:
                            obj_dict['keywords'] = json.loads(obj_dict.get('keywords', '[]') or '[]')
                        except json.JSONDecodeError:
                            obj_dict['keywords'] = []
                        temp_objects.append(obj_dict)
                    room.objects = temp_objects

            log.info("Loaded initial state for %d rooms.", len(self.rooms))

            # Third Pass: Spawn initial mobs into their rooms.
            initial_mob_count = 0
            for room in self.rooms.values():
                for template_id, spawn_info in room.spawners.items():
                    max_present = spawn_info.get("max_present", 1)
                    mob_template = self.mob_templates.get(template_id)
                    if mob_template:
                        for _ in range(max_present):
                            mob_instance = Mob(dict(mob_template), room)
                            room.add_mob(mob_instance)
                            initial_mob_count += 1
                    else:
                        log.warning("Room %d spawner refers to non-existent mob template ID %d.", room.dbid, template_id)
            log.info("Spawned %d initial mobs.", initial_mob_count)

        except Exception:
            log.exception("A critical error occurred during the world build process.")
            load_success = False

        if load_success:
            log.info("World build complete.")
        else:
            log.error("World build failed. Check previous errors.")

        return load_success
    
    # --- Getters ---
    def get_room(self, room_id: int) -> Optional[Room]:
        return self.rooms.get(room_id)
    
    def get_area(self, area_id: int) -> Optional[aiosqlite.Row]:
        return self.areas.get(area_id)
    
    def get_race_name(self, race_id: Optional[int]) -> str:
        if race_id is None: return "Unknown"
        race_data = self.races.get(race_id)
        return race_data['name'] if race_data else "Unknown"

    def get_class_name(self, class_id: Optional[int]) -> str:
        if class_id is None: return "Unknown"
        class_data = self.classes.get(class_id)
        return class_data['name'] if class_data else "Unknown"

    def get_item_template(self, template_id: int) -> Optional[aiosqlite.Row]:
        return self.item_templates.get(template_id)

    def get_mob_template(self, template_id: int) -> Optional[aiosqlite.Row]:
        return self.mob_templates.get(template_id)

    # --- Active Character Management ---
    def add_active_character(self, character: Character):
        self.active_characters[character.dbid] = character
        log.debug("Character %s added to active list.", character.name)

    def remove_active_character(self, character_id: int) -> Optional[Character]:
        return self.active_characters.pop(character_id, None)
    
    def get_active_character(self, character_id: int) -> Optional[Character]:
        return self.active_characters.get(character_id)
    
    def get_active_characters_list(self) -> List[Character]:
        return list(self.active_characters.values())

    # --- Ticker Callback Functions ---
    async def update_roundtimes(self, dt: float):
        """Ticker: Decrements roundtimes and resolves casting for all participants."""
        all_mobs = [mob for room in self.rooms.values() for mob in room.mobs]
        participants: List[Union[Character, Mob]] = self.get_active_characters_list() + all_mobs

        for p in participants:
            rt_before = p.roundtime
            if rt_before > 0:
                p.roundtime = max(0.0, rt_before - dt)

            if isinstance(p, Character):
                # Clear invalid combat state
                if p.is_fighting and (not p.target or not p.target.is_alive() or p.target.location != p.location):
                    p.is_fighting = False
                    p.target = None
                
                # Resolve finished casting
                if rt_before > 0 and p.roundtime == 0.0 and p.casting_info:
                    info = p.casting_info
                    p.casting_info = None
                    ability_key = info.get("key")
                    ability_data = ability_defs.get_ability_data(ability_key)

                    if not ability_data:
                        log.error("Finished casting unknown ability '%s' for %s.", ability_key, p.name)
                        continue

                    cost = ability_data.get("cost", 0)
                    if p.essence >= cost:
                        p.essence -= cost
                        try:
                            await combat.resolve_ability_effect(p, info.get("target_id"), info.get("target_type"), ability_data, self)
                        except Exception:
                            log.exception("Error resolving ability effect '%s' for %s", ability_key, p.name)
                            await p.send("Something went wrong as your action finished.")
                        
                        base_rt = ability_data.get("roundtime", 1.0)
                        # Armor penalty for spell recovery, using a simpler formula
                        rt_penalty = p.get_total_av(self) * 0.05 # 0.05s per point of AV
                        p.roundtime = base_rt + rt_penalty
                    else:
                        await p.send(f"{{RYou lose focus ({ability_data.get('name', ability_key)}) - not enough essence!{{x")

    async def update_mob_ai(self, dt: float):
        """Ticker: Ticks AI for all mobs in all loaded rooms."""
        tasks = [room.mob_ai_tick(dt, self) for room in self.rooms.values()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def update_respawns(self, dt: float):
        """Ticker: Checks for and processes mob respawns."""
        current_time = time.monotonic()
        tasks = [room.check_respawn(current_time) for room in self.rooms.values()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def update_death_timers(self, dt: float):
        """Ticker: Checks dying characters and transitions them to DEAD."""
        current_time = time.monotonic()
        dying_chars = [char for char in self.get_active_characters_list() if char.status == 'DYING']

        for char in dying_chars:
            if char.death_timer_ends_at and current_time >= char.death_timer_ends_at:
                log.info("Character %s death timer expired.", char.name)
                char.status = "DEAD"
                char.death_timer_ends_at = None
                
                initial_tether = char.spiritual_tether
                char.spiritual_tether = max(0, initial_tether - 1)
                log.info("Character %s tether decreased from %d to %d.", char.name, initial_tether, char.spiritual_tether)
                await char.send("{RYour connection to the living world weakens...{x")
                
                if char.spiritual_tether <= 0:
                    log.critical("!!! PERMANENT DEATH: Character %s (ID: %s) has reached 0 spiritual tether!", char.name, char.dbid)
                    await char.send("{R*** Your soul feels irrevocably severed! ***{x")
                
                await self.respawn_character(char)

    async def respawn_character(self, character: Character):
        """Handles moving a character to their respawn point and resetting their state."""
        respawn_room_id = 1 # Fallback to room 1
        respawn_room = self.get_room(respawn_room_id)
        if not respawn_room:
            log.critical("!!! Respawn Room ID %d not found! Cannot respawn %s.", respawn_room_id, character.name)
            await character.send("Your soul cannot find its way back... (Respawn room missing!)")
            return

        old_room = character.location
        if old_room and old_room != respawn_room:
            old_room.remove_character(character)

        character.update_location(respawn_room)
        respawn_room.add_character(character)
        character.respawn()

        await character.send("\r\n{WYou feel yourself drawn back to the mortal plane...{x")
        look_string = respawn_room.get_look_string(character, self)
        await character.send(look_string)

    async def update_effects(self, dt: float):
        """Ticker: Checks for and removes expired effects on all participants."""
        current_time = time.monotonic()
        all_mobs = [mob for room in self.rooms.values() for mob in room.mobs]
        participants = self.get_active_characters_list() + all_mobs

        for p in participants:
            if not p.effects:
                continue
            
            expired_keys = [key for key, data in p.effects.items() if data.get("ends_at", 0) <= current_time]
            
            for key in expired_keys:
                ability_data = ability_defs.get_ability_data(key)
                del p.effects[key]
                
                if ability_data:
                    target_name = p.name.capitalize()
                    if isinstance(p, Character) and ability_data.get('expire_msg_self'):
                        await p.send(ability_data['expire_msg_self'].format(target_name=target_name))
                    
                    if p.location and ability_data.get('expire_msg_room'):
                        await p.location.broadcast(f"\r\n{ability_data['expire_msg_room'].format(target_name=target_name)}\r\n", exclude={p})

    async def update_xp_absorption(self, dt: float):
        """Ticker: Processes XP pool absorption for characters in node rooms."""
        absorb_this_tick = config.XP_ABSORB_RATE_PER_SEC * dt
        chars_in_nodes = [c for c in self.get_active_characters_list() if c.location and "NODE" in c.location.flags and c.xp_pool > 0]

        for char in chars_in_nodes:
            absorb_amount = min(char.xp_pool, absorb_this_tick)
            char.xp_pool -= absorb_amount
            char.xp_total += absorb_amount
            if char.xp_pool <= 0:
                char.xp_pool = 0
                await char.send("You feel you have absorbed all you can for now.")
    
    async def update_regen(self, dt: float):
        """Ticker: Calls the regeneration logic for all active characters."""
        for char in self.get_active_characters_list():
            is_in_node = char.location and "NODE" in char.location.flags
            char.update_regen(dt, is_in_node)