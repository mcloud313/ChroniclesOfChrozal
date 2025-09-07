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


async def cmd_attack(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
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
    target = None

    # --- Find Target ---
    # Find the first living mob in the room that matches the partial name.
    target = character.location.get_mob_by_name(target_name)

    # If no mob was found, check for other players.
    if not target:
        target_char = character.location.get_character_by_name(target_name)
        if target_char and target_char != character:
            if not target_char.is_alive():
                await character.send(f"{target_char.name} is already defeated.")
                return True
            # TODO: Add PVP flag checks here in the future.
            target = target_char
        elif target_char == character:
            await character.send("You contemplate attacking yourself, but decide against it.")
            return True
        
    if not target:
        await character.send(f"You don't see '{target_name}' here to attack.")
        return True
    
    # --- Initiate Combat ---
    log.info("%s (HP: %.1f) is initiating combat with %s (HP: %.1f).",
            character.name, character.hp, target.name, target.hp)

    character.target = target
    character.is_fighting = True

    # If the target is a mob and isn't fighting back, make it retaliate.
    if isinstance(target, Mob) and not target.is_fighting:
        target.target = character
        target.is_fighting = True
        log.info("%s is now fighting %s after being attacked.", target.name, character.name)

    await character.send(f"You attack {target.name}!")

    # Get the character's wielded weapon.
    weapon = None
    weapon_template_id = character.equipment.get("WIELD_MAIN")
    if weapon_template_id:
        weapon = character.get_item_instance(world, weapon_template_id)
        if weapon and weapon.item_type != "WEAPON":
            log.debug("%s is trying to attack with a non-weapon: %s", character.name, weapon.name)
            weapon = None # Can't attack with a non-weapon.

    # Hand off to the core combat logic to resolve the attack.
    await combat_logic.resolve_physical_attack(character, target, weapon, world)

    return True