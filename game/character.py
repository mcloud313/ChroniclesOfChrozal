# game/character.py
"""
Represents a character in the game world, controlled by a player account.
Holds in-game state, attributes, and connection information.
"""
import math
import time
import random
import asyncio
import json
import logging
import aiosqlite
import config
from typing import TYPE_CHECKING, Optional, Dict, Any, List, Tuple, Union
from . import database
from . import utils
from .item import Item
from .definitions import skills as skill_defs
from .definitions import abilities as ability_defs
from .definitions import classes as class_defs

if TYPE_CHECKING:
    from .room import Room
    from .world import World
    from .mob import Mob

log = logging.getLogger(__name__)

class Character:
    """
    Represents an individual character within the game world.
    """
    @property
    def might_mod(self) -> int: return utils.calculate_modifier(self.stats.get("might", 10))
    @property
    def vit_mod(self) -> int: return utils.calculate_modifier(self.stats.get("vitality", 10))
    @property
    def agi_mod(self) -> int: return utils.calculate_modifier(self.stats.get("agility", 10))
    @property
    def int_mod(self) -> int: return utils.calculate_modifier(self.stats.get("intelligence", 10))
    @property
    def aura_mod(self) -> int: return utils.calculate_modifier(self.stats.get("aura", 10))
    @property
    def pers_mod(self) -> int: return utils.calculate_modifier(self.stats.get("persona", 10))

    # Derived Combat Stats
    @property
    def mar(self) -> int: return self.might_mod + (self.agi_mod // 2)
    @property
    def rar(self) -> int: return self.agi_mod + (self.might_mod // 2)
    @property
    def apr(self) -> int: return self.int_mod + (self.aura_mod // 2)
    @property
    def dpr(self) -> int: return self.aura_mod + (self.pers_mod // 2)
    @property
    def pds(self) -> int: return self.vit_mod
    @property
    def sds(self) -> int: return self.aura_mod
    @property
    def dv(self) -> int: return self.agi_mod * 2
    
    @property
    def barrier_value(self) -> int:
        """Calculates total Barrier Value (BV) from active effects."""
        total_bv = 0
        current_time = time.monotonic()
        for effect_data in self.effects.values():
            if effect_data.get("stat") == ability_defs.STAT_BARRIER_VALUE:
                if effect_data.get("ends_at", 0) > current_time:
                    total_bv += effect_data.get("amount", 0)
        return total_bv

    def __init__(self, writer: asyncio.StreamWriter, db_data: Dict[str, Any], player_is_admin: bool = False):
        """Initializes a Character object from database data and a network writer."""
        self.writer: asyncio.StreamWriter = writer
        self.is_admin: bool = player_is_admin

        # --- Data loaded from DB ---
        self.dbid: int = db_data['id']
        self.player_id: int = db_data['player_id']
        self.first_name: str = db_data['first_name']
        self.last_name: str = db_data['last_name']
        self.sex: str = db_data['sex']
        self.race_id: Optional[int] = db_data['race_id']
        self.class_id: Optional[int] = db_data['class_id']
        self.level: int = db_data['level']
        self.hp: float = float(db_data['hp'])
        self.max_hp: float = float(db_data['max_hp'])
        self.essence: float = float(db_data['essence'])
        self.max_essence: float = float(db_data['max_essence'])
        self.xp_pool: float = db_data['xp_pool']
        self.xp_total: float = db_data['xp_total']
        self.unspent_skill_points: int = db_data['unspent_skill_points']
        self.unspent_attribute_points: int = db_data['unspent_attribute_points']
        self.spiritual_tether: int = db_data['spiritual_tether']
        self.description: str = db_data['description']
        self.coinage: int = db_data['coinage']
        self.location_id: int = db_data['location_id']

        # --- Runtime State ---
        self.name: str = f"{self.first_name} {self.last_name}"
        self.location: Optional['Room'] = None
        self.target: Optional[Union['Character', 'Mob']] = None
        self.is_fighting: bool = False
        self.casting_info: Optional[Dict[str, Any]] = None
        self.effects: Dict[str, Dict[str, Any]] = {}
        self.roundtime: float = 0.0
        self.death_timer_ends_at: Optional[float] = None
        
        # --- Cleaned up Status and Stance Initialization ---
        self.status: str = db_data.get('status', 'ALIVE')
        self.stance: str = db_data.get('stance', 'Standing')
        if self.status not in ["ALIVE", "DYING", "DEAD", "MEDITATING"]:
            log.warning("Character %s loaded with invalid status '%s', resetting to ALIVE.", self.name, self.status)
            self.status = "ALIVE"

        # Load JSON fields with improved logging
        try:
            self.stats: Dict[str, int] = json.loads(db_data.get('stats') or '{}')
        except json.JSONDecodeError:
            log.warning("Character %s (%d): Could not decode stats JSON. Using empty.", self.name, self.dbid)
            self.stats: Dict[str, int] = {}
        
        try:
            self.known_spells: List[str] = json.loads(db_data.get('known_spells') or '[]')
        except json.JSONDecodeError:
            log.warning("Character %s (%d): Could not decode known_spells JSON. Using empty list.", self.name, self.dbid)
            self.known_spells = []

        try:
            self.known_abilities: List[str] = json.loads(db_data.get('known_abilities') or '[]')
        except json.JSONDecodeError:
            log.warning("Character %s (%d): Could not decode known_abilities JSON. Using empty list.", self.name, self.dbid)
            self.known_abilities = []

        try:
            self.skills: Dict[str, int] = json.loads(db_data.get('skills') or '{}')
        except json.JSONDecodeError:
            log.warning("Character %s (%d): Could not decode skills JSON. Using empty.", self.name, self.dbid)
            self.skills: Dict[str, int] = {}

        try:
            self.inventory: List[int] = json.loads(db_data.get('inventory') or '[]')
        except json.JSONDecodeError:
            log.warning("Character %s (%d): Could not decode inventory JSON. Using empty list.", self.name, self.dbid)
            self.inventory: List[int] = []

        try:
            self.equipment: Dict[str, int] = json.loads(db_data.get('equipment') or '{}')
        except (json.JSONDecodeError, TypeError):
            log.warning("Character %s (%d): Could not decode equipment JSON. Using empty dict.", self.name, self.dbid)
            self.equipment: Dict[str, int] = {}

        # Clamp loaded HP/Essence and handle loaded DYING/DEAD status
        self.hp = min(self.hp, self.max_hp)
        self.essence = min(self.essence, self.max_essence)
        if self.status in ["DYING", "DEAD"]:
            self.hp = 0.0

        log.debug("Character object initialized for %s (ID: %s, Status: %s, HP: %.1f/%.1f)",
                self.name, self.dbid, self.status, self.hp, self.max_hp)

    def get_max_weight(self) -> int:
        """Calculates maximum carrying weight based on Might."""
        might = self.stats.get("might", 10)
        return might * 10

    def get_current_weight(self, world: 'World') -> int:
        """Calculates current weight carried from inventory and equipment."""
        current_weight = 0
        all_item_ids = self.inventory + list(self.equipment.values())
        
        for item_template_id in all_item_ids:
            template = world.get_item_template(item_template_id)
            if template:
                try:
                    stats_dict = json.loads(template['stats'] or '{}')
                    current_weight += stats_dict.get("weight", 1)
                except (json.JSONDecodeError, TypeError):
                    log.warning("Could not parse stats for item template %d for weight calc.", item_template_id)
                    current_weight += 1
            else:
                log.warning("Could not find item template %d for weight calc.", item_template_id)
                current_weight += 1
        return current_weight

    def find_item_in_inventory_by_name(self, world: 'World', item_name: str) -> Optional[int]:
        """Finds the first template ID in inventory matching a partial name (case-insensitive)."""
        name_lower = item_name.lower()
        for template_id in self.inventory:
            template = world.get_item_template(template_id)
            if template and name_lower in template['name'].lower():
                return template_id
        return None

    def find_item_in_equipment_by_name(self, world: 'World', item_name: str) -> Optional[Tuple[str, int]]:
        """Finds the first equipped template ID matching a name (case-insensitive)."""
        name_lower = item_name.lower()
        for slot, template_id in self.equipment.items():
            template = world.get_item_template(template_id)
            if template and name_lower in template['name'].lower():
                return slot, template_id
        return None

    def find_item_anywhere_by_name(self, world: 'World', item_name: str) -> Optional[Tuple[str, int]]:
        """Finds item by name in equipment then inventory. Returns (location, template_id)."""
        equipped = self.find_item_in_equipment_by_name(world, item_name)
        if equipped:
            return equipped[0], equipped[1]

        inv_tid = self.find_item_in_inventory_by_name(world, item_name)
        if inv_tid:
            return "inventory", inv_tid

        return None

    def get_item_instance(self, world: 'World', template_id: int) -> Optional[Item]:
        """Instantiates an Item object from a template ID."""
        template_data = world.get_item_template(template_id)
        if template_data:
            try:
                return Item(template_data)
            except Exception:
                log.exception("Failed to instantiate Item from template %d", template_id)
        return None

    async def send(self, message: str, add_newline: bool = True):
        """Safely sends a message to this character's client, applying color codes."""
        if self.writer.is_closing():
            return

        message_to_send = utils.colorize(message)
        if add_newline and not message_to_send.endswith('\r\n'):
            message_to_send += '\r\n'

        try:
            log.debug("Sent to %s: %r", self.name, message)
            self.writer.write(message_to_send.encode(config.ENCODING))
            await self.writer.drain()
        except (ConnectionResetError, BrokenPipeError) as e:
            log.warning("Connection lost for %s during write: %s", self.name, e)
        except Exception:
            log.exception("Unexpected error writing to %s:", self.name)

    async def save(self, db_conn: aiosqlite.Connection):
        """Gathers essential character data and saves it to the database."""
        data_to_save = {
            "location_id": self.location_id, "hp": self.hp, "essence": self.essence,
            "xp_pool": self.xp_pool, "xp_total": self.xp_total, "level": self.level,
            "unspent_skill_points": self.unspent_skill_points,
            "unspent_attribute_points": self.unspent_attribute_points,
            "spiritual_tether": self.spiritual_tether, "status": self.status,
            "stance": self.stance, "stats": json.dumps(self.stats),
            "skills": json.dumps(self.skills), "known_spells": json.dumps(self.known_spells),
            "known_abilities": json.dumps(self.known_abilities),
            "inventory": json.dumps(self.inventory), "equipment": json.dumps(self.equipment),
            "coinage": self.coinage, "max_hp": self.max_hp, "max_essence": self.max_essence,
        }

        try:
            rowcount = await database.save_character_data(db_conn, self.dbid, data_to_save)
            if rowcount == 1:
                log.info("Successfully saved character %s (ID: %s).", self.name, self.dbid)
            else:
                log.warning("Save for character %s (ID: %s) reported %s rows affected.",
                            self.name, self.dbid, rowcount)
        except Exception:
            log.exception("Unexpected error saving character %s (ID: %s):", self.name, self.dbid)

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

    def update_regen(self, dt: float, is_in_node: bool):
        """Applies HP and essence regeneration."""
        if self.status not in ["ALIVE", "MEDITATING"]:
            return

        # HP Regeneration
        if self.hp < self.max_hp:
            base_hp_regen = self.vit_mod * config.HP_REGEN_VIT_MULTIPLIER
            hp_regen_rate = config.HP_REGEN_BASE_PER_SEC + base_hp_regen
            if is_in_node:
                hp_regen_rate *= config.NODE_REGEN_MULTIPLIER
            self.hp = min(self.max_hp, self.hp + (hp_regen_rate * dt))

        # Essence Regeneration
        if self.essence < self.max_essence:
            base_ess_regen = self.aura_mod * config.ESSENCE_REGEN_AURA_MULTIPLIER
            ess_regen_rate = config.ESSENCE_REGEN_BASE_PER_SEC + base_ess_regen
            if self.status == "MEDITATING":
                ess_regen_rate *= config.MEDITATE_REGEN_MULTIPLIER
            if is_in_node:
                ess_regen_rate *= config.NODE_REGEN_MULTIPLIER
            self.essence = min(self.max_essence, self.essence + (ess_regen_rate * dt))

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

    def get_total_av(self, world: 'World') -> int:
        """Calculates total armor value (AV) from worn equipment."""
        total_av = 0
        if not self.equipment:
            return 0
        
        for slot, template_id in self.equipment.items():
            template = world.get_item_template(template_id)
            if template and template['type'].upper() in ["ARMOR", "SHIELD"]:
                try:
                    stats_dict = json.loads(template['stats'] or '{}')
                    item_av = stats_dict.get("armor", 0)
                    total_av += item_av
                except (json.JSONDecodeError, TypeError):
                    log.warning("Could not parse stats for equipped item %d (Slot: %s) for AV calc.", template_id, slot)
        
        # BUG FIX: Moved log outside the loop.
        log.debug("Character %s final calculated Total AV: %d", self.name, total_av)
        return total_av

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

    def knows_spell(self, spell_key: str) -> bool:
        """Checks if the character knows a specific spell by its internal key."""
        return spell_key.lower() in self.known_spells

    def knows_ability(self, ability_key: str) -> bool:
        """Checks if the character knows a specific ability by its internal key."""
        return ability_key.lower() in self.known_abilities

    def get_shield(self, world: 'World') -> Optional[Item]:
        """Returns the Item object for the equipped shield, or None."""
        shield_template_id = self.equipment.get("WIELD_OFF")
        if not shield_template_id:
            return None
        
        shield_item = self.get_item_instance(world, shield_template_id)
        if shield_item and shield_item.item_type.upper() == "SHIELD":
            return shield_item
        return None

    def __repr__(self) -> str:
        return f"<Character {self.dbid}: '{self.name}'>"

    def __str__(self) -> str:
        loc_id = getattr(self.location, 'dbid', self.location_id)
        return f"Character(id={self.dbid}, name='{self.name}', loc={loc_id})"