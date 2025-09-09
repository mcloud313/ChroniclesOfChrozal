# game/commands/combat.py
"""
Combat related commands like attack.
"""
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..character import Character
    from ..world import World
    import aiosqlite

# Import combat logic handler
from .. import combat as combat_logic
from ..mob import Mob

log = logging.getLogger(__name__)


async def cmd_attack(character: 'Character', world: 'World', args_str: str) -> bool:
    """Handles the 'attack <target>' command."""
    if character.stance != "Standing":
        await character.send("You must be standing to attack.")
        return True
    if not args_str:
        await character.send("Attack whom?")
        return True
    
    if not character.location:
        await character.send("You cannot attack from the void.")
        return True
    
    target_name = args_str.strip().lower()
    target = character.location.get_mob_by_name(target_name)

    if not target:
        await character.send(f"You don't see '{target_name}' here to attack.")
        return True
    
    log.info("%s is initiating combat with %s.", character.name, target.name)

    character.target = target
    character.is_fighting = True

    if not target.is_fighting:
        target.target = character
        target.is_fighting = True

    await character.send(f"You attack {target.name}!")

    weapon = None
    if weapon_template_id := character.equipment.get("WIELD_MAIN"):
        weapon = character.get_item_instance(world, weapon_template_id)
        if weapon and weapon.item_type != "WEAPON":
            weapon = None
    
    await combat_logic.resolve_physical_attack(character, target, weapon, world)
    return True