# game/mob.py
"""
Represents Mob (Mobile Object / Non-Player Character) instances.
"""
import time
import random
import json
import logging
from . import utils
# from . import combat
from typing import TYPE_CHECKING, Optional, Dict, Any, List, Set

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

    def __init__(self, template_data: Dict[str, Any], current_room: 'Room'):
        """
        Initializes a Mob instance from template data.

        Args:
            template_data: A dictionary derived from the mob_templates row.
            current_room: The Room object where the mob is initially placed.
        """
        self.instance_id: int = Mob.next_instance_id
        Mob.next_instance_id += 1

        self.template_id: int = template_data['id']
        self.name: str = template_data['name'] # Usually includes 'a'/'an' e.g. "a giant rat"
        self.description: str = template_data['description']
        self.level: int = template_data['level']
        self.max_hp: int = template_data['max_hp']
        self.target: Optional['Character'] = None
        self.is_fighting: bool = False
        # TODO: Apply variance to HP/stats later? For V1, use template directly.
        self.hp: int = self.max_hp

        self.location: 'Room' = current_room

        # Load stats, attacks, loot, flags, respawn delay
        try:
            self.stats: Dict[str, int] = json.loads(template_data['stats'] or '{}')
        except (json.JSONDecodeError, TypeError):
            self.stats = {}
        try:
            self.attacks: List[Dict[str, Any]] = json.loads(template_data['attacks'] or '[]')
        except (json.JSONDecodeError, TypeError):
            self.attacks = []
        try:
            self.loot_table: Dict[str, Any] = json.loads(template_data['loot'] or '{}')
        except (json.JSONDecodeError, TypeError):
            self.loot_table = {}
        try:
            flags_list = json.loads(template_data['flags'] or '[]')
            self.flags: Set[str] = set(flag.upper() for flag in flags_list)
        except (json.JSONDecodeError, TypeError):
            self.flags = set()

        self.respawn_delay: int = template_data['respawn_delay_seconds']

        # Runtime State
        self.target: Optional['Character'] = None # Current combat target
        self.is_fighting: bool = False
        self.roundtime: float = 0.0
        self.time_of_death: Optional[float] = None # Timestamp when killed

        log.debug("Mob instance created: %s (Instance: %d, Template: %d) in Room %d",
                self.name, self.instance_id, self.template_id, self.location.dbid)

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

    async def simple_ai_tick(self, dt: float, world: 'World'): # <<< Add world param
        """Basic AI logic called by the ticker via Room/World."""
        from . import combat # Moved import to prevent circular error
        if not self.is_alive(): return

        self.tick_roundtime(dt) # Decay roundtime first
        if self.roundtime > 0: return # Still busy

        # --- Basic Retaliation / Action Logic ---
        if self.is_fighting and self.target:
            # Check if target is still valid
            if not self.target.is_alive() or self.target.location != self.location:
                log.debug("%s's target %s is gone. Stopping combat.", self.name, getattr(self.target,'name','?'))
                self.target = None
                self.is_fighting = False
                return # Stop acting this tick

            # If ready, attempt an attack (basic version)
            attack_data = self.choose_attack()
            if attack_data:
                attk_name = attack_data.get("name", "attack")
                # Call the main combat resolution function
                log.debug("%s uses %s against %s!", self.name.capitalize(), attk_name, self.target.name)
                # We need the combat module imported here
                # We pass the attack_data dict instead of a weapon Item
                await combat.resolve_physical_attack(self, self.target, attack_data, world) # Pass world
                # Roundtime applied inside resolve_physical_attack now
            else:
                log.warning("%s is fighting but has no attacks defined!", self.name)
                self.roundtime = 2.0 # Default cooldown if no attacks

        elif self.has_flag("AGGRESSIVE") and not self.is_fighting:
            # Find a player character in the room to attack
            potential_targets = [
                char for char in self.location.characters if char.is_alive()
            ]
            if potential_targets:
                self.target = random.choice(potential_targets)
                self.is_fighting = True
                log.info("%s becomes aggressive towards %s!", self.name.capitalize(), self.target.name)
                # Optionally announce aggression to room?
                # await self.location.broadcast(f"\r\n{self.name.capitalize()} growls and turns towards {self.target.name}!\r\n")
                # Try to attack immediately if possible
                if self.roundtime == 0.0:
                    await self.simple_ai_tick(0.0, world) # Re-call with world


        # TODO: Add movement logic later if not STATIONARY
        # TODO: Add other behaviors (healing, special abilities) later

    def has_flag(self, flag_name: str) -> bool:
        """Check if the mob has a specific flag (case-insensitive)."""
        return flag_name.upper() in self.flags

    def get_total_av(self, world: 'World') -> int:
        """Mobs don't wear armor in V1. Returns 0."""
        # TODO: Mobs should definitely get some armor value eventually...
        return 0

    def __repr__(self) -> str:
        return f"<Mob Inst:{self.instance_id} Tmpl:{self.template_id} '{self.name}' HP:{self.hp}/{self.max_hp}>"

    def __str__(self) -> str:
        return self.name.capitalize() # Simple name for display