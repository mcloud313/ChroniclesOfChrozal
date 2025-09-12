# game/commands/general.py
"""
General player commands like look, say, quit, who, help, and score.
"""
import math
import logging
import config
from typing import TYPE_CHECKING
from .. import utils
from ..definitions import slots

if TYPE_CHECKING:
    from ..character import Character
    from ..world import World

log = logging.getLogger(__name__)

async def cmd_look(character: 'Character', world: 'World', args_str: str) -> bool:
    """Handles looking at the room, characters, mobs, or other objects."""
    if not character.location:
        await character.send("You are floating in an endless void... somehow.")
        return True
    
    # --- NEW: Handle "look in <container>" ---
    if args_str.lower().startswith("in "):
        container_name = args_str[3:].strip()
        
        # Search for the container in the character's inventory/equipment first
        container = character.find_container_by_name(container_name)
        
        # If not found, search for a container in the room
        if not container:
            container = character.location.get_item_instance_by_name(container_name, world)
            if container and container.capacity <= 0: # Make sure it's actually a container
                container = None

        if not container:
            await character.send(f"You don't see a '{container_name}' here to look inside.")
            return True
        
        if not container.is_open:
            await character.send(f"The {container.name} is closed.")
            return True
        
        # Display the contents
        if not container.contents:
            await character.send(f"The {container.name} is empty.")
        else:
            contents_list = ", ".join(item.name for item in container.contents.values())
            await character.send(f"The {container.name} contains: {contents_list}.")
        return True

    # --- Original look logic, with one addition for container state ---
    target_name = args_str.strip().lower()

    # Case 1: Look at the room (no arguments)
    if not target_name or target_name == "here":
        room_desc = character.location.get_look_string(character, world)
        await character.send(room_desc)

        ground_items_output = []
        item_counts = {}
        for item_id in character.location.item_instance_ids:
            item_obj = world.get_item_object(item_id)
            if item_obj:
                item_counts[item_obj.name] = item_counts.get(item_obj.name, 0) + 1
        
        for name, count in sorted(item_counts.items()):
            display_name = name + (f" (x{count})" if count > 1 else "")
            ground_items_output.append(display_name)

        if character.location.coinage > 0:
            ground_items_output.append(utils.format_coinage(character.location.coinage))

        if ground_items_output:
            await character.send("You also see here: " + ", ".join(ground_items_output) + ".")
        return True
    
    # Case 2: Look at a specific target
    target_char = character.location.get_character_by_name(target_name)
    if target_char:
        output = []
        description = target_char.description.strip()
        if not description:
            description = f"{target_char.name} looks rather ordinary."
        output.append(description)
        output.append(utils.get_health_desc(target_char))
        output.append(f"\n\r{target_char.first_name} is using:")
        equipped_items_desc = []
        for slot in slots.ALL_SLOTS:
            item = target_char._equipped_items.get(slot)
            if item:
                slot_display = slot.replace('_', ' ').title()
                equipped_items_desc.append(f" <{slot_display:<12}> {item.name}")
        
        if equipped_items_desc:
            output.extend(equipped_items_desc)
        else:
            output.append(" Nothing.")

        await character.send("\n\r".join(output))
        return True
    
    target_mob = character.location.get_mob_by_name(target_name)
    if target_mob:
        await character.send(f"\n\r{target_mob.description}")
        return True
    
    target_obj_data = character.location.get_object_by_keyword(target_name)
    if target_obj_data:
        await character.send(f"\n\r{target_obj_data.get('description', 'It looks unremarkable.')}")
        return True
    
    item_to_examine = (character.location.get_item_instance_by_name(target_name, world) or
                       character.find_item_in_inventory_by_name(target_name))
    
    if item_to_examine:
        uuid_str = f"{{i({item_to_examine.id}){{x"
        examine_output = [
            f"\n\r--- {item_to_examine.name} {uuid_str} ---",
            item_to_examine.description,
            utils.get_condition_desc(item_to_examine.condition),
            f"Type: {item_to_examine.item_type.capitalize()}, Weight: {item_to_examine.weight} stones"
        ]
        
        # --- NEW: Add open/closed state to description ---
        if item_to_examine.capacity > 0:
            examine_output.append("It is open." if item_to_examine.is_open else "It is closed.")

        await character.send("\n\r".join(examine_output))
        return True

    await character.send(f"You don't see anything like '{target_name}' here.")
    return True

async def cmd_say(character: 'Character', world: 'World', args_str: str) -> bool:
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

async def cmd_quit(character: 'Character', world: 'World', args_str: str) -> bool:
    """Handles the 'quit' command."""
    await character.send("Farewell!")
    log.info("Character %s is quitting.", character.name)
    # REFACTOR: Call the character's own save method.
    await character.save()
    return False

async def cmd_who(character: 'Character', world: 'World', args_str: str) -> bool:
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
        title = ""
        output.append(f"[{char.level: >2}] {char.name:<25} {title:<15} ({race_name} {class_name})")

    output.append(f"{{C{'-' * len(header)}{{x")
    await character.send("\r\n".join(output))
    return True

async def cmd_help(character: 'Character', world: 'World', args_str: str) -> bool:
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

