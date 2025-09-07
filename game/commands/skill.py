# game/commands/skill.py
"""
Commands related to character skills and attributes.
"""
import logging
from typing import TYPE_CHECKING
import aiosqlite  # <-- FIX: Added missing import

from .. import utils
from ..definitions import skills as skill_defs

if TYPE_CHECKING:
    from ..character import Character
    from ..world import World

VALID_ATTRIBUTES = {"might", "vitality", "agility", "intellect", "aura", "persona"}
log = logging.getLogger(__name__)


async def cmd_spend(character: 'Character', world: 'World', db_conn: aiosqlite.Connection, args_str: str) -> bool:
    """Spends skill points to increase a skill rank."""
    if not args_str:
        await character.send("Spend points on which skill? (e.g., spend lockpicking)")
        await character.send(f"You have {character.unspent_skill_points} skill points available.")
        return True

    parts = args_str.split()
    skill_name_target = parts[0].lower()
    amount_to_spend = 1
    
    if len(parts) > 1:
        try:
            amount_to_spend = int(parts[1])
        except (ValueError, IndexError):
            skill_name_target = args_str.lower()
            amount_to_spend = 1

    if amount_to_spend <= 0:
        await character.send("You must spend a positive number of points.")
        return True

    found_skill_name = None
    possible_matches = [sk for sk in skill_defs.INITIAL_SKILLS if sk.startswith(skill_name_target)]
    if len(possible_matches) == 1:
        found_skill_name = possible_matches[0]
    elif skill_name_target in skill_defs.INITIAL_SKILLS:
        found_skill_name = skill_name_target

    if not found_skill_name:
        await character.send(f"Unknown skill '{skill_name_target}'. Type 'skills' to see available skills.")
        return True

    if character.unspent_skill_points < amount_to_spend:
        await character.send(f"You don't have enough skill points (have {character.unspent_skill_points}, need {amount_to_spend}).")
        return True

    current_rank = character.skills.get(found_skill_name, 0)
    new_rank = current_rank + amount_to_spend
    character.skills[found_skill_name] = new_rank
    character.unspent_skill_points -= amount_to_spend

    log.info("Character %s spent %d points on '%s', new rank %d.",
             character.name, amount_to_spend, found_skill_name, new_rank)
    await character.send(f"You improve your {found_skill_name.title()} skill to rank {new_rank}!")
    await character.send(f"({character.unspent_skill_points} skill points remaining).")

    character.roundtime = 2.0
    return True


async def cmd_improve(character: 'Character', world: 'World', db_conn: aiosqlite.Connection, args_str: str) -> bool:
    """Spends an attribute point to increase a core stat."""
    if not args_str:
        await character.send("Improve which attribute? (Might, Vitality, Agility, Intellect, Aura, Persona)")
        await character.send(f"You have {character.unspent_attribute_points} attribute points available.")
        return True

    stat_name_input = args_str.strip().lower()

    if stat_name_input not in VALID_ATTRIBUTES:
        await character.send(f"'{stat_name_input.capitalize()}' is not a valid attribute.")
        return True

    if character.unspent_attribute_points <= 0:
        await character.send("You have no attribute points available to spend.")
        return True

    current_value = character.stats.get(stat_name_input, 10)
    new_value = current_value + 1
    character.unspent_attribute_points -= 1
    character.stats[stat_name_input] = new_value
    
    character.recalculate_max_vitals()
    character.hp = min(character.hp, character.max_hp)
    character.essence = min(character.essence, character.max_essence)
    
    log.info("Character %s improved %s to %d. %d points remaining.",
             character.name, stat_name_input, new_value, character.unspent_attribute_points)

    await character.send(f"You focus your energies and improve your {stat_name_input.capitalize()}!")
    await character.send(f"({stat_name_input.capitalize()} is now {new_value}. You have {character.unspent_attribute_points} attribute points remaining.)")
    await character.send(f"(Your Max HP is now {int(character.max_hp)}, Max Essence is now {int(character.max_essence)})")

    return True