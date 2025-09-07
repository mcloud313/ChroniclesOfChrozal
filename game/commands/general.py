# game/commands/general.py
"""
General player commands like look, say, quit, who, help, and score.
"""
import aiosqlite
import math
import logging
import config
from typing import TYPE_CHECKING
from .. import utils

if TYPE_CHECKING:
    from ..character import Character
    from ..world import World

log = logging.getLogger(__name__)


async def cmd_look(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Handles looking at the room, characters, mobs, or other objects."""
    if not character.location:
        await character.send("You are floating in an endless void... somehow.")
        return True

    target_name = args_str.strip().lower()

    # Case 1: Look at the room (no arguments)
    if not target_name or target_name == "here":
        room_desc = character.location.get_look_string(character, world)
        await character.send(room_desc)

        ground_items_output = []
        item_counts = {}
        for item_id in character.location.items:
            item_counts[item_id] = item_counts.get(item_id, 0) + 1

        for template_id, count in sorted(item_counts.items()):
            template = world.get_item_template(template_id)
            item_name = template['name'] if template else f"Item #{template_id}"
            display_name = item_name + (f" (x{count})" if count > 1 else "")
            ground_items_output.append(display_name)

        if character.location.coinage > 0:
            ground_items_output.append(utils.format_coinage(character.location.coinage))

        if ground_items_output:
            await character.send("You also see here: " + ", ".join(ground_items_output) + ".")
        return True

    # Case 2: Look at a specific target
    # Search order: Characters -> Mobs -> Room Objects -> Ground Items -> Inventory
    
    # Look at Character
    target_char = character.location.get_character_by_name(target_name)
    if target_char:
        pronoun_subj, _, _, verb_is, _ = utils.get_pronouns(target_char.sex)
        output = [
            f"\r\n{target_char.description}",
            f"({world.get_race_name(target_char.race_id)} {world.get_class_name(target_char.class_id)}, Level {target_char.level})",
            f"{pronoun_subj} {verb_is} wearing:"
        ]
        equipped_items_desc = []
        for slot in target_char.equipment:
            template_id = target_char.equipment.get(slot)
            if template_id:
                template = utils.get_item_template_from_world(world, template_id)
                item_name = template['name'] if template else f"Unknown Item ({template_id})"
                slot_display = slot.replace('_', ' ').title()
                equipped_items_desc.append(f" <{slot_display:<12}> {item_name}")
        
        output.extend(equipped_items_desc if equipped_items_desc else [" Nothing significant."])
        await character.send("\r\n".join(output))
        return True

    # Look at Mob
    target_mob = character.location.get_mob_by_name(target_name)
    if target_mob:
        await character.send(f"\r\n{target_mob.description}")
        return True

    # Look at Room Object
    target_obj_data = character.location.get_object_by_keyword(target_name)
    if target_obj_data:
        await character.send(f"\r\n{target_obj_data.get('description', 'It looks unremarkable.')}")
        return True

    # Look at Item on Ground
    for t_id in character.location.items:
        template = world.get_item_template(t_id)
        if template and target_name in template['name'].lower():
            item = character.get_item_instance(world, t_id)
            await character.send(f"\r\n{item.description}" if item else "You see it, but cannot make out details.")
            return True

    # Look at Item in Inventory
    item_id_in_inv = character.find_item_in_inventory_by_name(world, target_name)
    if item_id_in_inv:
        item = character.get_item_instance(world, item_id_in_inv)
        await character.send(f"\r\n{item.description}" if item else "You look at it, but cannot make out details.")
        return True

    await character.send(f"You don't see anything like '{target_name}' here.")
    return True


async def cmd_say(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Handles the 'say' command."""
    if not args_str:
        await character.send("Say what?")
        return True
    
    if not character.location:
        await character.send("You try to speak, but no sound comes out.")
        return True
    
    message = args_str.strip()
    await character.send(f"You say, \"{message}\"")
    await character.location.broadcast(f"\r\n{character.first_name} says, \"{message}\"", exclude={character})
    return True


async def cmd_quit(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Handles the 'quit' command."""
    await character.send("Farewell!")
    log.info("Character %s is quitting.", character.name)
    await character.save(db_conn)
    return False # Signal to the connection handler to close the connection


async def cmd_who(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Handles the 'who' command, listing online characters."""
    active_chars = sorted(world.get_active_characters_list(), key=lambda char: char.name)
    
    if not active_chars:
        await character.send("You appear to be all alone in the world...")
        return True
    
    header = f"--- Players Online ({len(active_chars)}) ---"
    output = [f"\r\n{{C{header}{{x"]
    
    for char in active_chars:
        race_name = world.get_race_name(char.race_id)
        class_name = world.get_class_name(char.class_id)
        title = "" # Placeholder for title
        output.append(f"[{char.level: >2}] {char.name:<25} {title:<15} ({race_name} {class_name})")

    output.append(f"{{C{'-' * len(header)}{{x")
    await character.send("\r\n".join(output))
    return True


async def cmd_help(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Handles the 'help' command."""
    output = ("\r\n--- Basic Commands ---\r\n"
            " look              - Look around the room.\r\n"
            " north, south, etc - Move in a direction.\r\n"
            " say <message>     - Speak to others in the room.\r\n"
            " who               - List players currently online.\r\n"
            " score             - Display your character sheet.\r\n"
            " inventory         - Display your inventory and equipment.\r\n"
            " get, drop <item>  - Interact with items.\r\n"
            " attack <target>   - Initiate combat.\r\n"
            " help              - Show this help message.\r\n"
            " quit              - Leave the game.\r\n"
            "----------------------")
    await character.send(output)
    return True


async def cmd_score(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Handles the 'score' or 'stats' command."""
    xp_needed = utils.xp_needed_for_level(character.level)
    
    attributes_display = []
    stat_order = ["might", "vitality", "agility", "intellect", "aura", "persona"]
    for stat_name in stat_order:
        value = character.stats.get(stat_name, 10)
        modifier = utils.calculate_modifier(value)
        mod_sign = "+" if modifier >= 0 else ""
        attributes_display.append(f" {stat_name.capitalize():<10}: {value:>2} [{mod_sign}{modifier}]")

    total_av = character.get_total_av(world)
    barrier_val = character.barrier_value
    armor_training_rank = character.get_skill_rank("armor training")
    av_multiplier = 0.20 + (armor_training_rank * 0.01)
    effective_av = math.floor(total_av * av_multiplier)
    
    output = (
        f"\r\n=================================================="
        f"\r\n Name : {character.name:<28} Sex: {character.sex}"
        f"\r\n Race : {world.get_race_name(character.race_id):<28} Class: {world.get_class_name(character.class_id)}"
        f"\r\n Level: {character.level:<31}"
        f"\r\n=================================================="
        f"\r\n HP   : {int(character.hp):>4}/{int(character.max_hp):<28} Carry: {character.get_current_weight(world):>2}/{character.get_max_weight():<3} stones"
        f"\r\n Armor: {effective_av:>4}/{total_av:<28} (Effective/Total)"
        f"\r\n Barrier: {barrier_val:<28} "
        f"\r\n Essn : {int(character.essence):>4}/{int(character.max_essence):<31}"
        f"\r\n XP   : {int(character.xp_total):>4}/{xp_needed:<28} Pool: {int(character.xp_pool)}"
        f"\r\n Tether: {character.spiritual_tether:<30}"
        f"\r\n --- Attributes ---"
        f"\r\n{attributes_display[0]} {attributes_display[1]}"
        f"\r\n{attributes_display[2]} {attributes_display[3]}"
        f"\r\n{attributes_display[4]} {attributes_display[5]}"
        f"\r\n Skill Pts: {character.unspent_skill_points:<25} Attrib Pts: {character.unspent_attribute_points}"
        f"\r\n Coins: {utils.format_coinage(character.coinage):<31}"
        f"\r\n=================================================="
    )
    await character.send(output)
    return True


async def cmd_advance(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Handles the 'advance' command for leveling up."""
    if not character.location or "NODE" not in character.location.flags:
        await character.send("You must be in a Node to consolidate your experience and advance.")
        return True
    if character.level >= config.MAX_LEVEL:
        await character.send(f"You have already reached the maximum level ({config.MAX_LEVEL}).")
        return True

    xp_needed = utils.xp_needed_for_level(character.level)
    if character.xp_total < xp_needed:
        await character.send(f"You require {int(xp_needed - character.xp_total)} more experience to advance.")
        return True

    character.level += 1
    sp_gain = config.SKILL_POINTS_PER_LEVEL
    character.unspent_skill_points += sp_gain
    
    ap_gain = 1 if character.level % 4 == 0 else 0
    character.unspent_attribute_points += ap_gain

    # BUG FIX: Use the returned values directly instead of recalculating.
    hp_gain, essence_gain = character.apply_level_up_gains()

    log.info("Character %s advanced to level %d! Gains: HP+%.1f, Ess+%.1f, SP+%d, AP+%d",
            character.name, character.level, hp_gain, essence_gain, sp_gain, ap_gain)

    level_msg = [
        "\r\n{G*** CONGRATULATIONS! ***{x",
        f"You have advanced to level {character.level}!",
        "=" * 30,
        f"Maximum HP increased by {int(hp_gain)} (Now: {int(character.max_hp)}).",
        f"Maximum Essence increased by {int(essence_gain)} (Now: {int(character.max_essence)}).",
        f"You gain {sp_gain} skill points (Total unspent: {character.unspent_skill_points})."
    ]
    if ap_gain > 0:
        level_msg.append(f"You gain {ap_gain} attribute point (Total unspent: {character.unspent_attribute_points}).")
    
    await character.send("\r\n".join(level_msg))
    await character.save(db_conn)
    return True


async def cmd_skills(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Displays the character's known skills and ranks."""
    output = [
        "\r\n================== Skills ==================",
        f" Unspent Skill Points: {character.unspent_skill_points}",
        "------------------------------------------"
    ]
    
    skill_lines = [f" {name.title():<25}: {rank}" for name, rank in sorted(character.skills.items()) if rank > 0]
    if not skill_lines:
        output.append(" You have not trained any skills yet.")
    else:
        output.extend(skill_lines)
        
    output.append("==========================================")
    await character.send("\r\n".join(output))
    return True


async def cmd_meditate(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Begins meditation to restore essence faster."""
    if character.status != "ALIVE":
        await character.send("You cannot meditate right now.")
    elif character.stance != "Sitting":
        await character.send("You must be sitting down to meditate properly.")
    elif character.is_fighting:
        await character.send("You cannot meditate while fighting!")
    elif character.roundtime > 0:
        await character.send("You must be still to meditate.")
    else:
        character.status = "MEDITATING"
        character.roundtime = 1.0
        await character.send("You sit down and begin to meditate, focusing your inner energy.")
        if character.location:
            # IMPROVEMENT: Add the missing broadcast message.
            await character.location.broadcast(f"\r\n{character.name} sits down and begins meditating.", exclude={character})
    return True


async def cmd_emote(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Performs an action visible to the room."""
    if not args_str:
        await character.send("Emote what?")
        return True
    
    action_text = args_str.strip()
    await character.send(f"You emote: {character.name} {action_text}")
    if character.location:
        await character.location.broadcast(f"\r\n{character.name} {action_text}\r\n", exclude={character})
    return True


async def cmd_tell(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Sends a private message to another player online."""
    try:
        target_name, message = args_str.split(" ", 1)
        message = message.strip()
        target_name = target_name.strip().lower()
    except ValueError:
        await character.send("Tell whom what?")
        return True

    if not message:
        await character.send("What do you want to tell them?")
        return True
    if target_name == character.first_name.lower():
        await character.send("You mutter softly to yourself.")
        return True
    
    target_char = next((c for c in world.get_active_characters_list() if c.first_name.lower() == target_name), None)
    
    if not target_char:
        await character.send(f"'{target_name.capitalize()}' doesn't appear to be online.")
        return True
    
    await target_char.send(f"\r\n[[{character.name} tells you]: {message}]")
    await character.send(f"\r\n[[You tell {target_char.name}]: {message}]")
    return True


async def cmd_sit(character: 'Character', world: 'World', db_conn: aiosqlite.Connection, args_str: str) -> bool:
    """Makes the character sit down."""
    if character.stance == "Sitting":
        await character.send("You are already sitting.")
    elif character.is_fighting or character.roundtime > 0:
        await character.send("You are too busy to sit down.")
    else:
        character.roundtime = 1.0
        character.stance = "Sitting"
        await character.send("You sit down.")
        if character.location:
            await character.location.broadcast(f"\r\n{character.name} sits down.\r\n", exclude={character})
    return True


async def cmd_stand(character: 'Character', world: 'World', db_conn: aiosqlite.Connection, args_str: str) -> bool:
    """Makes the character stand up."""
    if character.stance == "Standing":
        await character.send("You are already standing.")
    elif character.roundtime > 0:
        await character.send("You are too busy to stand up.")
    else:
        if character.status == "MEDITATING":
            character.status = "ALIVE"
            await character.send("You stop meditating and stand up.")
        else:
            await character.send("You stand up.")
        
        character.roundtime = 1.0
        character.stance = "Standing"
        if character.location:
            await character.location.broadcast(f"\r\n{character.name} stands up.\r\n", exclude={character})
    return True


async def cmd_lie(character: 'Character', world: 'World', db_conn: 'aiosqlite.Connection', args_str: str) -> bool:
    """Makes the character lie down."""
    if character.stance == "Lying":
        await character.send("You are already lying down.")
    elif character.is_fighting or character.roundtime > 0:
        await character.send("You are too busy to lie down.")
    else:
        character.roundtime = 1.5
        character.stance = "Lying"
        await character.send("You lie down.")
        if character.location:
            await character.location.broadcast(f"\r\n{character.name} lies down.\r\n", exclude={character})
    return True