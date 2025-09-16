# game/combat/outcome_handler.py
"""
Handles the consequences of combat actions: applying damage, durability,
messaging, and processing defeat.
"""
import random
import math
import logging
import time
from typing import Union, List, Tuple, Dict, Any, TYPE_CHECKING

from ..character import Character
from ..mob import Mob
from ..item import Item
from .. import utils
from .hit_resolver import HitResult

if TYPE_CHECKING:
    from ..world import World

log = logging.getLogger(__name__)


def apply_damage(target: Union[Character, Mob], final_damage: int):
    """Applies the final calculated damage to the target's HP."""
    target.hp = max(0.0, target.hp - final_damage)

def _determine_loot(mob_template: Dict[str, Any]) -> Tuple[int, List[int]]:
    """Calculates loot from a normalized mob template."""
    dropped_coinage = 0
    dropped_item_ids = []

    # Get coinage directly from the template
    if max_coinage := mob_template.get("max_coinage", 0):
        dropped_coinage = random.randint(0, max_coinage)

    # Roll for each item in the loot table
    if item_list := mob_template.get("loot_table", []):
        for item_rule in item_list:
            if random.random() < item_rule.get('drop_chance', 0.0):
                # For now, we'll just drop one. We can add min/max quantity later.
                dropped_item_ids.append(item_rule['item_template_id'])
    
    return dropped_coinage, dropped_item_ids

async def _award_xp_to_character(character: Character, xp_amount: int):
    """Awards a specific amount of XP to a character's XP Pool."""
    if xp_amount <= 0: return
        
    intellect = character.stats.get("intellect", 10)
    xp_pool_cap = intellect * 100
    space_available = max(0, xp_pool_cap - character.xp_pool)
    actual_xp_added = min(xp_amount, space_available)

    if actual_xp_added > 0:
        character.xp_pool += actual_xp_added
        await character.send(f"You gain {int(actual_xp_added)} experience points into your pool.")
    elif not character.group:
        await character.send("Your mind cannot hold any more raw experience right now.")


async def handle_durability(attacker: Union[Character, Mob], target: Union[Character, Mob], attack_source: Item, world: 'World'):
    """Handles random durability loss for attacker's weapon and target's armor."""
    # Attacker weapon durability
    if isinstance(attacker, Character) and isinstance(attack_source, Item) and attack_source.item_type == "WEAPON":
        if random.random() < 0.10:  # 10% chance
            attack_source.condition -= 1
            await world.db_manager.update_item_condition(attack_source.id, attack_source.condition)

            if attack_source.condition <= 0:
                await attacker.send(f"{{RYour {attack_source.name} shatters into pieces!{{x")
                if attack_source.wear_location:
                    del attacker._equipped_items[attack_source.wear_location[0]]
                del world._all_item_instances[attack_source.id]
                await world.db_manager.delete_item_instance(attack_source.id)
            elif attack_source.condition <= 10:
                await attacker.send(f"{{yYour {attack_source.name} is badly damaged.{{x")

    # Target armor durability
    if isinstance(target, Character):
        armor_pieces = [item for item in target._equipped_items.values() if item.item_type == "ARMOR"]
        if armor_pieces and random.random() < 0.10:  # 10% chance
            armor_hit = random.choice(armor_pieces)
            armor_hit.condition -= 1
            await world.db_manager.update_item_condition(armor_hit.id, armor_hit.condition)

            if armor_hit.condition <= 0:
                await target.send(f"{{RYour {armor_hit.name} is destroyed by the blow!{{x")
                if armor_hit.wear_location:
                    del target._equipped_items[armor_hit.wear_location[0]]
                del world._all_item_instances[armor_hit.id]
                await world.db_manager.delete_item_instance(armor_hit.id)
            elif armor_hit.condition <= 10:
                await target.send(f"{{yYour {armor_hit.name} was damaged.{{x")

async def send_attack_messages(attacker: Union[Character, Mob], target: Union[Character, Mob], hit_result: HitResult, final_damage: int):
    """Sends all relevant combat messages to the attacker, target, and room."""
    attacker_name = attacker.name.capitalize()
    target_name = target.name.capitalize()

    hit_desc = "{rCRITICALLY HIT{x" if hit_result.is_crit else "hit"
    
    if isinstance(attacker, Character):
        await attacker.send(f"You {hit_desc} {target_name} for {{y{final_damage}{{x damage!")
    if isinstance(target, Character):
        await target.send(f"{{R{attacker_name} {hit_desc.upper()}S you for {{y{final_damage}{{x damage!{{x ({int(target.hp)}/{int(target.max_hp)} HP)")
    
    if attacker.location:
        await attacker.location.broadcast(f"\r\n{attacker_name} {hit_desc}s {target_name}!\r\n", exclude={attacker, target})

    if isinstance(target, Character) and target.status == "MEDITATING" and final_damage > 0:
        target.status = "ALIVE"
        await target.send("{RThe force of the blow shatters your concentration!{x")
        if attacker.location:
            await attacker.location.broadcast(f"\r\n{target_name} is snapped out of their meditative trance by the attack!\r\n", exclude={target})

