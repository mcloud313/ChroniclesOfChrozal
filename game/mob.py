# game/mob.py
"""
Represents Mob (Mobile Object / Non-Player Character) instances.
"""
import math
import time
import random
import json
import logging
from . import utils
# from . import combat
from typing import TYPE_CHECKING, Optional, Dict, Any, List, Set, Union

if TYPE_CHECKING:
    import aiosqlite
    from .room import Room
    from .character import Character

log = logging.getLogger(__name__)

class Mob:
    """
    Represents an instance of a mob in the world, based on a template.
    For V1, AI is very basic (retaliation). No complex state/inventory/equipment.
    """
    # Class variable to keep track of next available unique instance ID
    # This ensures mobs that look the same are distinct entities
    next_instance_id = 1

    @property
    def might_mod(self) -> int: return utils.calculate_modifier(self.stats.get("might", 10))
    # ... Add properties for vit_mod, agi_mod, int_mod, aura_mod, pers_mod ...
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

    # Derived Combat Stats (using same formulas)
    @property
    def mar(self) -> int: return self.might_mod + (self.agi_mod // 2)
    @property
    def rar(self) -> int: return self.agi_mod + (self.might_mod // 2)
    @property
    def apr(self) -> int: return utils.calculate_modifier(self.stats.get("intellect", 10)) + (utils.calculate_modifier(self.stats.get("aura", 10)) // 2) # Calculate directly if mods not needed often
    @property
    def dpr(self) -> int: return utils.calculate_modifier(self.stats.get("aura", 10)) + (utils.calculate_modifier(self.stats.get("persona", 10)) // 2)
    @property
    def pds(self) -> int: return self.vit_mod
    @property
    def sds(self) -> int: return utils.calculate_modifier(self.stats.get("aura", 10))
    @property
    def dv(self) -> int: return self.agi_mod * 2

    @property
    def barrier_value(self) -> int:
        """Mobs don't benefit from magical barriers in V1."""
        #TODO: ALLOW FOR MOBS TO BENEFIT FROM MAGICAL BARRIERS
        # Could check self.effects later if mobs can get buffs/barriers
        return 0

    def __init__(self, template_data: Dict[str, Any], current_room: 'Room'):
        """
        Initializes a Mob instance from template data, applying variance.

        Args:
            template_data: A dictionary derived from the mob_templates row.
            current_room: The Room object where the mob is initially placed.
        """
        self.instance_id: int = Mob.next_instance_id
        Mob.next_instance_id += 1

        # --- Store basic template info ---
        self.template_id: int = template_data['id']
        self.name: str = template_data['name']
        self.description: str = template_data['description']
        self.level: int = template_data['level']
        self.location: 'Room' = current_room # Initial location
        self.mob_type: Optional[str] = template_data.get('mob_type')
        self.effects: Dict[str, Dict[str, Any]] = {}

        # --- Load Variance Data ---
        variance_dict: Dict[str, int] = {}
        try:
            variance_str = template_data.get('variance', '{}') or '{}'
            variance_dict = json.loads(variance_str)
        except (json.JSONDecodeError, TypeError):
            log.warning("Mob template %d (%s): Could not decode variance JSON: %r",
            self.template_id, self.name, template_data.get('variance', '{}'))

        hp_var_pct = variance_dict.get("max_hp_pct", 0)
        stats_var_pct = variance_dict.get("stats_pct", 0)

        # --- Load and Apply Variance to Max HP ---
        template_max_hp: int = template_data.get('max_hp', 10)
        if hp_var_pct > 0:
            hp_multiplier = 1.0 + random.uniform(-hp_var_pct / 100.0, hp_var_pct / 100.0)
            self.max_hp = max(1, math.floor(template_max_hp * hp_multiplier))
        else:
            self.max_hp = max(1, template_max_hp)
        self.hp: int = self.max_hp # Start at full randomized health

        # --- Load and Apply Variance to Stats ---
        self.stats: Dict[str, int] = {} # Initialize instance stats
        try:
            template_stats: Dict[str, int] = json.loads(template_data.get('stats', '{}') or '{}')
            for stat_name, base_value in template_stats.items():
                if stats_var_pct > 0:
                    stat_multiplier = 1.0 + random.uniform(-stats_var_pct / 100.0, stats_var_pct / 100.0)
                    self.stats[stat_name] = max(1, math.floor(base_value * stat_multiplier))
                else:
                    self.stats[stat_name] = base_value
        except (json.JSONDecodeError, TypeError):
            log.warning("Mob template %d (%s): Could not decode stats JSON: %r",
                        self.template_id, self.name, template_data.get('stats', '{}'))
            # Ensure stats dict exists even if parse fails
            if not hasattr(self, 'stats'): self.stats = {}

        # Add default 10 for any core stats missing from template/parsing
        for core_stat in ["might", "vitality", "agility", "intellect", "aura", "persona"]:
            if core_stat not in self.stats:
                self.stats[core_stat] = 10
                log.debug("Mob template %d (%s): Assigning default 10 for missing stat '%s'",
                        self.template_id, self.name, core_stat)

        # --- Load other template data (attacks, loot, flags, respawn) ---
        try:
            self.attacks: List[Dict[str, Any]] = json.loads(template_data.get('attacks', '[]') or '[]')
        except (json.JSONDecodeError, TypeError): self.attacks = []
        try:
            self.loot_table: Dict[str, Any] = json.loads(template_data.get('loot', '{}') or '{}')
        except (json.JSONDecodeError, TypeError): self.loot_table = {}
        try:
            flags_list = json.loads(template_data.get('flags', '[]') or '[]')
            self.flags: Set[str] = set(flag.upper() for flag in flags_list)
        except (json.JSONDecodeError, TypeError): self.flags = set()

        self.respawn_delay: int = template_data.get('respawn_delay_seconds', 300)
        self.movement_chance: float = template_data.get('movement_chance', 0.0)

        # --- Initialize Runtime State ---
        self.target: Optional[Union['Character', 'Mob']] = None # Corrected hint
        self.is_fighting: bool = False
        self.roundtime: float = 0.0
        self.time_of_death: Optional[float] = None

        # log.debug("Mob instance created: %s (Instance: %d, Template: %d, HP: %d/%d) in Room %d",
        #         self.name, self.instance_id, self.template_id, self.hp, self.max_hp, self.location.dbid)

    def is_alive(self) -> bool:
        return self.hp > 0 and self.time_of_death is None

    def tick_roundtime(self, dt: float):
        """Decrements active roundtime."""
        if self.roundtime > 0:
            self.roundtime = max(0.0, self.roundtime - dt)

    def choose_attack(self) -> Optional[Dict[str, Any]]:
        """Selects an attack from the available list (basic random)."""
        if not self.attacks:
            return None
        return random.choice(self.attacks)

    def die(self):
        """Handles mob death."""
        log.info("MOB DEATH: %s (Instance: %d) entering die() method.", self.name.capitalize(), self.instance_id) # Add entry log
        self.hp = 0
        self.target = None
        self.is_fighting = False
        self.roundtime = 0.0 # Clear roundtime on death
        self.time_of_death = time.monotonic()
        # Loot drop handled by combat system calling something like get_loot()

    def respawn(self):
        """Resets mob state for respawning."""
        if self.is_alive(): return # Cannot respawn if alive

        log.info("RESPAWN: %s (Instance: %d) respawns in Room %d.",
            self.name.capitalize(), self.instance_id, getattr(self.location,'dbid','?'))
        self.hp = self.max_hp
        self.target = None
        self.is_fighting = False
        self.roundtime = 0.0
        self.time_of_death = None

    async def move(self, direction: str, world: 'World'):
        """Handles the logic for a mob moving to an adjacent room."""
        if not self.is_alive() or not self.location:
            return

        target_room_id = None
        exit_data = self.location.exits.get(direction.lower())

        # Mobs only use simple exits for now (value is int)
        if isinstance(exit_data, int):
            target_room_id = exit_data
        # Ignore complex exits (dict) for mob movement in V1
        # else: log.debug("Mob %s found complex exit %s, ignoring for movement.", self.instance_id, direction)

        if target_room_id is None:
            # This shouldn't happen if we only choose from valid simple exits, but safety check
            log.warning("Mob %s (%s) tried to move invalid direction %s from room %d.",
                        self.instance_id, self.name, direction, self.location.dbid)
            return

        target_room = world.get_room(target_room_id)
        if target_room is None:
            log.error("Mob %s (%s) tried to move to non-existent room %d from room %d.",
                    self.instance_id, self.name, target_room_id, self.location.dbid)
            return
        
        current_area_id = self.location.area_id
        target_area_id = target_room.area_id

        if current_area_id != target_area_id:
            # Mob doesn't get feedback, just doesn't move.
            # We might apply roundtime here anyway to prevent getting stuck trying the same exit?
            self.roundtime = 1.0 # Apply small RT for failed area change attempt
            return # Stop the move function

        current_room = self.location
        mob_name_cap = self.name.capitalize()

        # 1. Announce departure
        departure_msg = f"\r\n{mob_name_cap} leaves {direction}.\r\n"
        await current_room.broadcast(departure_msg) # Send to everyone including mob? Or exclude? Let's send to all for now.

        # 2. Remove mob from old room
        current_room.remove_mob(self)

        # 3. Update mob's location reference
        self.location = target_room # Update internal location reference

        # 4. Add mob to new room
        target_room.add_mob(self)

        # 5. Announce arrival
        arrival_msg = f"\r\n{mob_name_cap} arrives.\r\n"
        await target_room.broadcast(arrival_msg)

        # 6. Apply roundtime for moving
        self.roundtime = 4.0 # Example fixed move roundtime for mobs

    def has_flag(self, flag_name: str) -> bool:
        """Check if the mob has a specific flag (case-insensitive)."""
        # Assumes self.flags is a set of UPPERCASE strings loaded in __init__
        return flag_name.upper() in self.flags

    async def simple_ai_tick(self, dt: float, world: 'World'):
        """Basic AI logic called by the ticker via Room/World."""
        # Import combat locally within the method to prevent cycles
        from . import combat

        if not self.is_alive(): return
        self.tick_roundtime(dt)
        if self.roundtime > 0: return

        # --- Combat Logic (if fighting) ---
        if self.is_fighting and self.target:
            # Check if target is still valid first
            target_is_valid = self.target.is_alive() and hasattr(self.target, 'location') and self.target.location == self.location
            if not target_is_valid:
                self.target = None
                self.is_fighting = False
                return # <<< ADDED/CONFIRMED return statement here
            else:
                # Target IS valid, proceed with attack attempt
                attack_data = self.choose_attack()
                if attack_data:
                    attk_name = attack_data.get("name", "attack")
                    # self.target is guaranteed to be non-None here
                    log.debug("%s uses %s against %s!", self.name.capitalize(), attk_name, self.target.name)
                    try:
                        await combat.resolve_physical_attack(self, self.target, attack_data, world)
                    except Exception as combat_e:
                        log.exception("Error during mob %s resolving attack on %s: %s", self.name, self.target.name, combat_e)
                        self.roundtime = 1.0 # Small cooldown after error
                else:
                    log.warning("%s is fighting %s but has no attacks defined!", self.name, self.target.name)
                    self.roundtime = 2.0 # Default cooldown

        # --- Movement Logic (if NOT fighting and can move) ---
        if not self.is_fighting and self.movement_chance > 0 and not self.has_flag("STATIONARY"):
            is_aggressive = self.has_flag("AGGRESSIVE")
            if random.random() < self.movement_chance:
                possible_exits = [
                    direction for direction, target in self.location.exits.items()
                    if isinstance(target, int) # Only simple integer exits
                ]
                if possible_exits:
                    chosen_direction = random.choice(possible_exits)
                    await self.move(chosen_direction, world)
                    # Return after attempting move prevents AGGRO check in same tick
                    return


        # --- Aggressive Check (if NOT fighting and didn't move) ---
        # Use elif to ensure this doesn't run if the mob just moved
        if self.has_flag("AGGRESSIVE") and not self.is_fighting:
            if not self.location: # Safety check
                log.warning("Aggressive mob %s has no location!", self.name)
                return
            
            current_char_set = self.location.characters
            current_char_names = {c.name for c in current_char_set} # Get names for logging
            current_chars_in_room = list(self.location.characters) # Get current characters
            
        
            potential_targets = [
                char for char in self.location.characters if char.is_alive()
            ]
            if potential_targets:
                self.target = random.choice(potential_targets)
                self.is_fighting = True
                log.info("%s becomes aggressive towards %s!", self.name.capitalize(), self.target.name)
                # Optional: Announce aggression?
                # await self.location.broadcast(...)
                # Try to attack immediately if roundtime allows
                if self.roundtime == 0.0:
                    # We can safely call recursively here, as the next iteration
                    # will enter the 'is_fighting' block and not this 'AGGRESSIVE' one.
                    await self.simple_ai_tick(0.0, world)

                    #TODO: Add other mob abilities, healing, area attacks, legendary actions

    def get_total_av(self, world: 'World') -> int:
        """Mobs don't wear armor in V1. Returns 0."""
        # TODO: Mobs should definitely get some armor value eventually...
        return 0

    def __repr__(self) -> str:
        return f"<Mob Inst:{self.instance_id} Tmpl:{self.template_id} '{self.name}' HP:{self.hp}/{self.max_hp}>"

    def __str__(self) -> str:
        return self.name.capitalize() # Simple name for display