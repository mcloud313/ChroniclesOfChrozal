# game/mob.py
"""
Represents Mob (Mobile Object / Non-Player Character) instances.
"""
import math
import time
import random
import json
import logging
from typing import TYPE_CHECKING, Optional, Dict, Any, List, Set, Union

from . import utils
from .definitions import abilities as ability_defs

if TYPE_CHECKING:
    from .room import Room
    from .character import Character
    from .world import World

log = logging.getLogger(__name__)

class Mob:
    """
    Represents an instance of a mob in the world, based on a template.
    AI is very basic (retaliation, random movement, aggression).
    """
    next_instance_id = 1

    @property
    def might_mod(self) -> int: return utils.calculate_modifier(self.stats.get("might", 10))
    @property
    def vit_mod(self) -> int: return utils.calculate_modifier(self.stats.get("vitality", 10))
    @property
    def agi_mod(self) -> int: return utils.calculate_modifier(self.stats.get("agility", 10))
    @property
    def int_mod(self) -> int: return utils.calculate_modifier(self.stats.get("intellect", 10))
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
        """Calculates total Barrier Value (BV) from base stats and active effects."""
        total_bv = self.stats.get("base_barrier_value", 0)
        current_time = time.monotonic()
        if self.effects:
            for effect_data in list(self.effects.values()):
                if effect_data.get("ends_at", 0) > current_time and \
                   effect_data.get("stat") == ability_defs.STAT_BARRIER_VALUE:
                    total_bv += effect_data.get("amount", 0)
        return max(0, total_bv)
    
    @property
    def total_av(self) -> int:
        """Calculates total Armor Value (AV) from base stats and active effects."""
        total_av = self.stats.get("base_armor_value", 0)
        current_time = time.monotonic()
        if self.effects:
            for effect_data in list(self.effects.values()):
                if effect_data.get("ends_at", 0) > current_time and \
                   effect_data.get("stat") == "bonus_av":
                    total_av += effect_data.get("amount", 0)
        return max(0, total_av)


    @property
    def slow_penalty(self) -> float:
        """Returns the roundtime penalty from any active 'slow' effects."""
        for effect in self.effects.values():
            if effect.get('type') == 'slow' and effect.get('ends_at', 0) > time.monotonic():
                return effect.get('potency', 0.0)
        return 0.0

    def __init__(self, template_data: Dict[str, Any], current_room: 'Room'):
        """Initializes a Mob instance from template data, applying variance."""
        self.instance_id: int = Mob.next_instance_id
        Mob.next_instance_id += 1

        self.template_id: int = template_data['id']
        self.name: str = template_data['name']
        self.description: str = template_data['description']
        self.level: int = template_data['level']
        self.location: 'Room' = current_room
        self.mob_type: Optional[str] = template_data.get('mob_type')
        self.effects: Dict[str, Dict[str, Any]] = {}
        self.resistances: Dict[str, float] = template_data.get('resistances', {})
        self.flags: List[str] = template_data.get('flags', [])

        # --- Load Variance Data ---
        try:
            variance_str = template_data.get('variance', '{}') or '{}'
            variance_dict = json.loads(variance_str)
        except (json.JSONDecodeError, TypeError):
            log.warning("Mob template %d (%s): Could not decode variance JSON: %r",
                        self.template_id, self.name, template_data.get('variance'))
            variance_dict = {}

        hp_var_pct = variance_dict.get("max_hp_pct", 0)
        stats_var_pct = variance_dict.get("stats_pct", 0)

        # --- Load and Apply Variance to Max HP ---
        template_max_hp: int = template_data.get('max_hp', 10)
        if hp_var_pct > 0:
            hp_multiplier = 1.0 + random.uniform(-hp_var_pct / 100.0, hp_var_pct / 100.0)
            self.max_hp = max(1, math.floor(template_max_hp * hp_multiplier))
        else:
            self.max_hp = max(1, template_max_hp)
        self.hp: int = self.max_hp

        # --- Load and Apply Variance to Stats ---
        self.stats: Dict[str, int] = {}
        try:
            template_stats = json.loads(template_data.get('stats', '{}') or '{}')
            for stat_name, base_value in template_stats.items():
                if stats_var_pct > 0:
                    stat_multiplier = 1.0 + random.uniform(-stats_var_pct / 100.0, stats_var_pct / 100.0)
                    self.stats[stat_name] = max(1, math.floor(base_value * stat_multiplier))
                else:
                    self.stats[stat_name] = base_value
        except (json.JSONDecodeError, TypeError):
            log.warning("Mob template %d (%s): Could not decode stats JSON: %r",
                        self.template_id, self.name, template_data.get('stats'))
        
        for core_stat in ["might", "vitality", "agility", "intellect", "aura", "persona"]:
            if core_stat not in self.stats:
                self.stats[core_stat] = 10

        # --- Load other template data ---
        try:
            self.attacks: List[Dict[str, Any]] = json.loads(template_data.get('attacks', '[]') or '[]')
        except (json.JSONDecodeError, TypeError):
            log.warning("Mob template %d (%s): Could not decode attacks JSON.", self.template_id, self.name)
            self.attacks = []
        try:
            self.loot_table: Dict[str, Any] = json.loads(template_data.get('loot', '{}') or '{}')
        except (json.JSONDecodeError, TypeError):
            log.warning("Mob template %d (%s): Could not decode loot JSON.", self.template_id, self.name)
            self.loot_table = {}
        try:
            flags_list = json.loads(template_data.get('flags', '[]') or '[]')
            self.flags: Set[str] = {flag.upper() for flag in flags_list}
        except (json.JSONDecodeError, TypeError):
            log.warning("Mob template %d (%s): Could not decode flags JSON.", self.template_id, self.name)
            self.flags = set()

        self.respawn_delay: int = template_data.get('respawn_delay_seconds', 300)
        self.movement_chance: float = template_data.get('movement_chance', 0.0)

        # --- Initialize Runtime State ---
        self.target: Optional[Union['Character', 'Mob']] = None
        self.is_fighting: bool = False
        self.roundtime: float = 0.0
        self.time_of_death: Optional[float] = None

    def is_alive(self) -> bool:
        """Returns True if the mob has HP and is not marked as dead."""
        return self.hp > 0 and self.time_of_death is None

    def choose_attack(self) -> Optional[Dict[str, Any]]:
        """Selects an attack from the available list (basic random choice)."""
        if not self.attacks:
            return None
        return random.choice(self.attacks)

    def die(self):
        """Handles mob death."""
        log.info("MOB DEATH: %s (Instance: %d) has died.", self.name.capitalize(), self.instance_id)
        self.hp = 0
        self.target = None
        self.is_fighting = False
        self.roundtime = 0.0
        self.time_of_death = time.monotonic()

    def respawn(self):
        """Resets mob state for respawning."""
        log.info("RESPAWN: %s (Instance: %d) respawns in Room %d.",
                 self.name.capitalize(), self.instance_id, getattr(self.location, 'dbid', '?'))
        self.hp = self.max_hp
        self.target = None
        self.is_fighting = False
        self.roundtime = 0.0
        self.time_of_death = None

    async def move(self, direction: str, world: 'World'):
        """Handles the logic for a mob moving to an adjacent room."""
        if not self.is_alive() or not self.location:
            return

        exit_data = self.location.exits.get(direction.lower())
        target_room_id = exit_data if isinstance(exit_data, int) else None

        if target_room_id is None:
            return

        target_room = world.get_room(target_room_id)
        if target_room is None or target_room.area_id != self.location.area_id:
            return

        current_room = self.location
        await current_room.broadcast(f"\r\n{self.name.capitalize()} leaves {direction}.\r\n")
        current_room.remove_mob(self)
        self.location = target_room
        target_room.add_mob(self)
        await target_room.broadcast(f"\r\n{self.name.capitalize()} arrives.\r\n")
        self.roundtime = 4.0

    def has_flag(self, flag_name: str) -> bool:
        """Checks if the mob has a specific flag (case-insensitive)."""
        return flag_name.upper() in self.flags

    def get_total_av(self) -> int:
        """Calculates total Armor Value (AV) from base stats and active effects."""
        total_av = self.stats.get("base_armor_value", 0)
        current_time = time.monotonic()
        if self.effects:
            for effect_data in list(self.effects.values()):
                if effect_data.get("ends_at", 0) > current_time and \
                   effect_data.get("stat") == ability_defs.STAT_ARMOR_VALUE:
                    total_av += effect_data.get("amount", 0)
        return max(0, total_av)

    async def simple_ai_tick(self, dt: float, world: 'World'):
        """Basic AI logic called by the world ticker."""
        from . import resolver

        if not self.is_alive() or self.roundtime > 0:
            return

        # --- Combat Logic ---
        if self.is_fighting and self.target:
            target_is_valid = (
                self.target.is_alive() and
                hasattr(self.target, 'location') and
                self.target.location == self.location
            )
            if not target_is_valid:
                self.target = None
                self.is_fighting = False
                return
            else:
                attack_data = self.choose_attack()
                if attack_data:
                    try:
                        damage_type = attack_data.get("damage_type", "physical").lower()
                        if damage_type in ability_defs.MAGICAL_DAMAGE_TYPES:
                            await resolver.resolve_magical_attack(self, self.target, attack_data, world)
                        else:
                            await resolver.resolve_physical_attack(self, self.target, attack_data, world)
                    except Exception as e:
                        log.exception("Error during mob %s attack: %s", self.name, e)
                        self.roundtime = 1.0
                else:
                    self.roundtime = 2.0
                return

        # --- Movement Logic ---
        if not self.is_fighting and self.movement_chance > 0 and not self.has_flag("STATIONARY"):
            if random.random() < self.movement_chance:
                possible_exits = [
                    direction for direction, target in self.location.exits.items()
                    if isinstance(target, int)
                ]
                if possible_exits:
                    await self.move(random.choice(possible_exits), world)
                    return

        # --- Aggressive Check ---
        if self.has_flag("AGGRESSIVE") and not self.is_fighting:
            potential_targets = [char for char in self.location.characters if char.is_alive()]
            if potential_targets:
                self.target = random.choice(potential_targets)
                self.is_fighting = True
                await self.location.broadcast(f"\r\n{self.name.capitalize()} becomes aggressive towards {self.target.name}!\r\n")

    def __repr__(self) -> str:
        return f"<Mob Inst:{self.instance_id} Tmpl:{self.template_id} '{self.name}' HP:{self.hp}/{self.max_hp}>"

    def __str__(self) -> str:
        return self.name.capitalize()