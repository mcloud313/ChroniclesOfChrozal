# game/character.py
"""
Represents a character in the game world, controlled by a player account.
Holds in-game state, attributes, and connection information.
"""
from __future__ import annotations
import time
import random
import asyncio
import logging
import config
from typing import TYPE_CHECKING, Optional, Dict, Any, List, Tuple, Union, Set
from .item import Item
from .definitions import skills as skill_defs, abilities as ability_defs, classes as class_defs, item_defs
from .definitions import slots as slot_defs
from . import utils

if TYPE_CHECKING:
    from .room import Room
    from .world import World
    from .mob import Mob
    from .group import Group

log = logging.getLogger(__name__)

class Character:
    """Represents a character, now aware of unique item instances."""
    
    @property
    def might_mod(self) -> int:
        base_might = self.stats.get("might", 10)
        bonus_might = self.get_stat_bonus_from_equipment("bonus_might")
        return utils.calculate_modifier(base_might + bonus_might)
    
    @property
    def vit_mod(self) -> int:
        base_vitality = self.stats.get("vitality", 10)
        bonus_vitality = self.get_stat_bonus_from_equipment("bonus_vitality")
        return utils.calculate_modifier(base_vitality + bonus_vitality)
    
    @property
    def agi_mod(self) -> int:
        base_agility = self.stats.get("agility", 10)
        bonus_agility = self.get_stat_bonus_from_equipment("bonus_agility")
        return utils.calculate_modifier(base_agility + bonus_agility)
    
    @property
    def int_mod(self) -> int:
        base_intellect = self.stats.get("intellect", 10)
        bonus_intellect = self.get_stat_bonus_from_equipment("bonus_intellect")
        return utils.calculate_modifier(base_intellect + bonus_intellect)
    
    @property
    def aura_mod(self) -> int:
        base_aura = self.stats.get("aura", 10)
        bonus_aura = self.get_stat_bonus_from_equipment("bonus_aura")
        return utils.calculate_modifier(base_aura + bonus_aura)
    
    @property
    def pers_mod(self) -> int:
        base_persona = self.stats.get("persona", 10)
        bonus_persona = self.get_stat_bonus_from_equipment("bonus_persona")
        return utils.calculate_modifier(base_persona + bonus_persona)

    @property
    def mar(self) -> int:
        base_mar = self.might_mod + (self.agi_mod // 2)
        item_bonus = self.get_stat_bonus_from_equipment("bonus_mar")
        effect_bonus = self.get_stat_bonus_from_effects("bonus_mar")
        return base_mar + item_bonus + effect_bonus

    @property
    def rar(self) -> int:
        base_rar = self.agi_mod + (self.might_mod // 2)
        item_bonus = self.get_stat_bonus_from_equipment("bonus_rar")
        effect_bonus = self.get_stat_bonus_from_effects("bonus_rar")
        skill_bonus = self.get_skill_rank("projectile weapons") // 25
        return base_rar + item_bonus + effect_bonus + skill_bonus

    @property
    def apr(self) -> int:
        base_apr = self.int_mod + (self.aura_mod // 2)
        item_bonus = self.get_stat_bonus_from_equipment("bonus_apr")
        effect_bonus = self.get_stat_bonus_from_effects("bonus_apr")
        skill_bonus = self.get_skill_rank("spellcraft") // 25
        return base_apr + item_bonus + effect_bonus + skill_bonus

    @property
    def dpr(self) -> int:
        base_dpr = self.aura_mod + (self.pers_mod // 2)
        item_bonus = self.get_stat_bonus_from_equipment("bonus_dpr")
        effect_bonus = self.get_stat_bonus_from_effects("bonus_dpr")
        skill_bonus = self.get_skill_rank("piety") // 25
        return base_dpr + item_bonus + effect_bonus + skill_bonus

    @property
    def pds(self) -> int:
        """
        Calculates Physical Defense Stat.
        FIX: Added a base value of 2 for all characters.
        """
        base_pds = self.vit_mod 
        item_bonus = self.get_stat_bonus_from_equipment("bonus_pds")
        effect_bonus = self.get_stat_bonus_from_effects("bonus_pds")
        return base_pds + item_bonus + effect_bonus

    @property
    def sds(self) -> int:
        base_sds = self.aura_mod
        item_bonus = self.get_stat_bonus_from_equipment("bonus_sds")
        effect_bonus = self.get_stat_bonus_from_effects("bonus_sds")
        return base_sds + item_bonus + effect_bonus

    @property
    def dv(self) -> int:
        base_dv = self.agi_mod * 2
        item_bonus = self.get_stat_bonus_from_equipment("bonus_dv")
        effect_bonus = self.get_stat_bonus_from_effects("bonus_dv")
        dodge_bonus = self.get_skill_rank("dodge") // 25
        return base_dv + item_bonus + effect_bonus + dodge_bonus
    
    @property
    def barrier_value(self) -> int:
        """Calculates total Barrier Value (BV) from active effects."""
        total_bv = 0
        for effect_data in self.effects.values():
            # --- FIX: Look for the correct key, "stat_affected" ---
            if effect_data.get("stat_affected") == ability_defs.STAT_BARRIER_VALUE:
                total_bv += effect_data.get("amount", 0)
        return total_bv

    @property
    def total_spell_failure(self) -> int:
        """Calculates total spell failure chance from all equipped items."""
        total_failure = 0
        for item in self._equipped_items.values():
            total_failure += item.spell_failure
        return total_failure

    @property
    def slow_penalty(self) -> float:
        """Returns the roundtime penalty from any active 'slow' effects."""
        for effect in self.effects.values():
            if effect.get('type') == 'slow' and effect.get('ends_at', 0) > time.monotonic():
                return effect.get('potency', 0.0)
        return 0.0
    
    def base_av(self) -> int:
        """Returns the raw, unmodified Armor Value from equipped items."""
        return sum(item.armor for item in self._equipped_items.values() if item)
    
    @property
    def total_av(self) -> int:
        """Calculates the character's total Armor Value from all sources."""
        
        # --- LIKELY CAUSE OF THE BUG ---
        # The original code might be missing the () on the method call below.
        base_av = self.get_base_av_from_armor() # <-- FIX: Ensure parentheses are here
        # -------------------------------

        bonus_av = self.get_bonus_from_effects("bonus_av")
        
        # Calculate the percentage of AV the character benefits from
        armor_training_rank = self.get_skill_rank("armor training")
        if armor_training_rank < 50:
            av_percentage = 0.5 + (armor_training_rank / 100.0) # Scales from 50% to 99%
        else:
            av_percentage = 1.0 # 100% effectiveness at 50 ranks and above
            # Add a flat bonus for ranks beyond 50
            bonus_av += (armor_training_rank - 50) // 10

        # The final calculation from the traceback
        return int((base_av * av_percentage) + bonus_av)
    
    def get_base_av_from_armor(self) -> int:
        """Sums the armor value from all equipped armor items."""
        total = 0
        for item in self._equipped_items.values():
            if item.item_type == item_defs.ARMOR or item.item_type == item_defs.SHIELD:
                total += item.armor
        return total
    
    def get_bonus_from_effects(self, stat_name: str) -> int:
        """
        Calculates the total bonus or penalty for a given stat from all active effects.
        """
        total_modifier = 0
        # Iterate through a copy of the values in case the dictionary changes
        for effect in list(self.effects.values()):
            if effect.get('stat_affected') == stat_name:
                total_modifier += effect.get('amount', 0)
        return total_modifier

    
    def __init__(self, writer: asyncio.StreamWriter, db_data: Dict[str, Any], world: 'World', player_is_admin: bool = False):
        self.writer: asyncio.StreamWriter = writer
        self.is_admin: bool = player_is_admin
        self.world: 'World' = world

        # --- Data loaded directly from the 'characters' table row ---
        self.dbid: int = db_data['id']
        self.player_id: int = db_data['player_id']
        self.first_name: str = db_data['first_name']
        self.last_name: str = db_data['last_name']
        self.sex: str = db_data['sex']
        self.race_id: Optional[int] = db_data['race_id']
        self.class_id: Optional[int] = db_data['class_id']
        self.level: int = db_data['level']
        self.hunger: int = db_data.get('hunger', 100)
        self.thirst: int = db_data.get('thirst', 100)
        self.description: str = db_data['description']
        self.hp: float = float(db_data['hp'])
        self.max_hp: float = float(db_data['max_hp'])
        self.essence: float = float(db_data['essence'])
        self.max_essence: float = float(db_data['max_essence'])
        self.xp_pool: float = db_data['xp_pool']
        self.xp_total: float = db_data['xp_total']
        self.can_advance_notified: bool = False
        self.unspent_skill_points: int = db_data['unspent_skill_points']
        self.unspent_attribute_points: int = db_data['unspent_attribute_points']
        self.spiritual_tether: int = db_data.get('spiritual_tether', 10) # Default if not in db
        self.coinage: int = db_data['coinage']
        self.location_id: int = db_data['location_id']
        self.total_playtime_seconds: int = db_data['total_playtime_seconds']
        self.status: str = db_data.get('status', 'ALIVE')
        self.stance: str = db_data.get('stance', 'Standing')
        
        # --- Runtime State Attributes (not in the database) ---
        self.name: str = f"{self.first_name} {self.last_name}"
        self.location: Optional['Room'] = None
        self.target: Optional[Union['Character', 'Mob']] = None
        self.group: Optional['Group'] = None
        self.effects: Dict[str, Dict[str, Any]] = {}
        self.resistances: Dict[str, float] = {} # Can be populated by effects/items
        self.casting_info: Optional[Dict[str, Any]] = None
        self.pending_give_offer: Optional[Dict[str, Any]] = None
        self.is_dirty: bool = True
        self.login_timestamp: Optional[float] = None
        self.death_timer_ends_at: Optional[float] = None
        self.roundtime: float = 0.0
        self.is_fighting: bool = False
        self.is_hidden: bool = False
        self.detected_traps: set = set()
        self.known_abilities: Set[str] = set()

        self.active_song: Optional[str] = None
        self.active_song_name: Optional[str] = None

        # --- Data Structures to be populated by load_related_data() ---
        self.stats: Dict[str, int] = {}
        self.skills: Dict[str, int] = {}
        self._inventory_items: Dict[str, Item] = {}
        self._equipped_items: Dict[str, Item] = {}

        # Clamp loaded HP/Essence to max values
        self.hp = min(self.hp, self.max_hp)
        self.essence = min(self.essence, self.max_essence)
        if self.status in ["DYING", "DEAD"]:
            self.hp = 0.0

    async def load_related_data(self):
        """
        Fetches all related character data (stats, skills, items, equipment)
        and populates the character object.
        """
        results = await asyncio.gather(
            self.world.db_manager.get_character_stats(self.dbid),
            self.world.db_manager.get_character_skills(self.dbid),
            self.world.db_manager.get_character_abilities(self.dbid),
            self.world.db_manager.get_character_equipment(self.dbid),
            self.world.db_manager.get_instances_for_character(self.dbid)
        )
        stats_record, skills_records, ability_set, equipment_record, instance_records = results

        if stats_record:
            self.stats = {k: v for k, v in dict(stats_record).items() if k != 'character_id'}
        
        if skills_records:
            self.skills = {record['skill_name']: record['rank'] for record in skills_records}

        self.known_abilities = ability_set if ability_set else set()

        all_owned_items: Dict[str, Item] = {}
        if instance_records:
            for inst_record in instance_records:
                template_data = self.world.get_item_template(inst_record['template_id'])
                if template_data:
                    item_obj = Item(dict(inst_record), template_data)
                    all_owned_items[item_obj.id] = item_obj

        for item in all_owned_items.values():
            if item.container_id and (container := all_owned_items.get(item.container_id)):
                container.contents[item.id] = item

        if equipment_record:
            for slot, item_id in dict(equipment_record).items():
                if slot != 'character_id' and item_id and item_id in all_owned_items:
                    self._equipped_items[slot] = all_owned_items[item_id]

        for item in all_owned_items.values():
            if not item.is_equipped(self) and not item.is_in_container():
                self._inventory_items[item.id] = item

        log.debug("Loaded related data for %s.", self.name)

        await self.check_and_learn_new_abilities()
        # --------------------------------------------------------------------------

    async def send(self, message: str, add_newline: bool = True):
        """
        Formats and sends a message to the character's client.
        This is the central method for all server-to-client communication.
        """
        if self.writer.is_closing():
            # Avoid trying to write to a closed stream
            return

        # Apply color codes and ensure proper line endings for MUD clients
        message_to_send = utils.colorize(message)
        if add_newline and not message_to_send.endswith('\r\n'):
            message_to_send += '\r\n'
        
        try:
            self.writer.write(message_to_send.encode(config.ENCODING))
            await self.writer.drain()
        except (ConnectionResetError, BrokenPipeError) as e:
            # This is expected if the player disconnects abruptly.
            # No need to raise an error, just log it for debugging.
            log.warning("Failed to send to %s: %s", self.name, e)
            # The main connection handler will manage the cleanup.
        except Exception as e:
            log.exception("Unexpected error while sending to %s:", self.name, exc_info=e)



    def get_core_data_for_saving(self) -> Dict[str, Any]:
        """
        Gathers the character's core attributes into a dictionary for saving.
        """
        return {
            "level": self.level,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "essence": self.essence,
            "max_essence": self.max_essence,
            "xp_total": self.xp_total,
            "xp_pool": self.xp_pool,
            "coinage": self.coinage,
            "spiritual_tether": self.spiritual_tether,
            "total_playtime_seconds": self.total_playtime_seconds,
            "unspent_skill_points": self.unspent_skill_points,
            "unspent_attribute_points": self.unspent_attribute_points,
            # --- FIX: Add hunger and thirst to the save data ---
            "hunger": self.hunger,
            "thirst": self.thirst,
            "location_id": self.location_id
        }
    
    def get_all_owned_item_instances(self) -> List[Item]:
        """Recursively finds and returns a flat list of all items owned by the character."""
        all_items = []
        
        def recurse_items(item_list):
            for item in item_list:
                all_items.append(item)
                if item.contents:
                    recurse_items(item.contents.values())

        # Start with top-level inventory and equipped items
        recurse_items(self._inventory_items.values())
        recurse_items(self._equipped_items.values())
        return all_items

    async def save(self):
        """Prepares and saves the character's full state."""
        if not self.is_dirty:
            return

        # Prepare all data components for the save function
        core_data = self.get_core_data_for_saving()
        equipment_data = self.get_equipment_for_saving()
        # --- FIX: Prepare data for saving container contents ---
        all_items_data = [
            (item.id, item.container_id) for item in self.get_all_owned_item_instances()
        ]

        await self.world.db_manager.save_character_full(
            self.dbid,
            core_data,
            self.stats,
            self.skills,
            equipment_data,
            self.known_abilities,
            all_items_data  # Pass the new item data
        )

        self.is_dirty = False
        log.info(f"Successfully saved character: {self.name} (ID: {self.dbid})")


    def get_equipment_for_saving(self) -> Dict[str, Optional[str]]:
        """
        Serializes all equipped items into a dictionary mapping slot_name -> item_instance_id
        for saving to the database.
        """
        equipment_data = {}
        for slot in slot_defs.ALL_SLOTS:
            item = self._equipped_items.get(slot)
            
            # --- THE FINAL FIX ---
            # Pass the raw UUID object. The database driver will now handle it correctly
            # because the column data type is correct.
            equipment_data[slot] = item.id if item else None
            # ---------------------
        
        return equipment_data

    async def check_and_learn_new_abilities(self):
        """Checks for and learns new abilities upon leveling up."""
        char_class_name = self.world.get_class_name(self.class_id).lower()
        
        new_abilities_learned = False
        # Use world.abilities which is the pre-loaded dictionary of all ability templates
        for key, ability in self.world.abilities.items():
            # Character learns any ability they meet the level for that they don't already know.
            if (self.level >= ability['level_req'] and
                    char_class_name in ability['class_req'] and
                    key not in self.known_abilities):
                
                self.known_abilities.add(key)
                await self.send(f"{{gYou have learned a new {ability['ability_type'].lower()}: {ability['name']}!{{x")
                log.info(f"Character {self.name} learned new ability: {ability['name']}")
                new_abilities_learned = True
        if new_abilities_learned:
            self.is_dirty = True

    def respawn(self):
        """Resets character state after death."""
        log.info("RESPAWN: Character %s (ID %s) is respawning.", self.name, self.dbid)
        self.hp = self.max_hp
        self.essence = self.max_essence
        self.status = 'ALIVE'
        self.target = None
        self.is_fighting = False
        self.death_timer_ends_at = None
        self.roundtime = 0.0

    def can_see(self) -> bool:
        """
        Determines if the character can see in their current room.
        This is the central check for all darkness-related penalties.
        """
        if not self.location:
            return False # Can't see in the void
        
        # If the room is not flagged as DARK, the character can see.
        if "DARK" not in self.location.flags:
            return True
        
        # If the room IS dark, the character can only see if they have a light source.
        return self.is_holding_light_source()

    def update_regen(self, dt: float, is_in_node: bool):
        """Applies HP and essence regeneration using config-driven values."""
        if self.status not in ["ALIVE", "MEDITATING"]:
            return

        # --- Base Regeneration Rates ---
        hp_regen_rate = (config.HP_REGEN_BASE_PER_SEC + (self.vit_mod * config.HP_REGEN_VIT_MULTIPLIER))
        essence_regen_rate = (config.ESSENCE_REGEN_BASE_PER_SEC + (self.aura_mod * config.ESSENCE_REGEN_AURA_MULTIPLIER))

        # --- Apply Multipliers ---
        if is_in_node:
            hp_regen_rate *= config.NODE_REGEN_MULTIPLIER
            essence_regen_rate *= config.NODE_REGEN_MULTIPLIER
        
        if self.status == "MEDITATING":
            # Meditating only boosts essence regen
            essence_regen_rate *= config.MEDITATE_REGEN_MULTIPLIER

        # --- Apply Regeneration, Gated by Hunger/Thirst ---
        if self.hp < self.max_hp and self.status != "MEDITATING": # Can't regen HP while meditating
            if self.hunger > 0:
                self.hp = min(self.max_hp, self.hp + (hp_regen_rate * dt))

        if self.essence < self.max_essence:
            if self.thirst > 0:
                self.essence = min(self.max_essence, self.essence + (essence_regen_rate * dt))

    def update_location(self, new_location: Optional['Room']):
        """Updates the character's current location reference."""
        self.location = new_location
        if new_location:
            self.location_id = new_location.dbid

    def recalculate_max_vitals(self):
        """
        Recalculates Max HP and Max Essence based on current level and stats.
        This does NOT restore current HP/Essence, it only adjusts the maximums.
        Used at creation, on level up, or when base stats change.
        """
        # Base value is determined by level * average die roll + initial roll
        hp_die = class_defs.CLASS_HP_DIE.get(self.class_id, class_defs.DEFAULT_HP_DIE)
        ess_die = class_defs.CLASS_ESSENCE_DIE.get(self.class_id, class_defs.DEFAULT_ESSENCE_DIE)
        
        # A simple formula: a base amount + (level-1) * average roll per level + stat mods per level
        base_hp = hp_die + ((self.level - 1) * (hp_die / 2 + 0.5))
        base_essence = ess_die + ((self.level - 1) * (ess_die / 2 + 0.5))

        self.max_hp = float(max(1, base_hp + (self.level * self.vit_mod)))
        self.max_essence = float(max(0, base_essence + (self.level * (self.aura_mod + self.pers_mod))))
        
        log.debug("Recalculated max vitals for %s (Lvl %d): MaxHP=%.1f, MaxEss=%.1f",
                  self.name, self.level, self.max_hp, self.max_essence)

    def apply_level_up_gains(self) -> Tuple[float, float]:
        """
        Calculates and applies HP/Essence gains from a level up, then refills vitals.
        This should be called AFTER level has been incremented.
        """
        hp_die_size = class_defs.CLASS_HP_DIE.get(self.class_id, class_defs.DEFAULT_HP_DIE)
        essence_die_size = class_defs.CLASS_ESSENCE_DIE.get(self.class_id, class_defs.DEFAULT_ESSENCE_DIE)

        hp_roll = random.randint(1, hp_die_size)
        essence_roll = random.randint(1, essence_die_size)

        hp_increase = float(max(1, hp_roll + self.vit_mod))
        essence_increase = float(max(0, essence_roll + self.aura_mod + self.pers_mod))

        self.max_hp += hp_increase
        self.max_essence += essence_increase

        self.hp = self.max_hp
        self.essence = self.max_essence

        log.debug("%s Level Up: HP Roll(d%d)=%d, Mod=%d -> +%.1f; Ess Roll(d%d)=%d, Mod=%d -> +%.1f",
                self.name, hp_die_size, hp_roll, self.vit_mod, hp_increase,
                essence_die_size, essence_roll, self.aura_mod + self.pers_mod, essence_increase)

        return hp_increase, essence_increase

    def is_alive(self) -> bool:
        return self.hp > 0 and self.status != "DEAD"

    def get_max_weight(self) -> float:
        """Calculates the maximum weight the character can carry."""
        base_carry = config.BASE_CARRY_WEIGHT
        might_bonus = self.stats.get("might", 10) * config.CARRY_WEIGHT_MIGHT_MULTIPLIER
        return base_carry + might_bonus

    def get_shield(self) -> Optional[Item]:
        shield_item = self._equipped_items.get("off_hand")
        if shield_item and shield_item.item_type == "SHIELD":
            return shield_item
        return None

    def get_skill_rank(self, skill_name: str) -> int:
        """Gets the character's rank in a specific skill."""
        return self.skills.get(skill_name.lower(), 0)

    def get_skill_modifier(self, skill_name: str) -> int:
        """Calculates the total modifier for a skill check (rank + attribute modifier)."""
        skill_name_lower = skill_name.lower()
        rank = self.get_skill_rank(skill_name_lower)
        attr_name = skill_defs.get_attribute_for_skill(skill_name_lower)
        
        if not attr_name:
            return rank
        
        attr_value = self.stats.get(attr_name, 10)
        attr_mod = utils.calculate_modifier(attr_value)
        return rank + attr_mod
    
    def get_item_instance(self, instance_id: str) -> Optional[Item]:
        """Gets a loaded Item object for an instance the character owns."""
        return self._inventory_items.get(instance_id) or next((item for item in self._equipped_items.values() if item.id == instance_id), None)
    
    def find_item_in_inventory_by_name(self, item_name: str) -> Optional[Item]:
        """Finds the first item instance in inventory matching a name."""
        name_lower = item_name.lower()
        for item in self._inventory_items.values():
            if name_lower in item.name.lower():
                return item
        return None
    
    def find_item_in_equipment_by_name(self, item_name: str) -> Optional[Item]:
        """Finds the first item instance in equipment matching a name."""
        name_lower = item_name.lower()
        for item in self._equipped_items.values():
            # Check 'if item' to handle potential empty slots
            if item and name_lower in item.name.lower():
                return item
        return None

    def find_container_by_name(self, name: str) -> Optional[Item]:
        """Finds a container item in the character's top-level inventory or equipment."""
        name_lower = name.lower()
        # Check inventory (hands) first
        for item in self._inventory_items.values():
            if item.capacity > 0 and name_lower in item.name.lower():
                return item
        for item in self._equipped_items.values():
            if item.capacity > 0 and name_lower in item.name.lower():
                return item
        return None

    def knows_spell(self, spell_key: str) -> bool:
        """Checks if the character knows a specific spell by its internal key."""
        return spell_key.lower() in self.known_spells

    def knows_ability(self, ability_key: str) -> bool:
        """Checks if the character knows a specific ability by its internal key."""
        return ability_key.lower() in self.known_abilities
    
    def _get_item_weight_recursively(self, item: Item) -> float:
        """Helper to calculate the weight of an item and its contents."""
        total_weight = item.weight
        if item.contents:
            for content_item in item.contents.values():
                total_weight += self._get_item_weight_recursively(content_item)
        return total_weight

    def hands_are_full(self) -> bool:
        """Checks if the character can pick up or receive another item."""
        hand_slots_used = len(self._inventory_items)
        main_hand_item = self._equipped_items.get("main_hand")
        
        if main_hand_item:
            # A two-handed weapon instantly fills both "hand" slots.
            if main_hand_item.item_type == item_defs.TWO_HANDED_WEAPON:
                return True
            hand_slots_used += 1

        if self._equipped_items.get("off_hand"):
            hand_slots_used += 1
        
        return hand_slots_used >= 2

    def get_current_weight(self) -> float:
        """Calculates the total weight of all carried and equipped items."""
        total_weight = 0.0
        # Add weight of items in top-level inventory
        for item in self._inventory_items.values():
            total_weight += self._get_item_weight_recursively(item)
        # Add weight of equipped items
        for item in self._equipped_items.values():
            total_weight += self._get_item_weight_recursively(item)
        
        return round(total_weight, 2)

    def get_stat_bonus_from_effects(self, stat_name: str) -> int:
        """
        Calculates the total bonus for a given stat from all active effects.
        """
        total_bonus = 0
        current_time = time.monotonic()
        for effect in self.effects.values():
            if effect.get('stat_affected') == stat_name and effect.get('ends_at', 0) > current_time:
                total_bonus += effect.get('amount', 0)
        return total_bonus

    def is_holding_light_source(self) -> bool:
        """Checks if the character is holding or wearing a lit item."""
        for item in self._inventory_items.values():
            if item.instance_stats.get("is_lit"):
                return True
        for item in self._equipped_items.values():
            if item.instance_stats.get("is_lit"):
                return True
        return False

    def get_stat_bonus_from_equipment(self, stat_name: str) -> int:
        """
        Calculate the total bonus for a given stat from all equipped items.
        This reads from the item's unique 'instance stats'.
        """
        total_bonus = 0
        for item in self._equipped_items.values():
            total_bonus += item.instance_stats.get(stat_name, 0)
        return total_bonus

    def __repr__(self) -> str:
        return f"<Character {self.dbid}: '{self.name}'>"

    def __str__(self) -> str:
        loc_id = getattr(self.location, 'dbid', self.location_id)
        return f"Character(id={self.dbid}, name='{self.name}', loc={loc_id})"