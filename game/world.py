# game/world.py
"""
Manages the game world's loaded state and orchestrates ticker-driven updates.
"""
from __future__ import annotations
import time
import logging
import asyncio
from typing import Dict, Any, Optional, List, Union, TYPE_CHECKING
from itertools import groupby
from operator import itemgetter
from .room import Room
from .character import Character
from .mob import Mob
from .item import Item
from .definitions import abilities as ability_defs
from . import combat
import config

if TYPE_CHECKING:
    from .database import DatabaseManager
    from .group import Group

log = logging.getLogger(__name__)

class World:
    """
    Holds the currently loaded game world data and a reference to the database manager.
    """
    def __init__(self, db_manager: "DatabaseManager"):
        self.db_manager = db_manager
        self.areas: Dict[int, Dict] = {}
        self.rooms: Dict[int, Room] = {}
        self.races: Dict[int, Dict] = {}
        self.classes: Dict[int, Dict] = {}
        self.item_templates: Dict[int, Dict] = {}
        self.mob_templates: Dict[int, Dict] = {}
        self.active_characters: Dict[int, Character] = {}
        self._all_item_instances: Dict[str, Item] = {}
        self.shop_inventories: Dict[int, List[Dict]] = {}
        self.active_groups: Dict[int, 'Group'] = {}
        log.info("World object initialized.")

    async def build(self):
        """
        Loads all game data from the database via the db_manager to build the live world state.
        """
        log.info("Building world state from PostgreSQL database...")
        
        try:
            # Load all template data concurrently for speed
            results = await asyncio.gather(
                self.db_manager.fetch_all("SELECT * FROM areas ORDER BY id"),
                self.db_manager.fetch_all("SELECT * FROM races ORDER BY id"),
                self.db_manager.fetch_all("SELECT * FROM classes ORDER BY id"),
                self.db_manager.fetch_all("SELECT * FROM item_templates ORDER BY id"),
                self.db_manager.fetch_all("SELECT * FROM mob_templates ORDER BY id"),
                self.db_manager.fetch_all("SELECT * FROM rooms ORDER BY id"),
                self.db_manager.fetch_all("SELECT * FROM shop_inventories ORDER BY room_id")
            )
            area_rows, race_rows, class_rows, item_rows, mob_rows, room_rows, shop_rows = results

            self.areas = {row['id']: dict(row) for row in area_rows or []}
            self.races = {row['id']: dict(row) for row in race_rows or []}
            self.classes = {row['id']: dict(row) for row in class_rows or []}
            self.item_templates = {row['id']: dict(row) for row in item_rows or []}
            self.mob_templates = {row['id']: dict(row) for row in mob_rows or []}

            log.info("Loaded %d areas, %d races, %d classes, %d item templates, %d mob templates.",
                     len(self.areas), len(self.races), len(self.classes), len(self.item_templates), len(self.mob_templates))
            
            if shop_rows:
                # Group all shop items by their room_id
                for room_id, items_in_shop in groupby(shop_rows, key=itemgetter('room_id')):
                    # Store the list of item dictionaries for that room
                    self.shop_inventories[room_id] = [dict(item) for item in items_in_shop]
                log.info("Loaded inventories for %d shops.", len(self.shop_inventories))
            
            if not room_rows:
                log.error("Failed to load rooms or no rooms found in database.")
                return False
            
            for row_data in room_rows:
                self.rooms[row_data['id']] = Room(dict(row_data))

            # Populate rooms with their initial state
            for room in self.rooms.values():
                instance_records = await self.db_manager.get_instances_in_room(room.dbid)
                for record in instance_records:
                    instance_data = dict(record)
                    template_data = self.get_item_template(instance_data['template_id'])
                    if template_data:
                        item_obj = Item(instance_data, template_data)
                        room.item_instance_ids.append(item_obj.id)
                        self._all_item_instances[item_obj.id] = item_obj
                        
                object_rows = await self.db_manager.fetch_all("SELECT * FROM room_objects WHERE room_id = $1", room.dbid)
                room.objects = [dict(r) for r in object_rows]
                
                # Spawn initial mobs
                for template_id_str, spawn_info in room.spawners.items():
                    template_id = int(template_id_str)
                    if mob_template := self.mob_templates.get(template_id):
                        for _ in range(spawn_info.get("max_present", 1)):
                            room.add_mob(Mob(mob_template, room))
                    else:
                        log.warning("Room %d spawner refers to non-existent mob template ID %d.", room.dbid, template_id)

            log.info("World build complete. %d rooms loaded and populated.", len(self.rooms))
            return True

        except Exception:
            log.exception("A critical error occurred during the world build process.")
            return False
            
    # --- Getters ---
    def get_room(self, room_id: int) -> Optional[Room]:
        return self.rooms.get(room_id)
        
    def get_shop_inventory(self, room_id: int) -> Optional[List[Dict]]:
        """Returns the cached list of inventory items for a given shop room."""
        return self.shop_inventories.get(room_id)
    
    def get_item_object(self, instance_id: str) -> Optional[Item]:
        """Gets a loaded item instance object from the world cache."""
        return self._all_item_instances.get(instance_id)
    
    def get_area(self, area_id: int) -> Optional[Dict]:
        return self.areas.get(area_id)
    
    def get_race_name(self, race_id: Optional[int]) -> str:
        if race_id is None: return "Unknown"
        race_data = self.races.get(race_id)
        return race_data['name'] if race_data else "Unknown"

    def get_class_name(self, class_id: Optional[int]) -> str:
        if class_id is None: return "Unknown"
        class_data = self.classes.get(class_id)
        return class_data['name'] if class_data else "Unknown"

    def get_item_template(self, template_id: int) -> Optional[Dict]:
        return self.item_templates.get(template_id)

    def get_mob_template(self, template_id: int) -> Optional[Dict]:
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

    # -- Grouping Functions ---
    def add_active_group(self, group: ' Group'):
        """Adds a group to the world's list of active groups."""
        self.active_groups[group.id] = group
        log.debug(f"Group {group.id} created by {group.leader.name} now active.")

    def remove_active_group(self, group_id: int):
        """Removes a group from the active list."""
        if group_id in self.active_groups:
            del self.active_groups[group_id]
            log.debug(f"Group {group_id} removed from active list.")

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
                        rt_penalty = p.get_total_av() * 0.05
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
        respawn_room_id = 1
        respawn_room = self.get_room(respawn_room_id)
        if not respawn_room:
            log.critical("!!! Respawn Room ID %d not found! Cannot respawn %s.", respawn_room_id, character.name)
            return

        if old_room := character.location:
             if old_room != respawn_room:
                 old_room.remove_character(character)

        character.update_location(respawn_room)
        respawn_room.add_character(character)
        character.respawn()

        await character.send("\r\n{WYou feel yourself drawn back to the mortal plane...{x")
        await character.send(respawn_room.get_look_string(character, self))

    async def update_effects(self, dt: float):
        """Ticker: Checks for and removes expired effects on all participants."""
        current_time = time.monotonic()
        all_mobs = [mob for room in self.rooms.values() for mob in room.mobs]
        participants = self.get_active_characters_list() + all_mobs

        for p in participants:
            if not p.effects: continue
            expired_keys = [key for key, data in p.effects.items() if data.get("ends_at", 0) <= current_time]
            
            for key in expired_keys:
                ability_data = ability_defs.get_ability_data(key)
                del p.effects[key]
                if ability_data and p.location:
                    target_name = p.name.capitalize()
                    if isinstance(p, Character) and (msg := ability_data.get('expire_msg_self')):
                        await p.send(msg.format(target_name=target_name))
                    if msg_room := ability_data.get('expire_msg_room'):
                        await p.location.broadcast(f"\r\n{msg_room.format(target_name=target_name)}\r\n", exclude={p})

    async def update_xp_absorption(self, dt: float):
        """Ticker: Processes XP pool absorption for characters in node rooms."""
        absorb_this_tick = config.XP_ABSORB_RATE_PER_SEC * dt
        for char in self.get_active_characters_list():
            if char.location and "NODE" in char.location.flags and char.xp_pool > 0:
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