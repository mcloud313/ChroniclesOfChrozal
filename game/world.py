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
from . import resolver
from . import utils
from . import ticker

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
        self.dirty_rooms: set[int] = set()
        self.abilities: Dict[str, Dict] = {}
        self.damage_types: Dict[str, Dict] = {}

    async def build(self):
        """
        Loads all game data from the new normalized database schema.
        """
        log.info("Building world state from PostgreSQL database...")
        
        try:
            results = await asyncio.gather(
                self.db_manager.fetch_all("SELECT * FROM areas ORDER BY id"),
                self.db_manager.fetch_all("SELECT * FROM races ORDER BY id"),
                self.db_manager.fetch_all("SELECT * FROM classes ORDER BY id"),
                self.db_manager.fetch_all("SELECT * FROM item_templates ORDER BY id"),
                self.db_manager.fetch_all("SELECT * FROM mob_templates ORDER BY id"),
                self.db_manager.fetch_all("SELECT * FROM mob_attacks ORDER BY mob_template_id"),
                self.db_manager.fetch_all("SELECT * FROM mob_loot_table ORDER BY mob_template_id"),
                self.db_manager.fetch_all("SELECT * FROM rooms ORDER BY id"),
                self.db_manager.fetch_all("SELECT * FROM exits ORDER BY source_room_id"),
                self.db_manager.fetch_all("SELECT * FROM shop_inventories ORDER BY room_id"),
                self.db_manager.fetch_all("SELECT * FROM ability_templates"),
                self.db_manager.fetch_all("SELECT * FROM damage_types") 
            )
            (area_rows, race_rows, class_rows, item_rows, mob_rows, attack_rows,
             loot_rows, room_rows, exit_rows, shop_rows, ability_rows, damage_type_rows) = results

            self.areas = {row['id']: dict(row) for row in area_rows or []}
            self.races = {row['id']: dict(row) for row in race_rows or []}
            self.classes = {row['id']: dict(row) for row in class_rows or []}
            self.item_templates = {row['id']: dict(row) for row in item_rows or []}
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

            for room in self.rooms.values():
                instance_records = await self.db_manager.get_instances_in_room(room.dbid)
                for record in instance_records:
                    template_data = self.get_item_template(record['template_id'])
                    if template_data:
                        item_obj = Item(dict(record), template_data)
                        room.item_instance_ids.append(item_obj.id)
                        self._all_item_instances[item_obj.id] = item_obj
                        
                object_rows = await self.db_manager.fetch_all("SELECT * FROM room_objects WHERE room_id = $1", room.dbid)
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
        ticker.subscribe(self.update_item_decay, interval_seconds=30.0)

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
        """Ticker: Processes ongoing effects and removes expired ones."""
        current_time = time.monotonic()
        all_mobs = [mob for room in self.rooms.values() for mob in room.mobs]
        participants = self.get_active_characters_list() + all_mobs

        for p in participants:
            if not p.effects: continue
            
            expired_keys = []
            # Create a copy of items to avoid issues with modifying the dict while iterating
            active_effects = list(p.effects.items())

            for key, data in active_effects:
                # First, process ongoing effects for this tick
                effect_type = data.get('type')
                if effect_type in ('poison', 'bleed'):
                    await resolver.apply_dot_damage(p, data, self)
                # We'll add other effect types like regen here later

                # Then, check if the effect has expired
                if data.get("ends_at", 0) <= current_time:
                    expired_keys.append(key)
            
            # Remove all expired effects
            for key in expired_keys:
                if p.effects.get(key):
                    expired_effect_data = p.effects[key] # Get data before deleting
                    source_key = expired_effect_data.get("source_ability_key")
                    ability_data = self.abilities.get(source_key) if source_key else None
                    del p.effects[key]

                    # --- NEW: Handle expiring Max HP buffs ---
                    if expired_effect_data.get("stat_affected") == "max_hp":
                        amount = expired_effect_data.get("amount", 0)
                        p.max_hp -= amount
                        p.hp = min(p.hp, p.max_hp) # Ensure current HP isn't over the new max

                    if ability_data and p.location:
                        target_name = p.name.capitalize()
                        if isinstance(p, Character) and (msg := ability_data.get('expire_msg_self')):
                            await p.send(msg.format(target_name=target_name))
                        if msg_room := ability_data.get('expire_msg_room'):
                            await p.location.broadcast(f"\r\n{msg_room.format(target_name=target_name)}\r\n", exclude={p})

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
    
    async def update_stealth_checks(self, dt: float):
        """Ticker: Periodically allows observers to detect hidden characters."""
        # Only run this check occasionally to reduce spam and processing
        if random.random() > 0.10: # 10 % chance per second
            return
        
        hidden_chars = [c for c in self.get_active_characters_list() if c.is_hidden]
        if not hidden_chars:
            return
        
        for hidden_char in hidden_chars:
            stealth_mod = hidden_char.get_skill_modifier("stealth")

            observers = [c for c in hidden_char.location.characters if c != hidden_char] + \
                        [m for m in hidden_char.location.mobs if m.is_alive()]
            
            for observer in observers:
                # Mobs get a base perception check
                perception_mod = observer.get_skill_modifier("perception") if isinstance(observer, Character) \
                    else observer.level * 3
                
                # The hidden character's stealth is the DC for the observer's perception check
                if utils.skill_check(observer, "perception", dc=stealth_mod)['success']:
                    hidden_char.is_hidden = False
                    await hidden_char.send(f"{{RYou have been spotted by {observer.name}!{{x")
                    if isinstance(observer, Character):
                        await observer.send(f"You spot {hidden_char.name} hiding in the shadows!")
                    # Once spotted, break the inner loop and move to the next hidden character
                    break 

    async def update_regen(self, dt: float):
        """Ticker: Calls the regeneration logic for all active characters."""
        for char in self.get_active_characters_list():
            is_in_node = char.location and "NODE" in char.location.flags
            char.update_regen(dt, is_in_node)
            
    async def update_stealth_checks(self, dt: float):
        """Ticker: Periodically allows observers to detect hidden characters."""
        # Only run this check occasionally to reduce spam and processing
        if random.random() > 0.25: # Roughly 25% chance per second
            return

        hidden_chars = [c for c in self.get_active_characters_list() if c.is_hidden]
        if not hidden_chars:
            return

        for hidden_char in hidden_chars:
            # FIX: Get the hidden character's stealth modifier here
            stealth_mod = hidden_char.get_skill_modifier("stealth")

            observers = [c for c in hidden_char.location.characters if c != hidden_char] + \
                        [m for m in hidden_char.location.mobs if m.is_alive()]

            for observer in observers:
                perception_mod = observer.get_skill_modifier("perception") if isinstance(observer, Character) \
                    else observer.level * 3

                # The hidden character's stealth is the DC for the observer's perception check
                if utils.skill_check(observer, "perception", dc=stealth_mod)['success']:
                    hidden_char.is_hidden = False
                    await hidden_char.send(f"{{RYou have been spotted by {observer.name}!{{x")
                    if isinstance(observer, Character):
                        await observer.send(f"You spot {hidden_char.name} hiding in the shadows!")
                    break # Stop checking once spotted

    async def update_item_decay(self, dt: float):
        """Ticker: Periodically cleans up old, flagged items from the ground."""
        current_time = time.time()
        decay_threshold = config.ITEM_DECAY_TIME_SECONDS
        items_to_delete = []

        # Find items eligible for decay
        for item in self._all_item_instances.values():
            # Check if item is on the ground (via its owner in the game state, not DB)
            if item.owner_char is None and item.container is None:
                if item.has_flag("DECAYS"):
                    # We need to get the timestamp from the database record, as the python object doesn't have it yet.
                    # A more optimized way would be to load this at startup. For now, we'll fetch it.
                    record = await self.db_manager.get_item_instance(item.id)
                    if record and record['last_moved_at']:
                        age = current_time - record['last_moved_at'].timestamp()
                        if age > decay_threshold:
                            items_to_delete.append(item)
        
        if not items_to_delete:
            return

        # Delete the items
        for item in items_to_delete:
            log.info(f"Decaying item: {item.name} (ID: {item.id})")
            
            # Remove from world state
            del self._all_item_instances[item.id]
            if item.room:
                if item.id in item.room.item_instance_ids:
                    item.room.item_instance_ids.remove(item.id)
            
            # Remove from database
            await self.db_manager.delete_item_instance(item.id)
        
        if items_to_delete:
            log.info(f"Cleaned up {len(items_to_delete)} decayed items from the world.")
            