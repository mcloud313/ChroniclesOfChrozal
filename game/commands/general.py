# game/commands/general.py
"""
General player commands like look, say, quit, who help.
"""
import aiosqlite
import math
import logging
import config
from typing import TYPE_CHECKING, Optional, Union, Dict, Any, List
from .. import utils
from ..item import Item
from ..mob import Mob

# Avoid circular imports with type checking
if TYPE_CHECKING:
    from ..character import Character
    from ..world import World
    import aiosqlite

log = logging.getLogger(__name__)

# --- Command Functions ---
# Note: These functions match the CommandHandlerFunc signature

async def cmd_look(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Handles looking at room, characters, mobs, or items."""

    if not character.location:
        await character.send("You are floating in an endless void... somehow.")
        return True

    target_name = args_str.strip().lower()

    # --- Case 1: Look Room (no arguments) ---
    if not target_name or target_name == "here":
        room_desc = character.location.get_look_string(character, world) # Get base desc
        await character.send(room_desc) # Send base desc

        # Now add items and coinage on ground
        ground_items_output = []
        # Group items by template ID
        item_counts = {}
        for item_id in character.location.items:
            item_counts[item_id] = item_counts.get(item_id, 0) + 1

        for template_id, count in sorted(item_counts.items()):
            template = world.get_item_template(template_id)
            item_name = template['name'] if template else f"Item #{template_id}"
            display_name = item_name
            if count > 1: display_name += f" (x{count})"
            ground_items_output.append(display_name)

        coinage = character.location.coinage
        if coinage > 0:
            ground_items_output.append(utils.format_coinage(coinage)) # Add formatted coins

        if ground_items_output:
            await character.send("You also see here: " + ", ".join(ground_items_output) + ".")

        return True

    # --- Case 2: Look Target ---
    target_found = False
    output_buffer = [] # Build output lines

    # 1. Check Characters in room
    target_char = character.location.get_character_by_name(target_name)
    if target_char:
        target_found = True
        if target_char == character:
            # Look self - show score? Or basic desc? Let's show basic desc like looking at others
            output_buffer.append("\r\n" + character.description + "\r\n")
            race_name = world.get_race_name(character.race_id)
            class_name = world.get_class_name(character.class_id)
            pronoun_subj, _, _, verb_is, _ = utils.get_pronouns(character.sex)
            output_buffer.append(f"({race_name} {class_name}, Level {character.level})")
            output_buffer.append(f"{pronoun_subj} {verb_is} wearing:\r\n Nothing.") # Placeholder
        else:
            # Look other character
            try:
                target_race_name = world.get_race_name(target_char.race_id)
                target_class_name = world.get_class_name(target_char.class_id)
                pronoun_subj, _, _, verb_is, _ = utils.get_pronouns(target_char.sex)
                output_buffer.append("\r\n" + target_char.description + "\r\n")
                output_buffer.append(f"({target_race_name} {target_class_name}, Level {target_char.level})")
                output_buffer.append(f"{pronoun_subj} {verb_is} wearing:\r\n Nothing.") # Placeholder
            except Exception:
                log.exception("Error generating look description for target %s:", target_char.name, exc_info=True)
                output_buffer.append("You look, but your vision blurs momentarily.")

    # 2. Check Mobs in room (if no character found)
    if not target_found:
        target_mob = character.location.get_mob_by_name(target_name)
        if target_mob:
            target_found = True
            output_buffer.append(f"\r\n{target_mob.description}\r\n")
            # Maybe add brief HP status? ("looks healthy", "is wounded") - later polish
            # output_buffer.append(f"{target_mob.name.capitalize()} looks healthy.")

    if not target_found and hasattr(character.location, 'get_object_by_keyword'):
        target_obj_data = character.location.get_object_by_keyword(target_name)
        if target_obj_data:
            target_found = True
            # Just display the object's description
            output_buffer.append(f"\r\n{target_obj_data.get('description', 'It looks unremarkable.')}\r\n")

    # 3. Check Items on Ground (if no char/mob found)
    if not target_found:
        item_id_on_ground = None
        items_on_ground = list(character.location.items)
        for t_id in items_on_ground:
            template = world.get_item_template(t_id)
            if template and target_name in template['name'].lower():
                item_id_on_ground = t_id
                break
        if item_id_on_ground:
            target_found = True
            item = character.get_item_instance(world, item_id_on_ground)
            if item: output_buffer.append(f"\r\n{item.description}\r\n") # Just show desc for now
            else: output_buffer.append("You see it, but cannot make out details.")

    # 4. Check Items in Inventory (if not found elsewhere)
    if not target_found:
        # Pass world to finder
        item_id_in_inv = character.find_item_in_inventory_by_name(world, target_name)
        if item_id_in_inv:
            target_found = True
            item = character.get_item_instance(world, item_id_in_inv) # Pass world
            if item: output_buffer.append(f"\r\n{item.description}\r\n") # Just show desc
            else: output_buffer.append("You look at it, but cannot make out details.")

    # 5. Send result or Not Found Message
    if target_found:
        await character.send("\r\n".join(output_buffer))
    else:
        await character.send(f"You don't see anything like '{target_name}' here.")

    return True # Command processed

async def cmd_say(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Handles the 'say' command."""
    if not args_str:
        await character.send("Say what?")
        return True
    
    message = args_str.strip()
    if len(message) > config.MAX_INPUT_LENGTH:
        await character.send(f"That message is too long (max {config.MAX_INPUT_LENGTH} characters).")
        return True
    
    if not character.location:
        log.warning("Character %s tried to say but has no location.", character.name)
        await character.send("You try to speak, but no sound comes out.")
        return True
    
    speaker_msg = f"You say: \"{message}\""
    broadcast_msg = f"{character.first_name} says: \"{message}\""
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
    """Handles the 'who' command, listing online characters."""
    # TODO: Add characters that are offline that have logged in the last 30 days
    active_chars = world.get_active_characters_list()
    if not active_chars:
        await character.send("You appear to be all alone in the world...")
        return True
    
    output = "\r\n{{C--- Players Online ({count}) ---{{x\r\n".format(count=len(active_chars))
    # Sort by level? Or name? Let's sort by name for now.
    active_chars.sort(key=lambda char: char.name)

    who_lines = []
    for char in active_chars:
        try:
            # Fetch race and class names using the World helpers
            race_name = world.get_race_name(char.race_id) or "Unknown Race"
            class_name = world.get_class_name(char.class_id) or "Unknown Class"
            # TODO: Add Title lookup later based on status, level, achievements etc.
            title = "" # Placeholder for title
            # Format: [Lvl] Name Surname Title (Race Class)
            who_lines.append(f"[{char.level: >2}] {char.name:<25} {title:<15} ({race_name} {class_name})")
        except Exception:
            log.exception("Error formatting who entry for char %s", getattr(char, 'dbid', '?'))
            who_lines.append(f"[??] {getattr(char, 'name', 'Someone')} (Error loading info)")

    output += "\r\n".join(who_lines)
    output += "\r\n{{C----------------------------{{x\r\n" # Corrected Footer
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

    # --- Calculate Armor Values ---
    total_av = character.get_total_av(world)
    barrier_val = character.barrier_value # Use the property
    armor_training_rank = character.get_skill_rank("armor training")
    av_multiplier = min(1.0, 0.20 + (armor_training_rank * 0.01))
    effective_av = math.floor(total_av * av_multiplier)

    # --- Format Output ---
    # Using f-strings with padding for alignment
    output = "\r\n" + "=" * 50 + "\r\n"
    output += f" Name : {char_name:<28} Sex: {char_sex}\r\n"
    output += f" Race : {race_name:<28} Class: {class_name}\r\n"
    output += f" Level: {level:<31}\r\n"
    output += "=" * 50 + "\r\n"
    output += f" HP   : {int(hp):>4}/{int(max_hp):<28} Carry: {curr_w:>2}/{max_carry_weight:<3} stones\r\n"
    output += f" Armor: {effective_av:>4}/{total_av:<28} (Effective/Total)\r\n"
    output += f" Barrier: {barrier_val:<28} \r\n" # Display Barrier Value
    output += f" Essn : {int(essence):>4}/{int(max_essence):<31}\r\n"
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
    if hp_gain > 0: level_msg.append(f"Maximum HP increased by {int(hp_gain)} (Now: {int(character.max_hp)}).")
    if essence_gain > 0: level_msg.append(f"Maximum Essence increased by {int(essence_gain)} (Now: {int(character.max_essence)}).")
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

async def cmd_meditate(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Begins meditiation to restore essence faster."""

    if character.status != "ALIVE":
        await character.send("You cannot meditate right now.")
        return True
    if character.stance != "Sitting":
        await character.send("You must be sitting down to meditate properly.")
        return True
    if character.is_fighting:
        await character.send("You cannot meditate while fighting!")
        return True
    if character.roundtime > 0:
        await character.send("You must be stll to meditate.")
        return True
    if character.casting_info:
        await character.send("You cannot meditate while preparing another action.")
        return True
    character.status = "MEDITATING"
    # apply a short roundtime for starting meditation
    character.roundtime = 10.0
    await character.send("You sit down and begin to meditate, focusing your inner energy.")
    # optionally broadcast? "X sits down and begins meditating"
    # if character.location: await character.location.broadcast
    # TODO: Broadcast meditation
    # TODO: Change character stance to sitting.
    return True

async def cmd_emote(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Performs an action visible to the room"""
    if not args_str:
        await character.send("Emote what?")
        return True
    
    # Potentially sanitize args_str later to prevent exploits
    action_text = args_str.strip()

    if len(action_text) > config.MAX_INPUT_LENGTH:
        await character.send(f"That emote is too long (max {config.MAX_INPUT_LENGTH} characters).")
        return True

    # Message to self (includes "You emote:")
    self_msg = f"You emote: {character.name} {action_text}"
    #Message to others
    room_msg = f"\r\n{character.name} {action_text}\r\n"

    await character.send(self_msg)
    if character.location:
        await character.location.broadcast(room_msg, exclude={character})
    # Emotes usually don't take roundtime
    return True

async def cmd_tell(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Sends a private message to another player online."""
    if not args_str or ' ' not in args_str:
        await character.send("Tell whom what?")
        return True
    
    try:
        target_name, message = args_str.split(" ", 1)
    except ValueError:
        await character.send("Tell whom what?")
        return True
    
    if len(message) > config.MAX_INPUT_LENGTH:
        await character.send(f"That tell message is too long (max {config.MAX_INPUT_LENGTH} characters).")
        return True
    
    target_name = target_name.strip().lower()
    message = message.strip()

    if not message:
        await character.send("What do you want to tell them?")
        return True
    
    if target_name == character.first_name.lower(): # Prevent telling self
        await character.send("You mutter softly to yourself.")
        return True
    
    target_char: Optional[Character] = None
    for char in world.get_active_characters_list():
        # Match first name case-insensitevly for now
        if char.first_name.lower() == target_name:
            target_char = char
            break
    
    if not target_char:
        await character.send(f"'{target_name.capitalize()}' doesn't appear to be online.")
        return True
    
    # Send messages add color codes later)
    target_msg = f"\r\n[[{character.name} tells you]: {message}]"
    self_msg = f"\r\n[[You tell {target_char.name}]: {message}]"

    try:
        await target_char.send(target_msg)
        await character.send(self_msg)
    except Exception as e:
        log.error("Error sending tell from %s to %s: %s", character.name, target_char.name, e)
        await character.send("Your message could not be delivered.")

    # Tells usually don't take roundtime
    return True

async def cmd_sit(character: 'Character', world: 'World', db_conn: aiosqlite.Connection, args_str: str) -> bool:
    """Makes the character sit down."""
    if character.status == "DYING" or character.status == "DEAD":
        await character.send("You cannot do that right now.")
        return True
    if character.is_fighting:
        await character.send("You cannot sit down while fighting!")
        return True
    if character.roundtime > 0:
        await character.send("You are too busy to sit down.")
        return True
    if character.casting_info:
        await character.send("You cannot sit while preparing an action.")
        return True
    if character.stance == "Sitting":
        await character.send("You are already sitting.")
        return True
    
    # Sitting takes a moment
    character.roundtime = 4.0
    character.stance = "Sitting"
    await character.send("You sit down.")
    if character.location:
        await character.location.broadcast(f"\r\n{character.name} sits down.\r\n", exclude={character})
    return True

async def cmd_stand(character: 'Character', world: 'World', db_conn: aiosqlite.Connection, args_str: str) -> bool:
    """Makes the character stand up."""
    if character.status == "DYING" or character.status == "DEAD":
        await character.send("You cannot do that right now.")
        return True
    # Can stand while fighting (might be necessary if knocked down later)
    # if character.is_fighting: await character.send(...); return True
    if character.roundtime > 0:
        await character.send("You are too busy to stand up.")
        return True
    if character.casting_info: # Interrupt casting? Yes.
        await character.send("You stop preparing your action and stand up.")
        character.casting_info = None
    if character.stance == "Standing":
        await character.send("You are already standing.")
        return True

    # Standing is quick
    character.roundtime = 2.0
    character.stance = "Standing"
    await character.send("You stand up.")
    if character.location:
        await character.location.broadcast(f"\r\n{character.name} stands up.\r\n", exclude={character})
    return True

async def cmd_lie(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Makes the character lie down."""
    if character.status == "DYING" or character.status == "DEAD":
        await character.send("You cannot do that right now.")
        return True
    if character.is_fighting:
        await character.send("You cannot lie down while fighting!")
        return True
    if character.roundtime > 0:
        await character.send("You are too busy to lie down.")
        return True
    if character.casting_info:
        await character.send("You cannot lie down while preparing an action.")
        return True
    if character.stance == "Lying":
        await character.send("You are already lying down.")
        return True
    
    # Lying down takes a bit longer
    character.roundtime = 5.0
    character.stance = "Lying"
    await character.send("You lie down.")
    if character.location:
        await character.location.broadcast(f"\r\n{character.name} lies down.\r\n", exclude={character})
    return True