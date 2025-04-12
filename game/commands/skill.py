# game/commands/skill.py
"""
Commands related to character skills (e.g., spending points).
"""
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..character import Character
    from ..world import World
    import aiosqlite

# Import skill definitions to validate skill names
from ..definitions import skills as skill_defs

log = logging.getLogger(__name__)


async def cmd_spend(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Spends skill points to increase a skill rank."""
    if not args_str:
        await character.send("Spend points on which skill? (e.g., spend lockpicking)")
        await character.send(f"You have {character.unspent_skill_points} skill points available.")
        return True

    parts = args_str.split()
    skill_name_target = parts[0].lower()
    amount_to_spend = 1
    if len(parts) > 1:
        if parts[1].isdigit():
            amount_to_spend = int(parts[1])
        else:
            # Allow multi-word skill names if first part didn't match fully
            skill_name_target = args_str.lower() # Use full args as skill name
            amount_to_spend = 1 # Reset amount

    if amount_to_spend <= 0:
        await character.send("You must spend at least 1 point.")
        return True

    # Validate skill name
    found_skill_name = None
    if skill_name_target in skill_defs.INITIAL_SKILLS:
        found_skill_name = skill_name_target
    else:
        # Basic partial matching
        possible_matches = [sk for sk in skill_defs.INITIAL_SKILLS if sk.startswith(skill_name_target)]
        if len(possible_matches) == 1:
            found_skill_name = possible_matches[0]

    if not found_skill_name:
        await character.send(f"Unknown skill '{skill_name_target}'. Type 'skills' to see available skills.")
        return True

    # Check points
    if character.unspent_skill_points < amount_to_spend:
        await character.send(f"You don't have enough skill points. You need {amount_to_spend}, but only have {character.unspent_skill_points}.")
        return True

    # Increase skill
    current_rank = character.skills.get(found_skill_name, 0)
    new_rank = current_rank + amount_to_spend
    character.skills[found_skill_name] = new_rank
    character.unspent_skill_points -= amount_to_spend

    log.info("Character %s spent %d points on skill '%s', new rank %d.",
            character.name, amount_to_spend, found_skill_name, new_rank)
    await character.send(f"You focus your learning and improve your {found_skill_name.title()} skill to rank {new_rank}!")
    await character.send(f"({character.unspent_skill_points} skill points remaining).")

    # Apply roundtime for spending points?
    character.roundtime = 2.0 # Example

    return True