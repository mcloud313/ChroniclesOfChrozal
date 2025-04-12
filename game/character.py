# game/character.py
"""
Represents a character in the game world, controlled by a player account.
Holds in-game state, attributes, and connection information.
"""
import math
import time
import random
import asyncio
import json
import logging
import aiosqlite
from typing import TYPE_CHECKING, Optional, Dict, Any, List, Tuple, Union
from . import database
from . import utils
from .item import Item
from .definitions import skills as skill_defs


# Use TYPE_CHECKING block for Room to avoid circular import errors
# This makes the type checker happy but doesn't cause runtime import issues.
if TYPE_CHECKING:
    from .room import Room
    from .world import World

log = logging.getLogger(__name__)

    # Define Hit Dice size per class ID {class_id: die_size}
CLASS_HP_DIE = {
    1: 10,  # Warrior: d10
    2: 4,   # Mage: d4
    3: 8,   # Cleric: d8
    4: 6,   # Rogue: d6
}
DEFAULT_HP_DIE = 6 # Default if class not found

CLASS_ESSENCE_DIE = {
    1: 4,   # Warrior: d4
    2: 10,  # Mage: d10
    3: 8,   # Cleric: d8 (Assuming standard progression)
    4: 6,   # Rogue: d6 (Assuming standard progression)
}
DEFAULT_ESSENCE_DIE = 4 # Default if class not found


