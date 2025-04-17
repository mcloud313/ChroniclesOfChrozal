# game/commands/skill.py
"""
Commands related to character skills (e.g., spending points).
"""

import logging
from typing import TYPE_CHECKING
from .. import utils # <<< ADD THIS IMPORT

if TYPE_CHECKING:
    from ..character import Character
    from ..world import World
    import aiosqlite

# Import skill definitions to validate skill names
from ..definitions import skills as skill_defs

VALID_ATTRIBUTES = {"might", "vitality", "agility", "intellect", "aura", "persona"}

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
        try:
            amount_to_spend = int(parts[1])
            if amount_to_spend <= 0:
                await character.send("You must spend a positive number of points.")
                return True
        except ValueError:
            # Couldn't convert part[1] to int, maybe multi-word skill?
            skill_name_target = args_str.lower() # Assume full args is skill name
            amount_to_spend = 1 # Reset amount to default
        except IndexError:
            # Should not happen if len(parts) > 1, but safety
            amount_to_spend = 1

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

async def cmd_improve(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Spends an attribute point to increase a core stat."""

    if not args_str:
        await character.send("Improve which attribute? (Might, Vitality, Agility, Intellect, Aura, Persona)")
        await character.send(f"You have {character.unspent_attribute_points} attribute points available.")
        return True

    stat_name_input = args_str.strip().lower()

    # 1. Validate Stat Name
    if stat_name_input not in VALID_ATTRIBUTES:
        await character.send(f"'{stat_name_input.capitalize()}' is not a valid attribute you can improve.")
        await character.send(f"Choose from: {', '.join(s.capitalize() for s in VALID_ATTRIBUTES)}.")
        return True

    # 2. Check Available Points
    if character.unspent_attribute_points <= 0:
        await character.send("You have no attribute points available to spend.")
        # Remind when they get points?
        next_level_gain = 4 - (character.level % 4)
        if next_level_gain == 4 and character.level >= 4: # Handle level 4 itself
            next_level_gain = 4
        elif character.level < 4:
            next_level_gain = 4 - character.level
        await character.send(f"You gain an attribute point every 4 levels (Next at level {character.level + next_level_gain}).")
        return True

    # 3. Apply Improvement (No confirmation step for V1)
    current_value = character.stats.get(stat_name_input, 0) # Get current value
    new_value = current_value + 1

    # Decrement point first
    character.unspent_attribute_points -= 1
    # Increment stat
    character.stats[stat_name_input] = new_value
    log.info("Character %s improved %s from %d to %d. %d points remaining.",
            character.name, stat_name_input, current_value, new_value, character.unspent_attribute_points)

    # 4. Recalculate Derived Stats (Max HP/Essence depend on Vit/Aura/Pers)
    # Ensure calculate_derived_max_attributes ONLY sets max values now
    character.calculate_derived_max_attributes()

    # 5. Send Feedback
    await character.send(f"You focus your energies and improve your {stat_name_input.capitalize()}!")
    await character.send(f"({stat_name_input.capitalize()} is now {new_value}. You have {character.unspent_attribute_points} attribute points remaining.)")
    # Optionally show HP/Essence changes if they occurred
    await character.send(f"(Your Max HP is now {int(character.max_hp)}, Max Essence is now {int(character.max_essence)})")


    # No roundtime for spending points usually
    return True