async def handle_defeat(attacker: Union[Character, Mob], target: Union[Character, Mob], world: 'World'):
    """Handles logic for when a target's HP reaches 0, with group reward sharing."""
    attacker_name = getattr(attacker, 'name', 'Something').capitalize()
    target_name = getattr(target, 'name', 'Something').capitalize()
    target_loc = getattr(target, 'location', None)

    log.info("%s has defeated %s!", attacker_name, target_name)

    # --- Mob Defeat Logic ---
    if isinstance(target, Mob):
        if isinstance(attacker, Character):
            await attacker.send(f"You have slain {target_name}!")
        if target_loc:
            await target_loc.broadcast(f"\r\n{attacker_name} has slain {target_name}!\r\n", exclude={attacker})
        
        target.die()
        
        dropped_coinage, dropped_item_ids = _determine_loot(target.loot_table)
        base_xp = 50
        xp_gain = max(1, target.level * base_xp + random.randint(-base_xp // 2, base_xp // 2))
        killer = attacker if isinstance(attacker, Character) else None

        # Check if this was a group kill with other members present
        is_group_kill = False
        if killer and killer.group:
            present_members = [m for m in killer.group.members if m.location == killer.location and m.is_alive()]
            if len(present_members) > 1:
                is_group_kill = True

        # --- Group Kill Logic ---
        if is_group_kill:
            group_xp_total = int(xp_gain * 0.80) # 80% XP penalty/bonus for groups
            xp_per_member = group_xp_total // len(present_members)
            
            coins_per_member = dropped_coinage // len(present_members)
            remainder_coins = dropped_coinage % len(present_members)
            
            await killer.group.broadcast(f"{{yYour group receives {group_xp_total} XP and {utils.format_coinage(dropped_coinage)}!{{x")
            
            for member in present_members:
                await _award_xp_to_character(member, xp_per_member)
                member.coinage += coins_per_member
            
            killer.group.leader.coinage += remainder_coins

        # --- Solo Kill Logic ---
        elif killer:
            await _award_xp_to_character(killer, xp_gain)
            if dropped_coinage > 0 and target_loc:
                await target_loc.add_coinage(dropped_coinage, world)
                await target_loc.broadcast(f"\r\n{utils.format_coinage(dropped_coinage)} falls from {target_name}!\r\n")

        # --- Item Drop Logic (Shared by Solo and Group) ---
        if dropped_item_ids and target_loc:
            dropped_item_names = []
            for template_id in dropped_item_ids:
                # Create a new unique instance of the item in the room
                instance_data = await world.db_manager.create_item_instance(template_id, room_id=target_loc.dbid)
                if instance_data:
                    template = world.get_item_template(template_id)
                    item_obj = Item(instance_data, template)

                    # Add the new item to the world's in memory state
                    world._all_item_instances[item_obj.id] = item_obj
                    target_loc.item_instance_ids.append(item_obj.id)
                    dropped_item_names.append(template['name'])
            if dropped_item_names:
                await target_loc.broadcast(f"\r\n{target_name}'s corpse drops: {', '.join(dropped_item_names)}.\r\n")

    # --- Character Defeat Logic ---
    elif isinstance(target, Character) and target.status == "ALIVE":
        target.hp, target.status, target.stance = 0, "DYING", "Lying"
        target.is_fighting, target.target, target.casting_info = False, None, None

        target.xp_pool = 0.0
        xp_at_start_of_level = utils.xp_needed_for_level(target.level - 1) if target.level > 1 else 0
        xp_progress = target.xp_total - xp_at_start_of_level
        xp_penalty = math.floor(xp_progress * 0.10)
        target.xp_total = max(xp_at_start_of_level, target.xp_total - xp_penalty)
        
        await target.send("{rYou feel some of your experience drain away...{x")

        timer_duration = float(target.stats.get('vitality', 10))
        target.death_timer_ends_at = time.monotonic() + timer_duration
        
        coinage_to_drop = int(target.coinage * 0.10)
        if coinage_to_drop > 0 and target_loc:
            target.coinage -= coinage_to_drop
            await target_loc.add_coinage(coinage_to_drop, world)
            await target_loc.broadcast(f"\r\nSome coins fall from {target.name} as they collapse!\r\n", exclude={target})

            world.mark_room_dirty(target_loc)

        await target.send("\r\n{r*** YOU ARE DYING! ***{x")
        if target_loc:
            await target_loc.broadcast(f"\r\n{target_name} collapses to the ground, dying!\r\n", exclude={target})