class Character:
    """
    Represents an individual character within the game world.
    """
    # hint network connection type
    writer: asyncio.StreamWriter

    @property
    def might_mod(self) -> int: return utils.calculate_modifier(self.stats.get("might", 10))

    @property
    def vit_mod(self) -> int: return utils.calculate_modifier(self.stats.get("vitality", 10))

    @property
    def agi_mod(self) -> int: return utils.calculate_modifier(self.stats.get("agility", 10))

    @property
    def int_mod(self) -> int: return utils.calculate_modifier(self.stats.get("intelligence", 10))

    @property
    def aura_mod(self) -> int: return utils.calculate_modifier(self.stats.get("aura", 10))

    @property
    def pers_mod(self) -> int: return utils.calculate_modifier(self.stats.get("persona", 10))

    # Derived Combat Stats
    @property
    def mar(self) -> int: # Melee Attack Rating
        # Might Modifier + 1/2 of Agility Modifier (floor division)
        return self.might_mod + (self.agi_mod // 2)
    @property
    def rar(self) -> int: # Ranged Attack Rating
        # Agility Modifier + 1/2 of Might Modifier
        return self.agi_mod + (self.might_mod // 2)
    @property
    def apr(self) -> int: # Arcane Power Rating
        # Intellect Modifier + 1/2 Aura Modifier
        return self.int_mod + (self.aura_mod // 2)
    @property
    def dpr(self) -> int: # Divine Power Rating
        # Aura Modifier + 1/2 Persona Modifier
        return self.aura_mod + (self.pers_mod // 2)
    @property
    def pds(self) -> int: # Physical Defense Score
        # Vitality Modifier * 2
        return self.vit_mod
    @property
    def sds(self) -> int: # Spiritual Defense Score
        # Aura Modifier * 2
        return self.aura_mod
    @property
    def dv(self) -> int: # Dodge Value
        # Agility Modifier * 2
        return self.agi_mod * 2

    def __init__(self, writer: asyncio.StreamWriter, db_data: Dict[str, Any], player_is_admin: bool = False):
        """
        Initializes a Character object from database data and network writer.

        Args:
            writer: the asyncio streamwriter associated with the player's connection.
            db_data: a dictionary-like object (e.g., aiosqlite.Row) containing character
            data from the 'characters' table.
        """
        self.writer: asyncio.StreamWriter = writer # Network connection

        # --- Data loaded from DB ---
        self.writer: asyncio.StreamWriter = writer
        self.is_admin: bool = player_is_admin
        self.dbid: int = db_data['id']
        self.player_id: int = db_data['player_id'] # Link to Player account
        self.first_name: str = db_data['first_name']
        self.last_name: str = db_data['last_name']
        self.sex: str = db_data['sex']
        self.race_id: Optional[int] = db_data['race_id'] # Store ID
        self.class_id: Optional[int] = db_data['class_id'] # Store ID
        self.level: int = db_data['level']
        self.hp: int = db_data['hp']
        self.max_hp: int = db_data['max_hp']
        self.essence: int = db_data['essence']
        self.max_essence: int = db_data['max_essence']
        self.xp_pool: int = db_data['xp_pool'] # Unabsorbed XP
        self.xp_total: int = db_data['xp_total'] # Current level progress
        self.unspent_skill_points: int = db_data['unspent_skill_points']
        self.unspent_attribute_points: int = db_data['unspent_attribute_points']
        self.spiritual_tether: int = db_data.get('spiritual_tether', 1) # Load, default 1
        self.status: str = "ALIVE" # Start alive when loaded/created
        self.death_timer_ends_at: Optional[float] = None # Timer not active initially
        self.description: str = db_data['description']
        self.status: str = 'ALIVE' # Possible values: ALIVE, DYING, DEAD
        self.target: Optional[Union['Character', 'Mob']] = None # Who are we fighting? Needs Mob import below
        self.is_fighting: bool = False # Add fighting flag

        # Load stats (JSON string -> dict)
        try:
            self.stats: Dict[str, int] = json.loads(db_data['stats'] or '{}')
        except json.JSONDecodeError:
            log.warning("Character %s (%s): Could not decode stats JSON: %s",
                        self.dbid, self.first_name, db_data['stats'])
            self.stats: Dict[str, int] = {} # Default to empty if invalid

        # Load skills (JSON string -> dict)
        try:
            self.skills: Dict[str, int] = json.loads(db_data['skills'] or '{}')
        except json.JSONDecodeError:
            log.warning("Character %s (%s): Could not decode skills JSON: %s",
                        self.dbid, self.first_name, db_data['skills'])
            self.skills: Dict[str, int] = {} # Default to empty if invalid

        self.location_id: int = db_data['location_id'] # Store DB location ID
        self.location: Optional['Room'] = None

        self.coinage: int = db_data['coinage'] # Load coinage

        # Load inventory (List of template IDs)
        try:
            inv_str = db_data['inventory'] or '[]'
            self.inventory: List[int] = json.loads(inv_str)
            if not isinstance(self.inventory, list): #Ensure it's a list
                log.warning("Character %s inventory loaded non-list, resetting: %r", self.dbid, inv_str)
                self.inventory = []
        except (json.JSONDecodeError, TypeError):
            log.warning("Character %s: Could not decode inventory JSON: %r", self.dbid, db_data.get('inventory','[]'))
            self.inventory: List[int] = []

        # Load equipment (dict mapping slot name to template ID)
        try:
            eq_str = db_data['equipment'] or '{}'
            self.equipment: Dict[str, int] = json.loads(eq_str)
            if not isinstance(self.equipment, dict): # Ensure its a dict
                log.warning("Character %s equipment loaded non-dict, resetting: %r", self.dbid, eq_str)
                self.equipment = {}
        except (json.JSONDecodeError, TypeError):
            log.warning("Character %s: Could not decode equipment JSON: %r", self.dbid, db_data.get('equipment','{}'))
            self.equipment: Dict[str, int] = {}

        # Roundtime attribute
        self.roundtime: float = 0.0 # Time until next action possible

        # Add basic derived name property
        self.name = f"{self.first_name} {self.last_name}"
        self.calculate_initial_derived_attributes()
        log.debug("Character object initialized for %s (ID: %s)", self.name, self.dbid)

    def get_max_weight(self) -> int:
        """Calculates maximum carrying weight based on Might."""
        might = self.stats.get("might", 10) # Default 10 might if missing
        return might * 3

    def get_current_weight(self, world: 'World') -> int:
        """Calculates current weight carried from inventory and equipment."""
        current_weight = 0
        # Weight from inventory (loose items)
        for item_template_id in self.inventory:
            template = world.get_item_template(item_template_id)
            if template:
                try:
                    # Need to parse stats JSON from the template Row
                    stats_dict = json.loads(template['stats'] or '{}')
                    current_weight += stats_dict.get("weight", 1) # Add item weight
                except (json.JSONDecodeError, TypeError):
                    log.warning("Could not parse stats for inventory item template %d for weight calc.", item_template_id)
                    current_weight += 1 # Assume default weight 1 on error
            else:
                log.warning("Could not find item template %d in inventory for weight calc.", item_template_id)
                # Decide: count as 0 weight, default 1, or raise error? Default 1 seems safest.
                current_weight += 1

        # Weight from equipment
        for item_template_id in self.equipment.values():
            template = world.get_item_template(item_template_id)
            if template:
                try:
                    stats_dict = json.loads(template['stats'] or '{}')
                    current_weight += stats_dict.get("weight", 1)
                except (json.JSONDecodeError, TypeError):
                    log.warning("Could not parse stats for equipment item template %d for weight calc.", item_template_id)
                    current_weight += 1
            else:
                log.warning("Could not find item template %d in equipment for weight calc.", item_template_id)
                current_weight += 1

        # TODO: Add weight of coinage later if desired? Typically negligible.
        return current_weight

    def find_item_in_inventory_by_name(self, world: 'World', item_name: str) -> Optional[int]:
        """Finds the first template ID in inventory matching some (case-insensitive)"""
        name_lower = item_name.lower()
        for template_id in self.inventory:
            template = world.get_item_template(template_id)
            if template and name_lower in template['name'].lower():
                return template_id

    def find_item_in_equipment_by_name(self, world: 'World', item_name: str) -> Optional[Tuple[str, int]]:
        """Finds the first equipped template ID matching name (case-insensitive)."""
        name_lower = item_name.lower()
        for slot, template_id in self.equipment.items():
            template = world.get_item_template(template_id)
            if template and name_lower in template['name'].lower():
                return slot, template_id # Return slot name and template ID
        return None

    def find_item_anywhere_by_name(self, world: 'World', item_name: str) -> Optional[Tuple[str, int]]:
        """Finds item by name in equipment then inventory. Returns (location, template_id)."""
        # Check equipment first
        equipped = self.find_item_in_equipment_by_name(world, item_name)
        if equipped:
            return equipped[0], equipped[1] # Return slot, template_id

        # Check inventory next
        inv_tid = self.find_item_in_inventory_by_name(world, item_name)
        if inv_tid:
            return "inventory", inv_tid # Return "inventory", template_id

        return None

    def get_item_instance(self, world: 'World', template_id: int) -> Optional[Item]:
        """Instantiates an Item object from a template ID."""
        template_data = world.get_item_template(template_id)
        if template_data:
            try:
                return Item(template_data)
            except Exception:
                log.exception("Failed to instantiate Item from template %d", template_id)
        return None

    async def send(self, message: str):
        """
        Sends a message string to the character's connected client.
        Appends a newline characters if not present.

        Args:
            message: the string message to send.
        """
        if not self.writer or self.writer.is_closing():
            log.warning("Attempted to send to closed writer for character %s", self.name)
            return

        # Ensure message ends with standard MUD newline (\r\n) for telnet clients
        if not message.endswith('\r\n'):
            if message.endswith('\n'):
                message = message[:-1] + '\r\n'
            elif message.endswith('\r'):
                message = message[:-1] + '\r\n'
            else:
                message += '\r\n'

        try:
            # Encode message to bytes (UTF-8 is standard)
            self.writer.write(message.encode('utf-8'))
            await self.writer.drain() # Wait until buffer has flushed
            log.debug("Sent to %s: %r", self.name, message)
        except (ConnectionResetError, BrokenPipeError) as e:
            log.warning("Network error sending to character %s: %s. Writer closed.", self.name, e)
            # Connection is likely dead, try to close gracefully
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass # Ignore errors during close
        except Exception as e:
            log.exception("Unexpected error sending to character %s", self.name, exc_info=True)

    async def save(self, db_conn: aiosqlite.Connection):
        """Gathers essential character data and saves it to the database."""
        # Define V1 data to save
        data_to_save = {
            "location_id": self.location_id,
            "hp": self.hp,
            "essence": self.essence,
            "xp_pool": self.xp_pool,
            "xp_total": self.xp_total,
            "level": self.level,
            "unspent_skill_points": self.unspent_skill_points,
            "unspent_attribute_points": self.unspent_attribute_points,
            "spiritual_tehter": self.spiritual_tether,
            "stats": json.dumps(self.stats), # Save current stats
            "skills": json.dumps(self.skills), # Save current skills
            "inventory": json.dumps(self.inventory), # Save list of template IDs
            "equipment": json.dumps(self.equipment), # Save dict of {slot: template_id}
            "coinage": self.coinage,
            # Max HP/Essence are usually recalculated, not saved directly unless modified by effects
            # Level, Description, Sex, Race, Class usually saved only when changed significantly
        }

        # Only proceed if there's actually data to save
        if not data_to_save:
            log.warning("Character %s: No data generated to save.", self.name)
            return

        log.debug("Attempting save for character %s (ID: %s)... Data: %s", self.name, self.dbid, data_to_save)
        try:
            # Call the database function (which should now be the dynamic one)
            rowcount = await database.save_character_data(db_conn, self.dbid, data_to_save)

            # Log the outcome based on rowcount
            if rowcount is None:
                # This indicates an error occurred within execute_query/save_character_data
                log.error("Save FAILED for character %s (ID: %s), DB function returned None.", self.name, self.dbid)
            elif rowcount == 1:
                # This is the ideal, expected outcome
                log.info("Successfully saved character %s (ID: %s). 1 row affected.", self.name, self.dbid)
            elif rowcount == 0:
                # This means the WHERE id = ? clause didn't match any rows
                log.warning("Attempted to save character %s (ID: %s), but no rows were updated (ID not found in DB?).", self.name, self.dbid)
            else:
                # Handles the unexpected rowcount=2 (or other non-zero values)
                # Log as info for now, not warning, due to the unresolved issue
                log.info("Save attempt for character %s (ID: %s) completed. DB rowcount reported: %s.",
                        self.name, self.dbid, rowcount)

        except Exception as e:
            # Catch any other unexpected errors during the save process
            # Log the actual exception object 'e'
            log.exception("Unexpected error saving character %s (ID: %s): %s", self.name, self.dbid, e, exc_info=True)

    def respawn(self):
        """Resets character state after death"""
        log.info("RESPAWN: Character %s (ID %s) is respawning.", self.name, self.dbid)
        self.hp = self.max_hp
        self.essence = self.max_essence
        self.status = 'ALIVE'
        self.target = None
        self.is_fighting = False
        self.death_timer_ends_at = None
        self.roundtime = 0.0
        # Optionally add a short respawn sickness roundtime?


    def update_location(self, new_location: Optional['Room']):
        """
        Updates the character's current location reference.

        Args:
            new_location: The room object the character is now in, or None.
        """
        # TODO: Maybe trigger saving old room state / loading new? For now just update ref.
        old_loc_id = getattr(self.location, 'dbid', None)
        new_loc_id = getattr(new_location, 'dbid', None)
        self.location = new_location
        if new_location:
            self.location_id = new_location.dbid # Keep db id in sync
        log.debug("Character %s location updated from room %s to room %s",
                self.name, old_loc_id, new_loc_id)

    def calculate_initial_derived_attributes(self):
        """
        Sets initial Max HP/Essence based on stats AND max possible class die roll.
        Called from __init__ and potentially other recalculations.
        Also restores current HP/Essence to max.
        """
        vitality = self.stats.get("vitality", 10)
        aura = self.stats.get("aura", 10)
        persona = self.stats.get("persona", 10)

        vit_mod = utils.calculate_modifier(vitality)
        aura_mod = utils.calculate_modifier(aura)
        pers_mod = utils.calculate_modifier(persona)

        # Get MAX die roll values for initial calculation
        initial_hp_base = CLASS_HP_DIE.get(self.class_id, DEFAULT_HP_DIE) # Use max die value as base
        initial_essence_base = CLASS_ESSENCE_DIE.get(self.class_id, DEFAULT_ESSENCE_DIE) # Use max die value as base

        # SET Max HP/Essence (Base is max die roll + modifier)
        self.max_hp = initial_hp_base + vit_mod
        self.max_essence = initial_essence_base + aura_mod + pers_mod # Add base essence roll too

        # Clamp minimums? Should Max HP/Essence always be at least 1?
        self.max_hp = max(1, self.max_hp)
        self.max_essence = max(0, self.max_essence) # Essence can be 0

        # Restore current HP/Essence to Max (could be initial or after stat change/level)
        # Ensure current HP/Essence doesn't exceed new max if stats decreased somehow
        self.hp = min(self.hp, self.max_hp)
        self.essence = min(self.essence, self.max_essence)
        # Generally restore fully on level up / init
        self.hp = self.max_hp
        self.essence = self.max_essence


        log.debug("Character %s: Derived attributes calculated/updated: MaxHP=%d, MaxEssence=%d",
                self.name, self.max_hp, self.max_essence)

    def apply_level_up_gains(self) -> Tuple[int, int]:
        """
        Calculates HP/Essence gains based on class dice rolls and current modifiers,
        updates max values, and restores current HP/Essence to new max.
        Should be called AFTER level has been incremented.

        Returns:
            A tuple containing (hp_increase, essence_increase).
        """
        current_vit_mod = self.vit_mod
        current_aura_mod = self.aura_mod
        current_pers_mod = self.pers_mod

        # Get die sizes for the character's class
        hp_die_size = CLASS_HP_DIE.get(self.class_id, DEFAULT_HP_DIE)
        essence_die_size = CLASS_ESSENCE_DIE.get(self.class_id, DEFAULT_ESSENCE_DIE)

        # Roll the dice
        hp_roll = random.randint(1, hp_die_size)
        essence_roll = random.randint(1, essence_die_size)

        # Calculate increase (ensure minimums)
        hp_increase = max(1, hp_roll + current_vit_mod)
        essence_increase = max(0, essence_roll + current_aura_mod)

        # Apply increase to max values
        self.max_hp += hp_increase
        self.max_essence += essence_increase

        # Restore current HP/Essence to new max
        self.hp = self.max_hp
        self.essence = self.max_essence

        log.debug("Character %s Level Up Gains: HP Roll(d%d)=%d, Mod=%d -> +%d (New Max: %d); Essence Roll(d%d)=%d, Mod=%d -> +%d (New Max: %d)",
                self.name, hp_die_size, hp_roll, current_vit_mod, hp_increase, self.max_hp,
                essence_die_size, essence_roll, current_aura_mod + current_pers_mod, essence_increase, self.max_essence)

        return hp_increase, essence_increase

    def is_alive(self) -> bool: # Add helper consistent with Mob
        return self.hp > 0 and self.status != "DEAD" # DYING counts as alive for some checks

    # # def get_total_armor_value(self) -> int:
    # #     """Calculates total armor value from worn equipment."""
    # #     total_av = 0
    # #     if not hasattr(self, 'world'): return 0 # Safety check if world ref removed

    #     for template_id in self.equipment.values():
    #         template = self.world.get_item_template(template_id) # Needs world access! Refactor needed?
    #          # *** NOTE: This get_total_armor_value method WILL require passing world if self.world removed ***
    #          # *** OR Cache item instances in self.equipment instead of IDs ***
    #          # *** For now, ASSUME self.world exists for simplicity of this step ***
    #          # *** We will need to address this dependency ***
    #         if template:
    #             try:
    #                 stats_dict = json.loads(template['stats'] or '{}')
    #                 total_av += stats_dict.get("armor", 0)
    #             except (json.JSONDecodeError, TypeError): pass # Ignore bad item stats
    #     return total_av

    def get_skill_rank(self, skill_name: str) -> int:
        """Gets the character's rank in a specific skill"""
        return self.skills.get(skill_name.lower(), 0) # Return 0 if skill unknown

    def get_skill_modifier(self, skill_name: str) -> int:
        """
        Calculates the total modifier for a skill check.
        (skill rank + attribute modifier)
        """
        skill_name_lower = skill_name.lower()
        rank = self.get_skill_rank(skill_name_lower)

        # Find the governing attribute
        attr_name = skill_defs.get_attribute_for_skill(skill_name_lower)
        if not attr_name:
            log.warning("No attribute mapping found for skill '%s'", skill_name_lower)
            return rank # return just the rank if no attribute defined.
        
        # Get the attribute value and calculate its modifier
        attr_value = self.stats.get(attr_name, 10) # Default 10 if stat missing
        attr_mod = utils.calculate_modifier(attr_value)

        return rank + attr_mod

    def __repr__(self) -> str:
            return f"<Character {self.dbid}: '{self.first_name} {self.last_name}'>"

    def __str__(self) -> str:
            loc_id = getattr(self.location, 'dbid', self.location_id) # Show current or last known dbid
            return f"Character(id={self.dbid}, name='{self.first_name} {self.last_name}', loc={loc_id})"