async def cmd_score(character: 'Character', world: 'World', args_str: str) -> bool:
    """Handles the 'score' or 'stats' command."""
    xp_needed = utils.xp_needed_for_level(character.level)
    
    attributes_display = []
    stat_order = ["might", "vitality", "agility", "intellect", "aura", "persona"]
    for stat_name in stat_order:
        value = character.stats.get(stat_name, 10)
        modifier = utils.calculate_modifier(value)
        attributes_display.append(f" {stat_name.capitalize():<10}: {value:>2} [{modifier:+}]")

    total_av = character.get_total_av(world)
    armor_training_rank = character.get_skill_rank("armor training")
    effective_av = math.floor(total_av * (0.20 + (armor_training_rank * 0.01)))
    
    output = (
        f"\r\n=================================================="
        f"\r\n Name : {character.name:<28} Sex: {character.sex}"
        f"\r\n Race : {world.get_race_name(character.race_id):<28} Class: {world.get_class_name(character.class_id)}"
        f"\r\n Level: {character.level:<31}"
        f"\r\n=================================================="
        f"\r\n HP   : {int(character.hp):>4}/{int(character.max_hp):<28} Carry: {character.get_current_weight(world):>2}/{character.get_max_weight():<3} stones"
        f"\r\n Armor: {effective_av:>4}/{total_av:<28} (Effective/Total)"
        f"\r\n Barrier: {character.barrier_value:<28} "
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

async def cmd_advance(character: 'Character', world: 'World', args_str: str) -> bool:
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
    # REFACTOR: Call the character's own save method.
    await character.save()
    return True

async def cmd_skills(character: 'Character', world: 'World', args_str: str) -> bool:
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

async def cmd_meditate(character: 'Character', world: 'World', args_str: str) -> bool:
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
            await character.location.broadcast(f"\r\n{character.name} sits down and begins meditating.", exclude={character})
    return True

async def cmd_emote(character: 'Character', world: 'World', args_str: str) -> bool:
    """Performs an action visible to the room."""
    if not args_str:
        await character.send("Emote what?")
        return True
    
    action_text = args_str.strip()
    await character.send(f"You emote: {character.name} {action_text}")
    if character.location:
        await character.location.broadcast(f"\r\n{character.name} {action_text}\r\n", exclude={character})
    return True

async def cmd_tell(character: 'Character', world: 'World', args_str: str) -> bool:
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

async def cmd_sit(character: 'Character', world: 'World', args_str: str) -> bool:
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

async def cmd_stand(character: 'Character', world: 'World', args_str: str) -> bool:
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

async def cmd_lie(character: 'Character', world: 'World', args_str: str) -> bool:
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

async def cmd_search(character: 'Character', world: 'World', args_str: str) -> bool:
    """Actively searches the room for hidden things like traps."""
    if character.roundtime > 0:
        await character.send("You are too busy to search right now.")
        return True
    
    await character.send("You begin searching the area...")
    character.roundtime = 10.0
    found_anything = False
    
    # Search exits for traps
    for exit_name, exit_data in character.location.exits.items():
        if isinstance(exit_data, dict) and (trap := exit_data.get('trap')):
            if trap.get('is_active'):
                trap_id = f"exit_{exit_name}"
                if trap_id not in character.detected_traps:
                    if utils.skill_check(character, 'perception', dc=trap.get('perception_dc', 15))['success']:
                        await character.send(f"{{yYou found a trap on the {exit_name}!{{x")
                        character.detected_traps.add(trap_id)
                        found_anything = True
    # Search items (chests, etc.) in the room for traps
    for item_obj in [world.get_item_object(iid) for iid in character.location.item_instance_ids]:
        if item_obj and (trap := item_obj.instance_stats.get('trap')):
            if trap.get('is_active'):
                trap_id = f"item_{item_obj.id}"
                if trap_id not in character.detected_traps:
                    if utils.skill_check(character, 'perception', dc=trap.get('perception_dc', 15))['success']:
                        await character.send(f"{{yYou found a trap on the {item_obj.name}!{{x")
                        character.detected_traps.add(trap_id)
                        found_anything = True
    if not found_anything:
        await character.send("You don't find anything unusual.")
        
    return True

# Add this function to game/commands/general.py
async def cmd_release(character: 'Character', world: 'World', args_str: str) -> bool:
    """Releases a dead character's spirit to their tether point."""
    if character.status != "DEAD":
        await character.send("You are not dead.")
        return True

    await character.send("{RYou release your spirit from your corpse...{x")
    
    # Apply tether loss
    initial_tether = character.spiritual_tether
    character.spiritual_tether = max(0, initial_tether - 1)
    log.info("Character %s tether decreased from %d to %d.", character.name, initial_tether, character.spiritual_tether)
    await character.send("{RYour connection to the living world weakens...{x")
    
    if character.spiritual_tether <= 0:
        log.critical("!!! PERMANENT DEATH: Character %s (ID: %s) has reached 0 spiritual tether!", character.name, character.dbid)
        await character.send("{R*** Your soul feels irrevocably severed! ***{x")

    # Call the existing respawn logic
    await world.respawn_character(character)
    return True
    
                        