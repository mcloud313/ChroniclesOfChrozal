# game/mob.py
"""
Represents Mob (Mobile Object / Non-Player Character) instances.
"""
import time
import random
import json
import logging
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
        if not self.is_alive(): return # Already dead

        log.info("%s (Instance: %d) has died in Room %d.",
                self.name.capitalize(), self.instance_id, self.location.dbid)
        self.hp = 0
        self.target = None
        self.is_fighting = False
        self.roundtime = 0.0 # Clear roundtime on death
        self.time_of_death = time.monotonic()
        # Loot drop handled by combat system calling something like get_loot()

    def respawn(self):
        """Resets mob state for respawning."""
        if self.is_alive(): return # Cannot respawn if alive

        log.info("%s (Instance: %d) respawns in Room %d.",
            self.name.capitalize(), self.instance_id, self.location.dbid)
        self.hp = self.max_hp
        self.target = None
        self.is_fighting = False
        self.roundtime = 0.0
        self.time_of_death = None

    async def simple_ai_tick(self, dt: float):
        """Basic AI logic called by the ticker via Room/World."""
        if not self.is_alive():
            return # Dead mobs don't act

        # Tick roundtime first
        self.tick_roundtime(dt)
        if self.roundtime > 0:
            return # Still busy

        # Basic Retaliation / Action Logic
        if self.is_fighting and self.target:
            if not self.target.is_alive() or self.target.location != self.location:
                # Target died or left room
                log.debug("%s's target %s is gone. Stopping combat.", self.name, getattr(self.target,'name','?'))
                self.target = None
                self.is_fighting = False
            else:
                # Attack target if ready
                attack = self.choose_attack()
                if attack:
                    # We need the combat system here! Placeholder log.
                    log.debug("%s attacks %s with %s!", self.name, self.target.name, attack.get('name','attack'))
                    # Apply roundtime based on attack speed
                    self.roundtime = attack.get('speed', 2.0)
                    # In actual combat system: await combat_handler.resolve_attack(self, self.target, attack)
                else:
                    log.warning("%s is fighting but has no attacks defined!", self.name)
                    # Apply a default cooldown?
                    self.roundtime = 2.0

        elif self.has_flag("AGGRESSIVE") and not self.is_fighting:
            # Find a player character in the room to attack
            potential_targets = [
                char for char in self.location.characters if char.is_alive() # Check if character is alive
            ]
            if potential_targets:
                self.target = random.choice(potential_targets)
                self.is_fighting = True
                log.info("%s becomes aggressive towards %s!", self.name.capitalize(), self.target.name)
                # Potentially start attack immediately or wait for next tick
                # Let's attack immediately if roundtime is 0
                if self.roundtime == 0.0:
                    await self.simple_ai_tick(0.0) # Re-call AI tick to perform attack


        # TODO: Add movement logic later if not STATIONARY
        # TODO: Add other behaviors (healing, special abilities) later

    def has_flag(self, flag_name: str) -> bool:
        """Check if the mob has a specific flag (case-insensitive)."""
        return flag_name.upper() in self.flags

    def __repr__(self) -> str:
        return f"<Mob Inst:{self.instance_id} Tmpl:{self.template_id} '{self.name}' HP:{self.hp}/{self.max_hp}>"

    def __str__(self) -> str:
        return self.name.capitalize() # Simple name for display