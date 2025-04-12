# game/commands/general.py
"""
General player commands like look, say, quit, who help.
"""
import math
import logging
import config
from typing import TYPE_CHECKING
from .. import utils

# Avoid circular imports with type checking
if TYPE_CHECKING:
    from ..character import Character
    from ..world import World
    import aiosqlite

log = logging.getLogger(__name__)

# --- Command Functions ---
# Note: These functions match the CommandHandlerFunc signature

async def cmd_look(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Handles the 'look' command (looking at room or target character)."""

    if not character.location:
        await character.send("You are floating in an endless void... somehow.")
        log.warning("Character %s tried to look but has no location.", character.name)
        return True # Keep connection active
    
    target_name = args_str.strip()

    # --- Look at Room (No arguments) ---
    if not target_name:
        look_desc = character.location.get_look_string(character)
        await character.send(look_desc)
        return True
    
    # --- Look at Target (Character) ---
    target = character.location.get_character_by_name(target_name)

    # Handle target not found
    if target is None:
        # TODO: Later, check for items/objects in the room here too
        await character.send(f"You don't see anyone or anything named '{target_name}' here.")
        return True
    
    # Handle looking at self - show room description (standard MUD behavior)
    if target == character:
        look_desc = character.location.get_look_string(character)
        await character.send(look_desc)
        return True
    
    # --- Format Target Character's Description ---
    try:
        # Get Race/Class Names
        target_race_name = world.get_race_name(target.race_id)
        target_class_name = world.get_class_name(target.class_id)

        # Get Pronouns
        pronoun_subj, _, _, verb_is, _ = utils.get_pronouns(target.sex)

        output = "\r\n"
        # Display the generated description stored on the character
        output += target.description # Assumes target.description is loaded from DB
        output += "\r\n"
        # Add basic info line
        output += f"({target_race_name} {target_class_name}, Level {target.level})\r\n"
        # Add equipment placeholder
        output += f"{pronoun_subj} {verb_is} wearing:\r\n Nothing." # Placeholder
        # TODO: Add wielded item placeholder later

        await character.send(output)
    
    except Exception:
        log.exception("Error generating look description for target %s:", target.name, exc_info=True)
        await character.send("You look at them, but your vision blurs momentarily.")

    return True # Keep connection active

async def cmd_say(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Handles the 'say' command."""
    if not args_str:
        await character.send("Say what?")
        return True
    
    if not character.location:
        log.warning("Character %s tried to say but has no location.", character.name)
        await character.send("You try to speak, but no sound comes out.")
        return True
    
    speaker_msg = f"You say: \"{args_str}\""
    broadcast_msg = f"{character.first_name} says: \"{args_str}\""
    # Send message to self
    await character.send(speaker_msg) # Already adds \r\n in send()

    # Broadcast to room (add line endings for broadcast here)
    await character.location.broadcast(broadcast_msg + "\r\n", exclude={character})
    return True

async def cmd_quit(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Handles the 'quit' command."""
    await character.send("Farewell!")
    log.info("Character %s is quitting.", character.name)
    await character.save(db_conn) # Save character state
    return False

async def cmd_who(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Handles the 'who' command"""
    active_chars = world.get_active_characters_list()
    if not active_chars:
        await character.send("You appear to be all alone in the world...")
        return True
    
    output = "\r\n--- Currently Online ---\r\n"
    # TODO: Add Title/Class/Race info later
    for char in sorted(active_chars, key=lambda c: c.name):
        # Simple name list for now
        output += f"{char.name}\r\n"
    output += "--------------------------\r\n"
    output += f"Total players: {len(active_chars)}\r\n"

    await character.send(output)
    return True

async def cmd_help(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Handles the 'help' command."""
    # TODO: Implement a proper help system later (e.g., help <command>)
    output = "\r\n--- Basic Commands ---\r\n"
    output += " look              - Look around the room.\r\n"
    output += " north, south      - Move in a direction (aliases: n, s, etc.).\r\n"
    output += " east, west        - \r\n"
    output += " up, down          - \r\n"
    output += " say <message>   - Speak to others in the room.\r\n"
    output += " who               - List players currently online.\r\n"
    output += " help              - Show this help message.\r\n"
    output += " quit              - Leave the game.\r\n"
    output += "----------------------\r\n"

    await character.send(output)
    return True

async def cmd_score(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Handles the 'score/stats' command."""

    # --- Gather Data ---
    char_name = character.name
    char_sex = character.sex
    # Get race/class names safely using world lookup
    race_name = world.get_race_name(character.race_id)
    class_name = world.get_class_name(character.class_id)
    level = character.level
    hp = character.hp
    max_hp = character.max_hp
    essence = character.essence
    max_essence = character.max_essence
    xp_pool = character.xp_pool # unspent banked XP
    xp_total = character.xp_total # xp earned this level
    xp_needed = utils.xp_needed_for_level(level)
    coinage = character.coinage # Get from character attribute
    formatted_coinage = utils.format_coinage(coinage) # Use the util function

    # Attribute and Modifiers
    stats = character.stats # The dict like {'might': 15, ....}
    tether = character.spiritual_tether
    attributes_display = []
    stat_order = ["might", "vitality", "agility", "intellect", "aura", "persona"]
    modifiers = {} # Store modifiers for reuse
    for stat_name in stat_order:
        value = stats.get(stat_name, 10) # Get value, default 10
        modifier = utils.calculate_modifier(value)
        modifiers[stat_name] = modifier # Store modifier
        mod_sign = "+" if modifier >= 0 else "" # Add plus sign for positive/zero
        attributes_display.append(f" {stat_name.capitalize():<10}: {value:>2} [{mod_sign}{modifier}]")

    # Derived Stats
    might_val = stats.get("might", 10)
    max_carry_weight = might_val * 3
    curr_w = character.get_current_weight(world)

    # Coinage (Deferred until Phase 3)
    # coinage = character.coinage # Need this attribute added later
    # formatted_coinage = utils.format_coinage(coinage) # Need this util later

    # --- Format Output ---
    # Using f-strings with padding for alignment
    output = "\r\n" + "=" * 50 + "\r\n"
    output += f" Name : {char_name:<28} Sex: {char_sex}\r\n"
    output += f" Race : {race_name:<28} Class: {class_name}\r\n"
    output += f" Level: {level:<31}\r\n"
    output += "=" * 50 + "\r\n"
    output += f" HP   : {hp:>4}/{max_hp:<28} Carry: {curr_w:>2}/{max_carry_weight:<3} stones\r\n"
    output += f" Essn : {essence:>4}/{max_essence:<31}\r\n"
    output += f" XP   : {int(xp_total):>4}/{xp_needed:<28} Pool: {int(xp_pool)}\r\n"
    output += f" Tether: {tether:<30}\r\n" # Adjust padding if needed
    output += " --- Attributes ---                 \r\n" # Adjusted spacing
    # Display 3 attributes per line
    output += f"{attributes_display[0]} {attributes_display[1]}\r\n"
    output += f"{attributes_display[2]} {attributes_display[3]}\r\n"
    output += f"{attributes_display[4]} {attributes_display[5]}\r\n"
    output += f" Skill Pts: {character.unspent_skill_points:<25} Attrib Pts: {character.unspent_attribute_points}\r\n"
    output += f" Coins: {formatted_coinage:<31}\r\n"
    output += "=" * 50 + "\r\n"

    await character.send(output)
    return True # Keep connection active

async def cmd_advance(character: 'Character', world: 'World', db_conn:'aiosqlite.Connection', args_str: str) -> bool:
    """Handles the 'advance' command for levelling up."""
    #1. Check location
    if not character.location or "NODE" not in character.location.flags:
        await character.send("You must be in a designated safe Node to consolidate your experience and advance.")
        return True

    #2. Check Max Level
    max_level = getattr(config, 'MAX_LEVEL', 100)
    if character.level >= max_level:
        await character.send(f"You have already reached the maximum level ({max_level}).")
        return True

    #3. Check XP Eligibility
    xp_needed = utils.xp_needed_for_level(character.level) # Gets threshold for NEXT level
    if character.xp_total < xp_needed:
        xp_more = xp_needed - character.xp_total
        await character.send(f"You require {int(xp_more)} more experience to advance to level {character.level + 1}.")
        return True

    # 4. Increment Level
    character.level += 1
    log.info("Character %s (ID: %s) advanced to level %d!", character.name, character.dbid, character.level)

    # --- Eligibie for Level Up
    sp_gain = getattr(config, 'SKILL_POINTS_PER_LEVEL', 5)
    character.unspent_skill_points += sp_gain
    old_max_hp = character.max_hp
    old_max_essence = character.max_essence

    # 6. Award attribute point (every 4 levels)
    ap_gain = 0
    if character.level % 4 == 0:
        ap_gain = 1
        character.unspent_attribute_points += ap_gain

    # 7. Apply Level Up Gains (Updates Max values and restores current HP/Essence)
    #    This method performs the class die rolls + mods internally.
    hp_gain, essence_gain = character.apply_level_up_gains()
    # --- ^ ^ ^ ---

    log.info("Character %s (ID: %s) advanced to level %d! Gains: HP+%d, Ess+%d, SP+%d, AP+%d",
            character.name, character.dbid, character.level, hp_gain, essence_gain, sp_gain, ap_gain)

    hp_increase = character.max_hp - old_max_hp
    essence_increase = character.max_essence - old_max_essence

    # 8. Format Feedback Message (Uses gains returned from apply_level_up_gains)
    level_msg = ["\r\n{G*** CONGRATULATIONS! ***{x", # Added {x to reset color potentially
                f"You have advanced to level {character.level}!",
                 "=" * 30]

    # Use hp_gain and essence_gain directly from the method call results
    if hp_gain > 0: level_msg.append(f"Maximum HP increased by {hp_gain} (Now: {character.max_hp}).")
    if essence_gain > 0: level_msg.append(f"Maximum Essence increased by {essence_gain} (Now: {character.max_essence}).")
    if sp_gain > 0: level_msg.append(f"You gain {sp_gain} skill points (Total unspent: {character.unspent_skill_points}).")
    if ap_gain > 0: level_msg.append(f"You gain {ap_gain} attribute point (Total unspent: {character.unspent_attribute_points}).")
    level_msg.append("Use 'TRAIN <skill>' to spend skill points.")
    if character.unspent_attribute_points > 0:
        level_msg.append("Use '@setstat' or wait for attribute training command.") # Placeholder

    await character.send("\r\n".join(level_msg))

    # 9. Trigger immediate save after level up? Good practice.
    await character.save(db_conn)

    return True # Keep connection active

async def cmd_skills(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Displays the character's known skills and ranks."""

    output = "\r\n" + "=" * 20 + " Skills " + "=" * 20 + "\r\n"
    output += f" Unspent Skill Points: {character.unspent_skill_points}\r\n"
    output += "-" * (40 + 8) + "\r\n"

    if not character.skills:
        output += " You have not learned any skills yet.\r\n"
    else:
        # Display skills, maybe sorted alphabetically
        # Could enhance later to show governing attribute
        skill_lines = []
        for skill_name in sorted(character.skills.keys()):
            rank = character.skills[skill_name]
            if rank > 0: # Optionally only show skills with rank > 0
                skill_lines.append(f" {skill_name.title():<25}: {rank}")
        if not skill_lines:
            output += " You have not trained any skills yet.\r\n"
        else:
            # Simple two-column display?
            # This basic version just lists them. Could format better.
            output += "\r\n".join(skill_lines) + "\r\n"

    output += "=" * (40 + 8) + "\r\n"
    await character.send(output)
    return True

            