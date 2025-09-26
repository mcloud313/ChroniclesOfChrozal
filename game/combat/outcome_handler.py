# game/combat/outcome_handler.py
"""
Handles the consequences of combat actions: applying damage, durability,
messaging, and processing defeat.
"""
import json
import random
import asyncio
import math
import logging
import time
from typing import Union, List, Tuple, Dict, Any, TYPE_CHECKING

from .damage_calculator import DamageInfo

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
    # --- NEW: Concentration Check ---
    if isinstance(target, Character) and target.casting_info:
        concentration_dc = 10 + (final_damage // 2)
        check_result = utils.skill_check(target, "concentration", dc=concentration_dc)
        if not check_result['success']:
            spell_name = target.casting_info.get("name", "their spell")
            target.casting_info = None # Interrupt the spell
            asyncio.create_task(target.send(f"{{RThe pain causes you to lose concentration on {spell_name}!{{x"))
    # ----------------------------
    
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
        character.is_dirty = True
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

async def send_attack_messages(attacker: Union[Character, Mob], target: Union[Character, Mob], 
                               hit_result: HitResult, damage_info: 'DamageInfo', final_damage: int):
    """Sends all relevant, detailed combat messages."""
    attacker_name = attacker.name.capitalize()
    target_name = target.name
    attack_name = damage_info.attack_name
    
    hit_desc = "{rCRITICALLY HITS{x" if hit_result.is_crit else "hits"
    
    # --- Build Verbose Details for Players ---
    hit_details = f"[Roll:{hit_result.roll} + MAR:{hit_result.attacker_rating} vs DV:{hit_result.target_dv}]"
    mitigation = damage_info.pre_mitigation_damage - final_damage

    # --- NEW: Show which defense was used (AV or BV) ---
    effective_av = target.total_av
    effective_bv = math.floor(target.barrier_value / 2)
    defense_name = "AV" if effective_av >= effective_bv else "BV"
    defense_value = max(effective_av, effective_bv)
    
    damage_details = (f"[Dmg:{damage_info.pre_mitigation_damage}(Base) "
                      f"- {mitigation}(PDS:{target.pds}, {defense_name}:{defense_value}) = {final_damage}]")

    # --- Message to Attacker (if player) ---
    if isinstance(attacker, Character):
        verb = "hit" if not hit_result.is_crit else "CRITICALLY HIT"
        clean_weapon_name = utils.strip_article(attack_name)
        msg = (f"Your {clean_weapon_name} {verb} {target_name}!\n\r"
               f"You deal {{y{final_damage}{{x damage. {hit_details} {damage_details}")
        await attacker.send(msg)

    # --- Message to Target (if player) ---
    if isinstance(target, Character):
        msg = (f"{{R{attacker_name}'s {attack_name} {hit_desc.lower()} you!{{x\n\r"
               f"{{RYou take {{y{final_damage}{{x damage. {hit_details} {damage_details} "
               f"({int(target.hp)}/{int(target.max_hp)} HP)")
        await target.send(msg)
    
    # --- Message to Room ---
    if attacker.location:
        room_hit_desc = "critically hits" if hit_result.is_crit else "hits"
        await attacker.location.broadcast(
            f"\r\n{attacker_name}'s {attack_name} {room_hit_desc} {target_name}.\r\n",
            exclude={attacker, target}
        )

async def send_magical_attack_messages(caster: Union[Character, Mob], target: Union[Character, Mob],
                                     hit_result: HitResult, damage_info: 'DamageInfo', final_damage: int, show_roll_details: bool = True):
    """Sends all relevant, detailed combat messages for a magical attack."""
    caster_name = caster.name.capitalize()
    target_name = target.name
    spell_name = damage_info.attack_name
    
    hit_desc = "{rCRITICALLY HITS{x" if hit_result.is_crit else "hits"
    
    # Initialize detail strings as empty.
    details_str = ""
    
    # Only build the verbose detail strings if requested.
    if show_roll_details:
        rating_name = "APR" if damage_info.damage_type in ["arcane", "fire", "cold"] else "DPR"
        hit_details = f"{{i[Roll:{hit_result.roll} + {rating_name}:{hit_result.attacker_rating} vs DV:{hit_result.target_dv}]{{x"
        mitigation = damage_info.pre_mitigation_damage - final_damage

        effective_bv = target.barrier_value
        effective_av = math.floor(target.total_av / 2)
        defense_name = "BV" if effective_bv >= effective_av else "AV"
        defense_value = max(effective_bv, effective_av)
        
        mit_details = f"{{i[Dmg:{damage_info.pre_mitigation_damage}(Base) - {mitigation}(SDS:{target.sds}, {defense_name}:{defense_value}) = {final_damage}]{{x"
        details_str = f" {hit_details} {mit_details}"

    # --- Message to Caster (if player) ---
    if isinstance(caster, Character):
        verb = "critically hit" if hit_result.is_crit else "hit"
        msg = (f"Your {spell_name} {verb} {target_name}!\n\r"
               f"You deal {{y{final_damage}{{x damage.{details_str}")
        await caster.send(msg)

    # --- Message to Target (if player) ---
    if isinstance(target, Character):
        msg = (f"{{R{caster_name}'s {spell_name} {hit_desc.lower()} you!{{x\n\r"
               f"{{RYou take {{y{final_damage}{{x damage.{details_str} "
               f"({int(target.hp)}/{int(target.max_hp)} HP)")
        await target.send(msg)
    
    # --- Message to Room ---
    if caster.location:
        room_hit_desc = "critically hits" if hit_result.is_crit else "hits"
        await caster.location.broadcast(
            f"\r\n{caster_name}'s {spell_name} {room_hit_desc} {target_name}.\r\n",
            exclude={caster, target}
        )

async def send_ranged_attack_messages(attacker, target, hit_result, damage_info, final_damage):
    """Sends tailored messages for a ranged attack outcome."""
    hit_desc = "{rCRITICALLY STRIKE{x" if hit_result.is_crit else "strike"
    attack_name = utils.strip_article(damage_info.attack_name)

    roll_details_attacker = (
        f"{{i[Roll: {hit_result.roll} + RAR: {hit_result.attacker_rating} vs DV: {hit_result.target_dv}]"
        f" -> Damage: {final_damage}{{x"
    )
    roll_details_target = f"({int(target.hp)}/{int(target.max_hp)} HP)"

    # Attacker message
    if isinstance(attacker, Character):
        msg = (f"Your {attack_name} {hit_desc.lower()}s {target.name} for {{y{final_damage}{{x damage! {roll_details_attacker}")
        await attacker.send(msg)

    # Target message
    if isinstance(target, Character):
        msg = (f"{{R{attacker.name.capitalize()}'s {attack_name} {hit_desc}s you for {{y{final_damage}{{x damage! {roll_details_target}")
        await target.send(msg)

    # Room message
    room_hit_desc = "critically strikes" if hit_result.is_crit else "strikes"
    if attacker.location:
        msg = f"\r\n{attacker.name.capitalize()}'s {attack_name} {room_hit_desc} {target.name}!\r\n"
        await attacker.location.broadcast(msg, exclude={attacker, target})

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

        dropped_coinage, dropped_item_ids = 0, []
        mob_template = world.get_mob_template(target.template_id)
        
        if mob_template:
            dropped_coinage, dropped_item_ids = _determine_loot(mob_template)
        else:
            dropped_coinage, dropped_item_ids = 0, []

        base_xp = 25
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

        # --- MODIFIED ITEM DROP LOGIC ---
        if dropped_item_ids and target_loc:
            dropped_item_names = []
            for template_id in dropped_item_ids:
                template = world.get_item_template(template_id)
                if not template:
                    continue

                # 1. Check the template for lock or trap details.
                initial_stats = {}
                if lock_details := template.get("lock_details"):
                    # Important: Ensure we get a dict, not a string
                    initial_stats.update(json.loads(lock_details) if isinstance(lock_details, str) else lock_details)
                if trap_details := template.get("trap_details"):
                    initial_stats.update(json.loads(trap_details) if isinstance(trap_details, str) else trap_details)

                # 2. Create the item instance, passing the initial stats if they exist.
                instance_data = await world.db_manager.create_item_instance(
                    template_id=template_id,
                    room_id=target_loc.dbid,
                    instance_stats=initial_stats if initial_stats else None
                )
                
                if instance_data:
                    item_obj = Item(instance_data, template)

                    # 3. Add the new item to the world's in-memory state (your existing method)
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