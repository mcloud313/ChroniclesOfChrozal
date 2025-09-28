# game/world.py
"""
Manages the game world's loaded state and orchestrates ticker-driven updates.
"""
from __future__ import annotations
import time
import json 
import logging
import asyncio
import config
import random   
from typing import Dict, Any, Optional, List, Union, TYPE_CHECKING
from itertools import groupby
from operator import itemgetter
from .room import Room
from .character import Character
from .mob import Mob
from .item import Item
from .definitions import abilities as ability_defs
from .definitions import calendar as calendar_defs
from . import resolver
from . import utils
from . import ticker

if TYPE_CHECKING:
    from .database import DatabaseManager
    from .group import Group

log = logging.getLogger(__name__)

DECAY_CHECK_INTERVAL = 30.0  # Check for decay every 30 seconds

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
        self.pending_invites: Dict[int, int] = {}
        self.active_groups: Dict[int, 'Group'] = {}
        self.dirty_rooms: set[int] = set()
        self.abilities: Dict[str, Dict] = {}
        self.damage_types: Dict[str, Dict] = {}
        self._last_decay_check_time = time.monotonic()
        self.loot_tables: Dict [int, Dict] = {}
        self.loot_table_entries: Dict[int, List[Dict]] = {}
        self.ambient_scripts: List[Dict] = []
        self.game_time_accumulator: float = 0.0
        self.game_minute: int = 0
        self.game_hour: int = calendar_defs.STARTING_HOUR
        self.game_day: int = calendar_defs.STARTING_DAY
        self.game_month: int = calendar_defs.STARTING_MONTH
        self.game_year: int = calendar_defs.STARTING_YEAR


    async def build(self):
        """
        Loads all game data from the new normalized database schema.
        """
        log.info("Building world state from PostgreSQL database...")
        
        try:
            results = await asyncio.gather(
                self.db_manager.fetch_all_query("SELECT * FROM areas ORDER BY id"),
                self.db_manager.fetch_all_query("SELECT * FROM races ORDER BY id"),
                self.db_manager.fetch_all_query("SELECT * FROM classes ORDER BY id"),
                self.db_manager.fetch_all_query("SELECT * FROM item_templates ORDER BY id"),
                self.db_manager.fetch_all_query("SELECT * FROM mob_templates ORDER BY id"),
                self.db_manager.fetch_all_query("SELECT * FROM mob_attacks ORDER BY mob_template_id"),
                self.db_manager.fetch_all_query("SELECT * FROM mob_loot_table ORDER BY mob_template_id"),
                self.db_manager.fetch_all_query("SELECT * FROM rooms ORDER BY id"),
                self.db_manager.fetch_all_query("SELECT * FROM exits ORDER BY source_room_id"),
                self.db_manager.fetch_all_query("SELECT * FROM shop_inventories ORDER BY room_id"),
                self.db_manager.fetch_all_query("SELECT * FROM ability_templates"),
                self.db_manager.fetch_all_query("SELECT * FROM damage_types"),
                self.db_manager.fetch_all_query("SELECT * FROM loot_tables ORDER BY id"),
                self.db_manager.fetch_all_query("SELECT * FROM loot_table_entries ORDER BY loot_table_id"),
                self.db_manager.fetch_all_query("SELECT * FROM ambient_scripts"),
                self.db_manager.get_game_time()
            )
            (area_rows, race_rows, class_rows, item_template_records, mob_rows, attack_rows,
             loot_rows, room_rows, exit_rows, shop_rows, ability_rows, damage_type_rows,
             loot_table_rows, loot_entry_rows, scripts_rows, time_data) = results

            self.areas = {row['id']: dict(row) for row in area_rows or []}
            self.races = {row['id']: dict(row) for row in race_rows or []}
            self.classes = {row['id']: dict(row) for row in class_rows or []}

            if time_data:
                    self.game_year = time_data.get('game_year', calendar_defs.STARTING_YEAR)
                    self.game_month = time_data.get('game_month', calendar_defs.STARTING_MONTH)
                    self.game_day = time_data.get('game_day', calendar_defs.STARTING_DAY)
                    self.game_hour = time_data.get('game_hour', calendar_defs.STARTING_HOUR)
                    self.game_minute = time_data.get('game_minute', 0)

            for record in item_template_records:
                stats_data = record.get('stats')
                parsed_stats = {}
                # Check if the stats data is a string that needs parsing.
                if isinstance(stats_data, str) and stats_data:
                    try:
                        parsed_stats = json.loads(stats_data)
                    except json.JSONDecodeError:
                        log.warning("Malformed JSON in stats for item template %d", record['id'])
                elif isinstance(stats_data, dict):
                    parsed_stats = stats_data # It's already a dictionary, so we can use it directly.
                
                # Create a new, mutable version of the record
                mutable_record = dict(record)
                # Replace the original stats string with our parsed dictionary
                mutable_record['stats'] = parsed_stats
                # Store the corrected blueprint in the world's item template library
                self.item_templates[record['id']] = mutable_record

            self.mob_templates = {row['id']: dict(row) for row in mob_rows or []}
            self.abilities = {row['internal_name']: dict(row) for row in ability_rows or []}

            if ability_rows:
                for row in ability_rows:
                    ability_dict = dict(row)
                    try:
                        # The database driver returns JSONB as strings, so we must parse them.
                        ability_dict['class_req'] = json.loads(ability_dict.get('class_req', '[]'))
                        ability_dict['effect_details'] = json.loads(ability_dict.get('effect_details', '{}'))
                        ability_dict['messages'] = json.loads(ability_dict.get('messages', '{}'))
                    except (json.JSONDecodeError, TypeError):
                        log.error(f"Could not parse JSON for ability: {ability_dict.get('internal_name')}")
                        ability_dict['class_req'] = []
                        ability_dict['effect_details'] = {}
                        ability_dict['messages'] = {}
                    self.abilities[ability_dict['internal_name']] = ability_dict

            self.damage_types = {row['name']: dict(row) for row in damage_type_rows or []}

            for template in self.mob_templates.values():
                template['attacks'] = []
                template['loot_table'] = [] 
            
            if attack_rows:
                for mob_id, attacks in groupby(attack_rows, key=itemgetter('mob_template_id')):
                    if mob_id in self.mob_templates:
                        self.mob_templates[mob_id]['attacks'] = [dict(a) for a in attacks]
            
            if loot_rows:
                for mob_id, loot_items in groupby(loot_rows, key=itemgetter('mob_template_id')):
                    if mob_id in self.mob_templates:
                        self.mob_templates[mob_id]['loot_table'] = [dict(i) for i in loot_items]

            if not room_rows:
                log.error("No rooms found in database. World build failed.")
                return False
            
            for row_data in room_rows:
                room = Room(dict(row_data))
                self.rooms[room.dbid] = room

            is_currently_night = self.is_night()
            for room in self.rooms.values():
                # FIX: Add 'and "LIT" not in room.flags' to the condition
                if "OUTDOORS" in room.flags and "LIT" not in room.flags:
                    if is_currently_night:
                        room.flags.add("DARK")
                    else:
                        room.flags.discard("DARK")

            if exit_rows:
                for room_id, exits in groupby(exit_rows, key=itemgetter('source_room_id')):
                    if room_id in self.rooms:
                        self.rooms[room_id].exits = {
                            exit_row['direction']: dict(exit_row) for exit_row in exits
                        }

            if shop_rows:
                for room_id, items in groupby(shop_rows, key=itemgetter('room_id')):
                    if room_id in self.rooms:
                        self.shop_inventories[room_id] = [dict(i) for i in items]
            
            self.loot_tables = {row['id']: dict(row) for row in loot_table_rows or []}
            if loot_entry_rows:
                for table_id, entries in groupby(loot_entry_rows, key=itemgetter('loot_table_id')):
                    if table_id in self.loot_tables:
                        self.loot_table_entries[table_id] = [dict(e) for e in entries]

            self.ambient_scripts = [dict(row) for row in scripts_rows or []]  

            for room in self.rooms.values():
                instance_records = await self.db_manager.get_instances_in_room(room.dbid)
                for record in instance_records:
                    template_data = self.get_item_template(record['template_id'])
                    if template_data:
                        item_obj = Item(dict(record), template_data)
                        item_obj.room = room
                        room.item_instance_ids.append(item_obj.id)
                        self._all_item_instances[item_obj.id] = item_obj
                        
                object_rows = await self.db_manager.fetch_all_query("SELECT * FROM room_objects WHERE room_id = $1", room.dbid)
                room.objects = [dict(r) for r in object_rows]
                
                # Initial spawn of mobs at server startup
                for template_id, spawn_info in room.spawners.items():
                    if mob_template := self.mob_templates.get(template_id):
                        for _ in range(spawn_info.get("max_present", 1)):
                            room.add_mob(Mob(mob_template, room))

            log.info("World build complete. %d rooms loaded and populated.", len(self.rooms))
            return True

        except Exception:
            log.exception("A critical error occurred during the world build process.")
            return False
            
    # --- Getters ---
    def get_room(self, room_id: int) -> Optional[Room]:
        return self.rooms.get(room_id)

    def is_night(self) -> bool:
        """Determines if it is currently night time in the game world."""
        return not (calendar_defs.DAWN_HOUR <= self.game_hour < calendar_defs.DUSK_HOUR)

    def mark_room_dirty(self, room: Room):
        self.dirty_rooms.add(room.dbid)

    async def save_state(self):
        log.info("Saving world state...")
        active_chars = self.get_active_characters_list()
        if active_chars:
            char_save_tasks = [char.save() for char in active_chars]
            await asyncio.gather(*char_save_tasks, return_exceptions=True)
            log.info(f"Saved {len(active_chars)} active characters.")

        if self.dirty_rooms:
            rooms_to_save_ids = list(self.dirty_rooms)
            self.dirty_rooms.clear() 

            room_save_tasks = [self.get_room(room_id).save(self.db_manager) for room_id in rooms_to_save_ids if self.get_room(room_id)]
            if room_save_tasks:
                await asyncio.gather(*room_save_tasks, return_exceptions=True)

                log.info(f"Saved {len(room_save_tasks)} dirty rooms.")
        await self.db_manager.save_game_time(self.game_year, self.game_month, self.game_day, self.game_hour, self.game_minute)
        log.info("World state save complete.")

    def get_shop_inventory(self, room_id: int) -> Optional[List[Dict]]:
        return self.shop_inventories.get(room_id)
    
    def get_item_object(self, instance_id: str) -> Optional[Item]:
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

    def remove_active_character(self, character_id: int) -> Optional[Character]:
        return self.active_characters.pop(character_id, None)
    
    def get_active_character(self, character_id: int) -> Optional[Character]:
        return self.active_characters.get(character_id)
    
    def get_active_characters_list(self) -> List[Character]:
        return list(self.active_characters.values())

    # -- Grouping Functions ---
    def add_active_group(self, group: ' Group'):
        self.active_groups[group.id] = group

    def remove_active_group(self, group_id: int):
        if group_id in self.active_groups:
            del self.active_groups[group_id]
            
    def subscribe_to_ticker(self):
        """Subscribes all world update methods to the global ticker."""
        log.info("Subscribing world systems to the game ticker...")
        ticker.subscribe(self.update_roundtimes)
        ticker.subscribe(self.update_mob_ai)
        ticker.subscribe(self.update_respawns) 
        ticker.subscribe(self.update_death_timers)
        ticker.subscribe(self.update_effects)
        ticker.subscribe(self.update_xp_absorption)
        ticker.subscribe(self.update_regen)
        ticker.subscribe(self.update_stealth_checks)
        ticker.subscribe(self.update_room_effects)
        ticker.subscribe(self.update_item_decay)
        ticker.subscribe(self.update_ambient_scripts)
        ticker.subscribe(self.update_hunger_thirst)
        ticker.subscribe(self.update_game_time)
        ticker.subscribe(self.update_bard_songs)

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
                    ability_data = self.abilities.get(ability_key)

                    if not ability_data:
                        log.error("Finished casting unknown ability '%s' for %s.", ability_key, p.name)
                        continue

                    cost = ability_data.get("cost", 0)
                    if p.essence >= cost:
                        messages = ability_data.get("messages", {})
                        target_name = info.get("target_name", "its target")

                        if msg_self := messages.get("caster_self_complete"):
                                await p.send(msg_self.format(caster_name=p.name, target_name=target_name))
                            
                            # Message to the room
                        if msg_room := messages.get("room_complete"):
                            if p.location:
                                await p.location.broadcast(
                                    f"\r\n{msg_room.format(caster_name=p.name, target_name=target_name)}\r\n",
                                    exclude={p}
                                    )
                        p.essence -= cost
                        try:
                            await resolver.resolve_ability_effect(p, info.get("target_id"), info.get("target_type"), ability_data, self)

                        except Exception:
                            log.exception("Error resolving ability effect '%s' for %s", ability_key, p.name)
                            await p.send("Something went wrong as your action finished.")
                        
                        base_rt = ability_data.get("roundtime", 1.0)
                        rt_penalty = p.total_av * 0.05
                        p.roundtime = base_rt + rt_penalty
                    else:
                        await p.send(f"{{RYou lose focus ({ability_data.get('name', ability_key)}) - not enough essence!{{x")

    async def update_mob_ai(self, dt: float):
        tasks = [room.mob_ai_tick(dt, self) for room in self.rooms.values()]
        if tasks: await asyncio.gather(*tasks, return_exceptions=True)

    async def update_respawns(self, dt: float):
        tasks = [room.check_respawn(self) for room in self.rooms.values()]
        if tasks: await asyncio.gather(*tasks, return_exceptions=True)

    async def update_bard_songs(self, dt: float):
        """Ticker: Manages upkeep and applies effects for active bard songs."""
        bards = [c for c in self.get_active_characters_list() if c.active_song]
        if not bards:
            return

        for bard in bards:
            song_data = self.abilities.get(bard.active_song)
            if not song_data:
                bard.active_song = None
                continue

            details = song_data.get("effect_details", {})
            upkeep = details.get("essence_upkeep", 0)

            if bard.essence < upkeep:
                await bard.send(f"You run out of essence and your '{bard.active_song_name}' fades.")
                bard.active_song = None
                bard.active_song_name = None
                continue
            bard.essence -= upkeep

            is_debuff = details.get("is_debuff", False)
            if is_debuff:
                targets = [m for m in bard.location.mobs if m.is_alive()]
            else:
                if bard.group:
                    targets = [p for p in bard.group.members if p.location == bard.location and p.is_alive()]
                else:
                    targets = [bard]

            effect_name = details.get("name")
            for target in targets:
                target.effects[f"Song_{effect_name}"] = {
                    "name": f"Song_{effect_name}",
                    "stat_affected": details.get("stat_affected"),
                    "amount": details.get("amount"),
                    "ends_at": time.monotonic() + 2.0
                }

    # In game/world.py
    async def update_death_timers(self, dt: float):
        current_time = time.monotonic()
        for char in self.get_active_characters_list():
            if char.status == 'DYING' and char.death_timer_ends_at and current_time >= char.death_timer_ends_at:
                char.status = "DEAD"
                
                await char.send("\r\n{RYou have succumbed to your wounds. Your spirit now lingers over your corpse.{x")
                await char.send("{RYou may be resurrected by a powerful cleric, or you may <release> your spirit to return to your spiritual tether.{x")
                
                if char.location:
                    await char.location.broadcast(f"\r\n{char.name} has died.\r\n")

    async def respawn_character(self, character: Character):
        """Handles moving a character to their respawn point and resetting their state."""
        respawn_room_id = 44
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
        """Ticker: Processes ongoing effects and resolves expired ones."""
        current_time = time.monotonic()
        
        # Consolidate all active characters and mobs into a single list to iterate over
        all_mobs = [mob for room in self.rooms.values() for mob in room.mobs if mob.is_alive()]
        participants = self.get_active_characters_list() + all_mobs

        for participant in participants:
            if not participant.effects:
                continue
            
            # We must iterate over a copy, as the resolver will modify the dictionary
            active_effects = list(participant.effects.items())
            expired_keys = []

            for key, data in active_effects:
                # 1. Process ongoing damage effects for this tick (DoTs, etc.)
                effect_type = data.get('type')
                if effect_type in ('poison', 'bleed'):
                    # This part remains the same, handling damage per tick
                    await resolver.apply_dot_damage(participant, data, self)

                # 2. Check if the effect has expired
                if data.get("ends_at", 0) <= current_time:
                    expired_keys.append(key)
            
            # 3. Resolve all expired effects using the new centralized function
            if expired_keys:
                for key in expired_keys:
                    # This single call now handles stat reversal, messaging, and removal.
                    await resolver.resolve_effect_expiration(participant, key, self)
                            
    async def update_room_effects(self, dt: float):
        """Ticker: Applies effects from room flags to characters within them."""
        for char in self.get_active_characters_list():
            if not char.location or not char.is_alive():
                continue

            room_flags = char.location.flags

            # --- Periodic Damage Flags ---
            if "BLAZING" in room_flags:
                # Example: 2 fire damage per tick
                await resolver.apply_dot_damage(char, {'potency': 2, 'type': 'fire'}, self)
            if "ACIDIC" in room_flags:
                # Example: 2 acid damage per tick
                await resolver.apply_dot_damage(char, {'potency': 2, 'type': 'acid'}, self)
            if "FREEZING" in room_flags:
                await resolver.apply_dot_damage(char, {'potency': 2, 'type': 'cold'}, self)
            # --- Chance-based Status Effect Flags ---
            if "POISONOUS" in room_flags:
                # Example: 10% chance per tick to be afflicted with a weak poison
                if random.random() < 0.10 and not char.effects.get("RoomPoison"):
                    poison_effect = {"name": "RoomPoison", "type": "poison", "duration": 10.0, "potency": 3}
                    await resolver.apply_effect(char, char, poison_effect, {"name": "a poisonous miasma"}, self)

    async def update_xp_absorption(self, dt: float):
        """Ticker: Processes XP pool absorption and checks for level advancement."""
        absorb_this_tick = config.XP_ABSORB_RATE_PER_SEC * dt
        for char in self.get_active_characters_list():
            if char.location and "NODE" in char.location.flags and char.xp_pool > 0:
                absorb_amount = min(char.xp_pool, absorb_this_tick)
                char.xp_pool -= absorb_amount
                char.xp_total += absorb_amount
                char.is_dirty = True
                
                if char.xp_pool <= 0:
                    char.xp_pool = 0
                    await char.send("You feel you have absorbed all you can for now.")

                # After absorbing, check if the character can level up.
                xp_for_next_level = utils.xp_needed_for_level(char.level)
                if char.xp_total >= xp_for_next_level and not char.can_advance_notified:
                    await char.send("{gYou have gained enough experience to advance to the next level!{x")
                    await char.send("{gType {c<advance>{g to proceed.{x")
                    char.can_advance_notified = True
    
    async def update_stealth_checks(self, dt: float):
        """Ticker: Periodically allows observers to detect hidden characters and mobs."""
        if random.random() > 0.10: # 10% chance per second
            return
        
        # Find all hidden entities (characters and mobs)
        hidden_chars = [c for c in self.get_active_characters_list() if c.is_hidden]
        all_mobs = [m for r in self.rooms.values() for m in r.mobs]
        hidden_mobs = [m for m in all_mobs if m.is_hidden and m.is_alive()]
        
        hidden_entities = hidden_chars + hidden_mobs
        if not hidden_entities:
            return

        for hidden_entity in hidden_entities:
            # Determine the stealth value (DC) of the hidden entity
            if isinstance(hidden_entity, Character):
                stealth_dc = hidden_entity.get_skill_modifier("stealth")
            else: # It's a Mob
                stealth_dc = hidden_entity.get_stealth_value()

            # --- FIX: Filter observers to exclude self and group members ---
            observers = []
            for char in hidden_entity.location.characters:
                # Must be alive and not the hider themselves
                if not char.is_alive() or char == hidden_entity:
                    continue
                # If the hider is a character and is in a group, exclude group members
                if isinstance(hidden_entity, Character) and hidden_entity.group and char in hidden_entity.group.members:
                    continue
                observers.append(char)
            # -----------------------------------------------------------------

            for observer in observers:
                # Mobs can't detect hidden players in this implementation yet, but players can detect mobs
                if utils.skill_check(observer, "perception", dc=stealth_dc)['success']:
                    hidden_entity.is_hidden = False
                    
                    if isinstance(hidden_entity, Character):
                        await hidden_entity.send(f"{{RYou have been spotted by {observer.name}!{{x")
                    
                    await observer.send(f"{{YYou spot {hidden_entity.name} hiding in the shadows!{{x")
                    await observer.location.broadcast(
                        f"\r\n{observer.name} spots {hidden_entity.name} hiding in the shadows!\r\n",
                        exclude={observer, hidden_entity}
                    )
                    break # Stop checking once spotted

    async def update_hunger_thirst(self, dt: float):
        """Ticker: Decreases hunger and thirst and notifies characters on status changes."""
        for char in self.get_active_characters_list():
            # Store current status before changing values
            old_hunger_status = utils.format_hunger_status(char)
            old_thirst_status = utils.format_thirst_status(char)

            # Decrease thirst and hunger
            char.thirst = max(0, char.thirst - (dt / 100.0))
            char.hunger = max(0, char.hunger - (dt / 200.0))

            # Get new status
            new_hunger_status = utils.format_hunger_status(char)
            new_thirst_status = utils.format_thirst_status(char)

            # Check if hunger status has changed to a worse state and notify
            if new_hunger_status != old_hunger_status:
                if "Peckish" in new_hunger_status:
                    await char.send("{YYou are starting to feel peckish.{x")
                elif "Hungry" in new_hunger_status:
                    await char.send("{YYour stomach rumbles loudly.{x")
                elif "Starving" in new_hunger_status:
                    await char.send("{RYou are starving! Your health regeneration has stopped!{x")

            # Check if thirst status has changed to a worse state and notify
            if new_thirst_status != old_thirst_status:
                if "Thirsty" in new_thirst_status:
                    await char.send("{yYou feel thirsty.{x")
                elif "Parched" in new_thirst_status:
                    await char.send("{yYour mouth feels dry and parched.{x")
                elif "Dehydrated" in new_thirst_status:
                    await char.send("{rYou are dehydrated! Your essence regeneration has stopped!{x")

    async def update_regen(self, dt: float):
        """Ticker: Calls the regeneration logic for all active characters."""
        for char in self.get_active_characters_list():
            is_in_node = char.location and "NODE" in char.location.flags
            char.update_regen(dt, is_in_node)
        
    async def update_item_decay(self, dt: float):
        """
        Ticker: Periodically cleans up old, flagged items from the ground.
        Uses an internal timer to only run its logic every DECAY_CHECK_INTERVAL seconds.
        """
        current_time = time.monotonic()
        
        # 1. Use an internal timer to run this check infrequently
        if current_time - self._last_decay_check_time < DECAY_CHECK_INTERVAL:
            return
        
        self._last_decay_check_time = current_time

        decay_threshold = config.ITEM_DECAY_TIME_SECONDS
        items_to_delete = []

        # 2. Efficiently find items eligible for decay (no database calls here)
        for item in self._all_item_instances.values():
            if item.room and item.has_flag("DECAYS"):
                if item.last_moved_at:
                    # Use the timestamp stored on the object itself
                    age = time.time() - item.last_moved_at.timestamp()
                    if age > decay_threshold:
                        items_to_delete.append(item)
        
        if not items_to_delete:
            return

        # 3. Delete the items
        for item in items_to_delete:
            # Remove from world state
            del self._all_item_instances[item.id]
            if item.room and item.id in item.room.item_instance_ids:
                item.room.item_instance_ids.remove(item.id)
            
            # Remove from database
            await self.db_manager.delete_item_instance(item.id)
        
        log.info(f"Cleaned up {len(items_to_delete)} decayed items from the world.")

    async def update_game_time(self, dt: float):
    """Ticker: Advances the in-game calendar and clock, and manages day/night cycle."""
    self.game_time_accumulator += dt

    if self.game_time_accumulator < calendar_defs.SECONDS_PER_GAME_MINUTE:
        return
    
    minutes_passed = int(self.game_time_accumulator / calendar_defs.SECONDS_PER_GAME_MINUTE)
    self.game_time_accumulator %= calendar_defs.SECONDS_PER_GAME_MINUTE

    if not minutes_passed:
        return

    # --- Day/Night Cycle Logic ---
    hour_before_update = self.game_hour
    
    self.game_minute += minutes_passed
    while self.game_minute >= calendar_defs.MINUTES_PER_HOUR:
        self.game_minute -= calendar_defs.MINUTES_PER_HOUR
        self.game_hour += 1
        if self.game_hour >= calendar_defs.HOURS_PER_DAY:
            self.game_hour = 0
            self.game_day += 1

            # NEW: Call the weather update when a new day starts
            await self._update_world_weather()

            if self.game_day > calendar_defs.DAYS_PER_MONTH:
                self.game_day = 1
                self.game_month += 1
                if self.game_month > calendar_defs.MONTHS_PER_YEAR:
                    self.game_month = 1
                    self.game_year += 1

    # Check if the hour has changed
    if self.game_hour == hour_before_update:
        return

    message = None
    apply_dark = False
    remove_dark = False

    if self.game_hour == calendar_defs.DAWN_HOUR:
        message = "{YThe sun crests the horizon, chasing away the shadows of the night.{x"
        remove_dark = True
    elif self.game_hour == calendar_defs.DUSK_HOUR:
        message = "{yThe sun dips below the horizon, and darkness begins to fall.{x"
        apply_dark = True
    elif self.game_hour == 0: # Midnight
        message = "{BThe moons hang high in the sky, marking the deepest point of the night.{x"
    elif self.game_hour == 12: # Noon
        message = "{CThe sun reaches its zenith in the sky.{x"

    if message or apply_dark or remove_dark:
        # Find all characters in outdoor rooms
        outdoor_chars = [
            char for char in self.get_active_characters_list()
            if char.location and "OUTDOORS" in char.location.flags
        ]
        
        # Send message to outdoor characters
        if message:
            tasks = [char.send(message) for char in outdoor_chars]
            if tasks:
                await asyncio.gather(*tasks)

        # Update room flags
        for room in self.rooms.values():
            if "OUTDOORS" in room.flags:
                # NEW: Add 'and "LIT" not in room.flags' to prevent lit rooms from getting dark
                if apply_dark and "LIT" not in room.flags:
                    room.flags.add("DARK")
                elif remove_dark:
                    room.flags.discard("DARK")


    async def generate_loot_for_container(self, container: Item, loot_table_id: int, character: Character):
        """
        Generates items and coinage from a loot table and places them in a container.
        This version fetches data live from the database.
        """
        # Fetch loot table entries live from the database
        entries = await self.db_manager.fetch_loot_table_entries(loot_table_id)
        if not entries:
            log.warning(f"Attempted to generate loot for container {container.id} from empty or non-existent loot table {loot_table_id}.")
            return

        generated_items = []
        generated_coinage = 0

        for entry in entries:
            # Roll to see if this item/coin drop happens
            if random.random() <= entry['drop_chance']:
                # Handle Coinage
                if entry['max_coinage'] > 0:
                    coin_amount = random.randint(entry['min_coinage'], entry['max_coinage'])
                    generated_coinage += coin_amount

                # Handle Items
                if item_template_id := entry.get('item_template_id'):
                    quantity = random.randint(entry['min_quantity'], entry['max_quantity'])
                    for _ in range(quantity):
                        new_instance_data = await self.db_manager.create_item_instance(
                            template_id=item_template_id,
                            container_id=container.id  # This places the item inside the container
                        )
                        if new_instance_data:
                            template = self.get_item_template(item_template_id)
                            new_item = Item(new_instance_data, template)
                            # Add the new item to the world and container's in-memory state
                            self._all_item_instances[new_item.id] = new_item
                            container.contents[new_item.id] = new_item
                            generated_items.append(new_item.name)
        
        # Add all generated coinage to the floor of the character's room and notify them.
        if generated_coinage > 0 and character.location:
            await character.location.add_coinage(generated_coinage, self)
            await character.send(f"You find {utils.format_coinage(generated_coinage)} inside.")

        if generated_items:
            log.info(f"Generated loot in {container.name}: {', '.join(generated_items)}")
            # You can optionally add a message to the player here as well.
            await character.send(f"You also find: {', '.join(generated_items)}.")

    async def update_ambient_scripts(self, dt: float):
        """Ticker: Periodically shows immersive messages to players."""
        # --- FIX: Use a configurable setting and more intuitive logic ---
        # This will run if a random number is LESS than your setting.
        # e.g., if the setting is 0.01, this block runs on a 1% chance.
        if random.random() < config.AMBIENT_SCRIPT_CHANCE_PER_TICK:
            active_chars = self.get_active_characters_list()
            if not active_chars:
                return

            # Group players by location to avoid spam
            active_chars.sort(key=lambda c: c.location.dbid if c.location else -1)

            for room_id, chars_in_room_iter in groupby(active_chars, key=lambda c: c.location.dbid if c.location else -1):
                if room_id == -1:
                    continue

                chars_in_room = list(chars_in_room_iter)
                first_char = chars_in_room[0]
                room = first_char.location

                possible_scripts = [
                    script for script in self.ambient_scripts
                    if (script['room_id'] == room.dbid or
                        script['area_id'] == room.area_id)
                ]

                if possible_scripts:
                    chosen_script = random.choice(possible_scripts)
                    message = f"{{i{chosen_script['script_text']}{{x"

                    tasks = [char.send(message) for char in chars_in_room]
                    if tasks:
                        await asyncio.gather(*tasks, return_exceptions=True)

    async def broadcast_to_all(self, message: str, exclude: set = None):
        """Sends a message to all active characters."""
        if exclude is None:
            exclude = set()
        
        tasks = []
        for char in self.get_active_characters_list():
            if char not in exclude:
                tasks.append(char.send(message))
        
        if tasks:
            await asyncio.gather(*tasks)