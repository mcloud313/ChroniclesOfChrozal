# game/commands/rogue.py
import logging
import random
from typing import TYPE_CHECKING
from .. import utils
from .. character import Character

if TYPE_CHECKING:
    from ..character import Character
    from ..world import World

log = logging.getLogger(__name__)

async def cmd_hide(character: 'Character', world: 'World', args_str: str) -> bool:
    """Attempts to hide from observers in the current room."""
    if character.is_fighting:
        await character.send("You can't hide while in combat!")
        return True
    if character.is_hidden:
        await character.send("You are already hidden.")
        return True

    # Your stealth is checked against every observer's perception
    stealth_mod = character.get_skill_modifier("stealth")
    observers = [c for c in character.location.characters if c != character] + \
                [m for m in character.location.mobs if m.is_alive()]

    spotted = False
    for observer in observers:
        # For mobs, we'll estimate their perception skill
        perception_mod = observer.get_skill_modifier("perception") if isinstance(observer, Character) \
            else observer.level * 3 # Mobs get a base perception

        # The observer's perception check is the DC for your stealth check
        if utils.skill_check(character, "stealth", dc=perception_mod)['success']:
            continue # You successfully hid from this observer
        else:
            spotted = True
            await character.send(f"You fail to hide from {observer.name}.")
            # Optional: await observer.send(f"You notice {character.name} trying to hide.")
            break # One spot is all it takes

    if not spotted:
        character.is_hidden = True
        await character.send("You slip into the shadows.")

    return True

async def cmd_lockpick(character: 'Character', world: 'World', args_str: str) -> bool:
    """Attempts to pick the lock on a door or container."""
    if not args_str:
        await character.send("What do you want to lockpick?")
        return True
    
    target_name = args_str.lower()
    
    #  --- Try to find a locked door (exit) ---
    for exit_name, exit_data in character.location.exits.items():
        if target_name in exit_name.lower() and isinstance(exit_data, dict):
            if not exit_data.get('is_locked'):
                await character.send("That is already unlocked.")
                return True
            
            dc = exit_data.get('lockpick_dc')
            if dc is None:
                await character.send("That lock cannot be picked.")
                return True
            
            # Perform the skill check
            check_result = utils.skill_check(character, "lockpicking", dc)
            if check_result['success']:
                exit_data['is_locked'] = False # unlock in memory
                await world.db_manager.update_room_exits(character.location.dbid, character.location.exits) # Save to DB
                await character.send(f"{{gSuccess! You pick the lock on the {exit_name}.{{x")
            else:
                await character.send(f"{{rYou fail to pick the lock on the {exit_name}.{{x")
            character.roundtime = 10.0 # Lockpicking takes time
            return True
    
    # --- If not a door, try to find a locked item (chest) ---
    target_item = character.location.get_item_instance_by_name(target_name, world)
    if target_item and target_item.instance_stats.get('is_locked'):
        dc = target_item.instance_stats.get('lockpick_dc')
        if dc is None:
            await character.send("That lock cannot be picked.")
            return True
        
        # Perform the skill check
        check_result = utils.skill_check(character, "lockpicking", dc)
        if check_result['success']:
            target_item.instance_stats['is_locked'] = False
            await world.db_manager.update_item_instance_stats(target_item.id, target_item.instance_stats) # Save to DB
            await character.send(f"{{gSuccess! You pick the lock on the {target_item.name}.{{x")
        else:
            await character.send(f"{{rYou fail to pick the lock on the {target_item.name}.{{x")
        character.roundtime = 3.0
        return True

    await character.send("You don't see that here to lockpick.")
    return True

async def cmd_disarm(character: 'Character', world: 'World', args_str: str) -> bool:
    """Attempts to disarm a detected trap on a door or container."""
    if not args_str:
        await character.send("What do you want to disarm?")
        return True

    target_name = args_str.lower()

    # Find the target (door or item) and its corresponding trap_id
    target_obj, trap_id, trap_data = None, None, None
    for exit_name, exit_data in character.location.exits.items():
        if target_name in exit_name.lower() and isinstance(exit_data, dict):
            if 'trap' in exit_data:
                target_obj, trap_id, trap_data = exit_data, f"exit_{exit_name}", exit_data['trap']
                break
    
    if not target_obj:
        item = character.location.get_item_instance_by_name(target_name, world)
        if item and 'trap' in item.instance_stats:
            target_obj, trap_id, trap_data = item, f"item_{item.id}", item.instance_stats['trap']

    # --- Validation ---
    if not target_obj or not trap_data or not trap_data.get('is_active'):
        await character.send("You don't see a trap there.")
        return True
    if trap_id not in character.detected_traps:
        await character.send("You must find a trap before you can disarm it.")
        return True

    # --- Skill Check ---
    dc = trap_data.get('disarm_dc', 20)
    check_result = utils.skill_check(character, "disable device", dc)
    character.roundtime = 4.0 # Disarming is tricky

    if check_result['success']:
        trap_data['is_active'] = False
        # Persist the change
        if isinstance(target_obj, dict): # It's an exit
            await world.db_manager.update_room_exits(character.location.dbid, character.location.exits)
        else: # It's an item
            await world.db_manager.update_item_instance_stats(target_obj.id, target_obj.instance_stats)
        await character.send(f"{{gSuccess! You disarm the trap.{{x")
    else:
        await character.send(f"{{rYou fail to disarm the trap...{{x")
        # 25% chance to trigger the trap on failure!
        if random.random() < 0.25:
            await character.send(f"{{R...and you've triggered it!{{x")
            # Here we would resolve the trap's effect, for now, we'll just log it.
            log.info(f"Trap {trap_id} triggered on failed disarm by {character.name}.")
            trap_data['is_active'] = False # Trap is used up

    return True