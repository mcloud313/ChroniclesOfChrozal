# game/handlers/creation.py

"""
Handles the interactive character creation process.
"""
import asyncio
import logging
import json
import aiosqlite
from enum import Enum, auto
from typing import Optional, Dict, Any, List
# Imports from game package
from game import database
from game import utils
from game.player import Player
from game.character import Character
from game.world import World
# Import trait definitions (assuming traits.py is in game/definitions/)
log = logging.getLogger(__name__)
try:
    from ..definitions import traits as trait_defs
    from ..definitions import races as race_defs
    from ..definitions import classes as class_defs
    from ..definitions import abilities as ability_defs
except ImportError:
    log.error("Could not import trait definitions! Creation menus will fail.")
    trait_defs = None

log = logging.getLogger(__name__)

class CreationState(Enum):
    """States within the character creation process."""
    GET_FIRST_NAME = auto()
    GET_LAST_NAME = auto()
    GET_SEX = auto()
    GET_RACE = auto()
    GET_CLASS = auto()
    ROLL_STATS = auto()
    CONFIRM_STATS = auto()
    ASSIGN_STATS = auto()
    BUILD_DESCRIPTION_START = auto() # Entry point for description menus
    # Add states for each description menu (Height, Build, etc.)
    GET_TRAIT_HEIGHT = auto()
    GET_TRAIT_BUILD = auto()
    GET_TRAIT_HAIR_STYLE = auto()
    GET_TRAIT_HAIR_COLOR = auto()
    GET_TRAIT_EYE_COLOR = auto()
    GET_TRAIT_NOSE_TYPE = auto()
    GET_TRAIT_SKIN_TONE = auto()
    GET_TRAIT_BEARD_STYLE = auto()
    GET_TRAIT_EAR_SHAPE = auto()
    GET_TRAIT_SKIN_PATTERN = auto()
    GET_TRAIT_SHELL_COLOR = auto()
    GET_TRAIT_HEAD_SHAPE = auto()
    FINALIZE = auto() # Ready to create character in DB
    COMPLETE = auto() # Signifies success
    CANCELLED = auto() # User quit

class CreationHandler:
    """Manages the state machine for creating a new character."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                player: Player, world: World, db_conn: aiosqlite.Connection):
        self.reader = reader
        self.writer = writer
        self.player = player # 
        self.world = world
        self.db_conn = db_conn
        self.state = CreationState.GET_FIRST_NAME
        self.addr = writer.get_extra_info('peername', 'Unknown Address')

        # Data collected during creation
        self.creation_data: Dict[str, Any] = {
            "first_name": None,
            "last_name" : None,
            "sex": None,
            "race_id": None,
            "race_name": None, 
            "class_id": None,
            "stats": {},
            "base_stats": [],
            "description_traits": {},
            "description": ""
        }
        # Temporary state for stat assignment
        self._available_scores: List[int] = []
        self._assigning_stat_index: int = 0
        self._stat_order = ["might", "vitality", "agility", "intellect", "aura", "persona"]

        # Temporary state for description building
        self._trait_keys: List[str] = [] # Order of trait menus to present
        self._current_trait_index: int = 0

    # --- Helper Methods (similar to ConnectionHandler) ---
    async def _prompt(self, message: str):
        if not message.endswith("\n\r") and not message.endswith("\r\n"):
            message += ": "
        self.writer.write(message.encode('utf-8'))
        await self.writer.drain()

    async def _read_line(self) -> str | None:
        try:
            data = await self.reader.readuntil(b'\n')
            decoded_data = data.decode('utf-8').strip()
            # Allow 'quit' during creation
            if decoded_data.lower() == 'quit':
                self.state = CreationState.CANCELLED
                return None
            return decoded_data
        except (ConnectionResetError, asyncio.IncompleteReadError, BrokenPipeError) as e:
            log.warning("Connection lost from %s during creation read: %s", self.addr, e)
            self.state = CreationState.CANCELLED
            return None
        except Exception:
            log.exception("Unexpected error reading from %s during creation:", self.addr, exc_info=True)
            self.state = CreationState.CANCELLED
            return None

    async def _send(self, message: str):
        if self.writer.is_closing():
            return
        if not message.endswith('\r\n'):
            message += '\r\n'
        try:
            self.writer.write(message.encode('utf-8'))
            await self.writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            self.state = CreationState.CANCELLED
        except Exception:
            log.exception("Unexpected error writing to %s during creation:", self.addr, exc_info=True)
            self.state = CreationState.CANCELLED

    # --- State Handling Methods ---
    async def _handle_get_name(self, part: str):
        """Handles getting first or last name."""
        await self._prompt(f"Enter character {part} name (or 'quit')")
        name = await self._read_line()
        if name is None: return # Quit or connection lost

        if not name or len(name) > 15 or not name.isalpha(): # Basic validation
            await self._send(f"Invalid {part} name. Please use 1-15 letters only.")
            return # Stay in current state

        self.creation_data[f"{part}_name"] = name.capitalize()
        log.debug("Creation: Got %s name '%s' for player %s", part, self.creation_data[f"{part}_name"], self.player.dbid)
        # Transition to next state
        if part == "first":
            self.state = CreationState.GET_LAST_NAME
        else:
            self.state = CreationState.GET_SEX

    async def _handle_get_sex(self):
        options = {"m": "Male", "f": "Female", "t": "They/Them"}
        prompt = "\r\nSelect your character's sex:\r\n"
        for key, val in options.items():
            prompt += f" [{key.upper()}] {val}\r\n"

        await self._send(prompt)
        await self._prompt("Enter choice (m/f/t)")
        choice = await self._read_line()
        if choice is None: return

        chosen_sex = options.get(choice.lower())
        if not chosen_sex:
            await self._send("Invalid choice.")
            return # Stay in state

        self.creation_data["sex"] = chosen_sex
        log.debug("Creation: Got sex '%s' for player %s", chosen_sex, self.player.dbid)
        self.state = CreationState.GET_RACE

    async def _handle_get_race(self):
        races = await database.load_all_races(self.db_conn)
        if races is None:
            await self._send("Error loading races. Cannot continue creation.")
            self.state = CreationState.CANCELLED
            return

        prompt = "\r\n--- Select a Race ---\r\n"
        race_map: Dict[int, Dict] = {} # Map selection number to race row
        for i, race_row in enumerate(races):
            selection_num = i + 1
            race_map[selection_num] = dict(race_row) # Convert Row to dict
            prompt += f" {selection_num}. {race_row['name']} - {race_row['description']}\r\n"
        prompt += "--------------------\r\n"

        await self._send(prompt)
        await self._prompt("Enter the number of your choice")
        choice = await self._read_line()
        if choice is None: return

        try:
            selection_num = int(choice)
            selected_race = race_map.get(selection_num)
            if not selected_race:
                await self._send("Invalid selection.")
                return # Stay in state

            self.creation_data["race_id"] = selected_race['id']
            self.creation_data["race_name"] = selected_race['name'] # Store name too
            log.debug("Creation: Got race '%s' (ID: %s) for player %s",
                    selected_race['name'], selected_race['id'], self.player.dbid)
            self.state = CreationState.GET_CLASS
        except ValueError:
            await self._send("Invalid input. Please enter a number.")
            return

    async def _handle_get_class(self):
        # Similar logic to _handle_get_race
        classes = await database.load_all_classes(self.db_conn)
        if classes is None:
            await self._send("Error loading classes. Cannot continue creation.")
            self.state = CreationState.CANCELLED
            return

        prompt = "\r\n--- Select a Class ---\r\n"
        class_map: Dict[int, Dict] = {}
        for i, class_row in enumerate(classes):
            selection_num = i + 1
            class_map[selection_num] = dict(class_row)
            prompt += f" {selection_num}. {class_row['name']} - {class_row['description']}\r\n"
        prompt += "--------------------\r\n"

        await self._send(prompt)
        await self._prompt("Enter the number of your choice")
        choice = await self._read_line()
        if choice is None: return

        try:
            selection_num = int(choice)
            selected_class = class_map.get(selection_num)
            if not selected_class:
                await self._send("Invalid selection.")
                return

            self.creation_data["class_id"] = selected_class['id']
            self.creation_data["class_name"] = selected_class['name']
            log.debug("Creation: Got class '%s' (ID: %s) for player %s",
                    selected_class['name'], selected_class['id'], self.player.dbid)
            self.state = CreationState.ROLL_STATS
        except ValueError:
            await self._send("Invalid input. Please enter a number.")
            return

    async def _handle_roll_stats(self):
        """Generates and displays stats, prompts keep/reroll."""
        self.creation_data["base_stats"] = utils.generate_stat_set()
        stats_str = ", ".join(map(str, self.creation_data["base_stats"]))
        await self._send(f"\r\nYour generated stats: [ {stats_str} ]")
        await self._prompt("Type 'keep' to accept these scores, or 'reroll' to try again")
        self.state = CreationState.CONFIRM_STATS

    async def _handle_confirm_stats(self):
        """Processes keep/reroll input."""
        choice = await self._read_line()
        if choice is None: return

        choice = choice.lower()
        if choice == 'keep':
            race_name = self.creation_data.get("race_name", "Unknown")
            bonus_text = race_defs.format_racial_modifiers(race_name)
            await self._send("\r\n" + bonus_text) # Send the formatted bonus string
            await self._send("\r\nScores accepted. Now assign them.")
            self._available_scores = list(self.creation_data["base_stats"]) # Copy for assignment
            self._assigning_stat_index = 0 # Start assigning first stat
            self.state = CreationState.ASSIGN_STATS
        elif choice == 'reroll':
            await self._send("Rerolling...")
            self.state = CreationState.ROLL_STATS # Go back to roll again
        else:
            await self._send("Invalid choice. Please type 'keep' or 'reroll'.")
            # Stay in CONFIRM_STATS state, re-prompt happens in main loop implicitly

    async def _handle_assign_stats(self):
        """Handles assigning one stat score at a time."""
        if self._assigning_stat_index >= len(self._stat_order):
            log.debug("Creation: Base stats assigned: %s", self.creation_data['stats'])
            log.info("Applying racial modifiers...")
            race_name = self.creation_data.get("race_name", "").lower()
            racial_mods = race_defs.get_racial_modifiers(race_name)
            final_stats = self.creation_data["stats"] # Modify directly

            apply_msgs = []
            for stat, bonus in racial_mods.items():
                if stat in final_stats:
                    current_val = final_stats[stat]
                    # Apply bonus, ensure stat doesn't drop below 1 (or a higher minimum if desired)
                    final_stats[stat] = max(1, current_val + bonus)
                    apply_msgs.append(f"{stat.capitalize()} adjusted by {bonus:+d} -> {final_stats[stat]}")
                    log.debug("Applied %s %+d modifier. %s: %d -> %d",
                            race_name, bonus, stat, current_val, final_stats[stat])
                else:
                    log.warning("Stat %s not found in assigned stats for racial modifier.", stat)

            # Send feedback about applied modifiers
            if apply_msgs:
                await self._send("\r\nYour racial traits have adjusted your attributes:")
                for msg in apply_msgs:
                    await self._send(f" - {msg}")

            log.debug("Final stats after racial mods: %s", self.creation_data["stats"])

            # All stats assigned, move on
            log.debug("Creation: Stats assigned for player %s: %s", self.player.dbid, self.creation_data['stats'])
            # Prepare for description building
            self.state = CreationState.BUILD_DESCRIPTION_START
            return

        current_stat_to_assign = self._stat_order[self._assigning_stat_index]
        scores_str = ", ".join(map(str, self._available_scores))
        prompt = f"\r\nAvailable scores: [ {scores_str} ]\r\n"
        prompt += f"Assign a score to {current_stat_to_assign.capitalize()}:"

        await self._send(prompt)
        choice_str = await self._read_line()
        if choice_str is None: return

        try:
            chosen_score = int(choice_str)
            if chosen_score not in self._available_scores:
                await self._send("That score is not available. Please choose from the list.")
                return # Stay in state, re-prompt

            # Assign the score
            self.creation_data["stats"][current_stat_to_assign] = chosen_score
            self._available_scores.remove(chosen_score) # Remove from available
            self._assigning_stat_index += 1 # Move to next stat
            log.debug("Creation: Assigned %d to %s for player %s",
                    chosen_score, current_stat_to_assign, self.player.dbid)
            # Loop back in handle() to assign next stat or transition

        except ValueError:
            await self._send("Invalid input. Please enter a number from the available scores.")
            return

    async def _handle_build_description_start(self):
        """Sets up the description building process."""
        if not trait_defs:
            log.error("Trait definitions missing, cannot build description for player %s.", self.player.dbid)
            await self._send("Error: Trait definitions are missing. Skipping description setup.")
            self.state = CreationState.FINALIZE # Skip to finalize
            return

        race_name = self.creation_data.get("race_name", "").lower()
        options = trait_defs.get_trait_options(race_name)
        if not options:
            log.warning("No trait options found for race '%s' for player %s. Skipping description.",
                    race_name, self.player.dbid)
            self.state = CreationState.FINALIZE # Skip to finalize
            return

        # Get the ordered list of traits to ask about
        # Ensure consistent order: Height, Build, Hair Style, Hair Color, Eye Color, Nose Type ...
        self._trait_keys = [
            "Height", "Build", "Hair Style", "Hair Color", "Eye Color", "Nose Type", "Beard Type",
            "Skin Tone", "Ear Shape", "Head Shape", "Shell Color", "Skin Pattern"
            # Add other keys consistent with trait_defs.py, checking if they exist for the race
        ]
        # Filter keys based on what's actually available for the race
        self._trait_keys = [key for key in self._trait_keys if key in options]

        if not self._trait_keys:
            log.warning("No valid trait keys found to prompt for race '%s'. Skipping.", race_name)
            self.state = CreationState.FINALIZE
            return

        self._current_trait_index = 0
        self.creation_data["description_traits"] = {} # Reset traits dict
        # Transition to the first specific trait state dynamically maybe? Or use a generic state?
        # Let's use specific states for clarity, matching the keys.
        first_trait_key = self._trait_keys[0]
        try:
            self.state = CreationState[f"GET_TRAIT_{first_trait_key.upper().replace(' ', '_')}"]
        except KeyError:
            log.error("Could not find matching CreationState for trait key '%s'", first_trait_key)
            self.state = CreationState.FINALIZE # Fallback if state enum mismatch

    async def _handle_get_trait(self, trait_key: str):
        """Handles prompting for a specific physical trait."""
        if not trait_defs or self._current_trait_index >= len(self._trait_keys):
            self.state = CreationState.FINALIZE # Should not happen if start logic is right
            return

        # trait_key should match the key used in TRAIT_OPTIONS (e.g., "Hair Style")
        race_name = self.creation_data.get("race_name", "").lower()
        options_dict = trait_defs.get_trait_options(race_name)
        trait_options = options_dict.get(trait_key, [])

        if not trait_options:
            log.warning("No options found for trait '%s', race '%s'. Skipping trait.", trait_key, race_name)
            # Move to next trait
            self._current_trait_index += 1
            if self._current_trait_index >= len(self._trait_keys):
                self.state = CreationState.FINALIZE
            else:
                next_trait_key = self._trait_keys[self._current_trait_index]
                try:
                    self.state = CreationState[f"GET_TRAIT_{next_trait_key.upper().replace(' ', '_')}"]
                except KeyError:
                    log.error("Could not find matching CreationState for trait key '%s'", next_trait_key)
                    self.state = CreationState.FINALIZE
            return

        prompt = f"\r\n--- Select {trait_key} ---\r\n"
        for i, option in enumerate(trait_options):
            prompt += f" {i+1}. {option}\r\n"
        prompt += "--------------------\r\n"

        await self._send(prompt)
        await self._prompt(f"Enter the number for your desired {trait_key}")
        choice = await self._read_line()
        if choice is None: return

        try:
            selection_num = int(choice)
            if 1 <= selection_num <= len(trait_options):
                selected_trait = trait_options[selection_num - 1]
                self.creation_data["description_traits"][trait_key] = selected_trait
                log.debug("Creation: Got trait '%s' = '%s' for player %s", trait_key, selected_trait, self.player.dbid)

                # Move to next trait or finalize
                self._current_trait_index += 1
                if self._current_trait_index >= len(self._trait_keys):
                    self.state = CreationState.FINALIZE
                else:
                    next_trait_key = self._trait_keys[self._current_trait_index]
                    try:
                        self.state = CreationState[f"GET_TRAIT_{next_trait_key.upper().replace(' ', '_')}"]
                    except KeyError:
                        log.error("Could not find matching CreationState for trait key '%s'", next_trait_key)
                        self.state = CreationState.FINALIZE # Fallback

            else:
                await self._send("Invalid selection.")
                return # Stay in current trait state
        except ValueError:
            await self._send("Invalid input. Please enter a number.")
            return # Stay in current trait state

    def _build_description_string(self) -> str:
        """Constructs a more detailed description paragraph from selected traits."""
        traits = self.creation_data.get("description_traits", {})
        sex = self.creation_data.get("sex")
        race_name = self.creation_data.get('race_name', 'Unknown Race')
        # Ensure class_name was stored in _handle_get_class!
        class_name = self.creation_data.get('class_name', 'Unknown Class')
        first_name = self.creation_data.get('first_name', 'Someone')
        last_name = self.creation_data.get('last_name', '')

        # --- Pronoun Setup ---
        pronoun_subj, _, pronoun_poss, verb_is, verb_has = utils.get_pronouns(sex) # Correct

        # --- Build Description Parts ---
        description_parts = []

        # Initial line
        description_parts.append(f"You see {first_name} {last_name}, {utils.get_article(race_name)} {race_name} {class_name}.")

        # --- Physical Build ---
        height = traits.get("Height", "").lower()
        build = traits.get("Build", "").lower()
        if height and build:
            description_parts.append(f"{pronoun_subj} {verb_is} of {height} height and {verb_has} {utils.get_article(build)} {build} build.")
        elif height:
            description_parts.append(f"{pronoun_subj} {verb_is} of {height} height.")
        elif build:
            description_parts.append(f"{pronoun_subj} {verb_has} {utils.get_article(build)} {build} build.")

        # --- Skin / Shell / Patterns ---
        skin_tone = traits.get("Skin Tone", "").lower()
        skin_pattern = traits.get("Skin Pattern", "").lower()
        shell_color = traits.get("Shell Color", "").lower()
        skin_sentence_parts = []
        if skin_tone:
            skin_sentence_parts.append(f"{pronoun_poss} skin has {utils.get_article(skin_tone)} {skin_tone} tone")
        if skin_pattern:
            skin_sentence_parts.append(f"is marked by {skin_pattern} patterns") # Changed phrasing
        if shell_color:
            skin_sentence_parts.append(f"is protected by {utils.get_article(shell_color)} {shell_color} shell")

        if skin_sentence_parts:
            # Combine skin parts grammatically
            skin_desc = skin_sentence_parts[0]
            if len(skin_sentence_parts) > 1:
                skin_desc += " and " + skin_sentence_parts[1]
            if len(skin_sentence_parts) > 2: # Max 3 assumed for now
                skin_desc += " and " + skin_sentence_parts[2]
            description_parts.append(f"{pronoun_subj}'s body {skin_desc}.") # Form sentence

        # --- Head / Hair / Beard ---
        head_shape = traits.get("Head Shape", "").lower()
        hair_style = traits.get("Hair Style", "").lower()
        hair_color = traits.get("Hair Color", "").lower()
        beard_style = traits.get("Beard Style", "").lower()
        head_sentence_parts = []
        # Head shape first if present
        if head_shape:
            head_sentence_parts.append(f"{pronoun_subj} {verb_has} {utils.get_article(head_shape)} {head_shape} head")

        # Combine hair style/color
        hair_desc = ""
        if hair_style and hair_color and hair_style != "bald":
            hair_desc = f"{hair_style} {hair_color} hair"
        elif hair_style: # e.g., Bald
            hair_desc = f"{hair_style} hair" # "bald hair" is okay for generic MUD desc
        if hair_desc:
            head_sentence_parts.append(hair_desc)

        # Add beard info
        if beard_style and beard_style not in ["none", "clean-shaven"]:
            head_sentence_parts.append(f"and {utils.get_article(beard_style)} {beard_style} beard")
        elif beard_style == "clean-shaven":
            head_sentence_parts.append("and a clean-shaven face")

        if head_sentence_parts:
            # Construct sentence - capitalize first word if needed
            first_word = head_sentence_parts[0]
            if not description_parts[-1].endswith((".", "?", "!")): # Check if previous part ended sentence
                first_word = first_word[0].lower() + first_word[1:]
            else: # Start new sentence
                first_word = first_word[0].upper() + first_word[1:]

            head_sentence = first_word
            if len(head_sentence_parts) > 1:
                head_sentence += ", " + ", ".join(head_sentence_parts[1:-1]) # Middle parts with comma
                if len(head_sentence_parts) > 2: head_sentence += "," # Comma before 'and' if > 2 parts
                head_sentence += " and " + head_sentence_parts[-1] # Last part with 'and'
            description_parts.append(head_sentence + ".")


        # --- Facial Features ---
        eye_color = traits.get("Eye Color", "").lower()
        ear_shape = traits.get("Ear Shape", "").lower()
        nose_type = traits.get("Nose Type", "").lower()
        facial_sentence_parts = []
        if eye_color:
            facial_sentence_parts.append(f"{eye_color} eyes")
        if ear_shape:
            facial_sentence_parts.append(f"{ear_shape} ears")
        if nose_type:
            facial_sentence_parts.append(f"{utils.get_article(nose_type)} {nose_type} nose")

        if facial_sentence_parts:
            face_desc = ", ".join(facial_sentence_parts[:-1])
            if len(facial_sentence_parts) > 1:
                face_desc += " and " + facial_sentence_parts[-1]
            elif facial_sentence_parts:
                face_desc = facial_sentence_parts[0]

            # Start new sentence
            description_parts.append(f"{pronoun_poss.capitalize()} face is distinguished by {face_desc}.")

        # --- Combine and Return ---
        # Join parts with spaces, ensuring only one space between sentences.
        full_desc = " ".join(description_parts)
        # Add placeholder for equipment
        full_desc += f"\r\n{pronoun_subj} {verb_is} wearing:\r\n Nothing."

        return full_desc.strip()

    async def _handle_finalize(self):
        """Calculates derived stats, builds description, gets starting skills/abilities, creates DB entry."""
        log.info("Finalizing character creation for player %s", self.player.dbid)
        class_name = self.creation_data.get('class_name') # Needed for lookup
        class_name_lower = class_name.lower() if class_name else ""

        # 1. Build Description String
        self.creation_data["description"] = self._build_description_string()
        log.debug("Generated Description: %s", self.creation_data["description"])

        # 2. Calculate Initial Derived Stats (HP/Essence)
        # We need the assigned stats from creation_data['stats']
        stats_dict = self.creation_data.get("stats", {})
        might= stats_dict.get("might", 10)
        vitality = stats_dict.get("vitality", 10)
        agility = stats_dict.get("agility", 10)
        intellect = stats_dict.get("intellect", 10)
        aura = stats_dict.get("aura", 10)
        persona = stats_dict.get("persona", 10)
        # Get base HP from class - need class info! Load class data here?
        # Or define base HP constants based on class_id? Use constants for now.
        class_base_hp = {1: 10, 2: 4, 3: 8, 4: 6} # Warrior, Mage, Cleric, Rogue
        base_hp = class_base_hp.get(self.creation_data.get("class_id"), 6) # Default if class unknown

        mig_mod = utils.calculate_modifier(might)
        vit_mod = utils.calculate_modifier(vitality)
        agi_mod = utils.calculate_modifier(agility)
        int_mod = utils.calculate_modifier(intellect)
        aura_mod = utils.calculate_modifier(aura)
        pers_mod = utils.calculate_modifier(persona)

        max_hp = base_hp + vit_mod
        max_essence = aura_mod + pers_mod
        hp = max_hp # Start full
        essence = max_essence # Start full

        log.debug("Calculated initial stats: MaxHP=%d, MaxEssence=%d", max_hp, max_essence)

        starting_spells = []
        starting_abilities = []

        for ability_key, data in ability_defs.ABILITIES_DATA.items():
            # Check level requirement is 1
            if data.get("level_req", 999) == 1:
                allowed_classes = data.get("class_req", [])
                # Check if class matches or if skill is for all classes
                if not allowed_classes or class_name_lower in allowed_classes:
                    ability_type = data.get("type", "ABILITY").upper()
                    if ability_type == "SPELL":
                        starting_spells.append(ability_key) # Store internal key name
                    else: # Assume ability
                        starting_abilities.append(ability_key)

        known_spells_json = json.dumps(sorted(starting_spells))
        known_abilities_json = json.dumps(sorted(starting_abilities))
        log.debug("Assigning starting spells: %s, abilities: %s", starting_spells, starting_abilities)



        # 3. Prepare data for DB insert
        try:
            skills_json = json.dumps({}) # Start with empty skills
            stats_json = json.dumps(self.creation_data["stats"])
        except TypeError as e:
            log.error("Failed to serialize stats/skills to JSON: %s", e)
            await self._send("An internal error occurred preparing character data.")
            self.state = CreationState.CANCELLED
            return

        # 4. Call database.create_character
        new_char_id = await database.create_character(
            conn=self.db_conn,
            player_id=self.player.dbid,
            first_name=self.creation_data["first_name"],
            last_name=self.creation_data["last_name"],
            sex=self.creation_data["sex"],
            race_id=self.creation_data["race_id"],
            class_id=self.creation_data["class_id"],
            stats_json=stats_json,
            skills_json=skills_json, # Empty for now
            description=self.creation_data["description"],
            hp=hp,
            max_hp=max_hp,
            essence=essence,
            max_essence=max_essence,
            known_spells_json=known_abilities_json,
            known_abilities_json=known_abilities_json,
            location_id=1 # Start in default room
        )

        if new_char_id:
            log.info("Character ID %d created successfully in DB.", new_char_id)
            self.creation_data["new_char_id"] = new_char_id # Store ID to return
            self.state = CreationState.COMPLETE
            learned_output = []
            if starting_spells:
                # Get display names using helper function
                spell_names = [ability_defs.get_ability_data(s).get("name", s) for s in starting_spells]
                learned_output.append("spells: " + ", ".join(spell_names))
            if starting_abilities:
                ability_names = [ability_defs.get_ability_data(a).get("name", a) for a in starting_abilities]
                learned_output.append("abilities: " + ", ".join(ability_names))
            if learned_output:
                await self._send(f"\r\nAs a {class_name.title()}, you begin knowing the following " + " and ".join(learned_output) + ".")
        else:
            log.error("Database failed to create character for player %s.", self.player.dbid)
            await self._send("A database error occurred during character finalization. Please contact an admin.")
            self.state = CreationState.CANCELLED # Treat DB error as cancellation

    # --- Main Handler Loop ---
    async def handle(self) -> Optional[int]:
        """
        Runs the character creation state machine.

        Returns:
            The dbid of the newly created character on success,
            None if the user quits or an error occurs.
        """
        log.debug("CreationHandler starting for player %s (%s)", self.player.username, self.addr)
        await self._send("\r\n--- Character Creation ---\r\nType 'quit' at any time to cancel.")

        while self.state not in [CreationState.COMPLETE, CreationState.CANCELLED]:
            current_state = self.state # Cache state in case it changes during await
            try:
                if current_state == CreationState.GET_FIRST_NAME:
                    await self._handle_get_name("first")
                elif current_state == CreationState.GET_LAST_NAME:
                    await self._handle_get_name("last")
                elif current_state == CreationState.GET_SEX:
                    await self._handle_get_sex()
                elif current_state == CreationState.GET_RACE:
                    await self._handle_get_race()
                elif current_state == CreationState.GET_CLASS:
                    await self._handle_get_class()
                elif current_state == CreationState.ROLL_STATS:
                    await self._handle_roll_stats()
                elif current_state == CreationState.CONFIRM_STATS:
                    await self._handle_confirm_stats()
                elif current_state == CreationState.ASSIGN_STATS:
                    await self._handle_assign_stats()
                elif current_state == CreationState.BUILD_DESCRIPTION_START:
                    await self._handle_build_description_start()
                # Handle specific trait states dynamically if possible, or list them
                elif current_state == CreationState.GET_TRAIT_HEIGHT:
                    await self._handle_get_trait("Height")
                elif current_state == CreationState.GET_TRAIT_BUILD:
                    await self._handle_get_trait("Build")
                elif current_state == CreationState.GET_TRAIT_HAIR_STYLE:
                    await self._handle_get_trait("Hair Style")
                elif current_state == CreationState.GET_TRAIT_HAIR_COLOR:
                    await self._handle_get_trait("Hair Color")
                elif current_state == CreationState.GET_TRAIT_EYE_COLOR:
                    await self._handle_get_trait("Eye Color")
                elif current_state == CreationState.GET_TRAIT_NOSE_TYPE:
                    await self._handle_get_trait("Nose Type")
                elif current_state == CreationState.GET_TRAIT_SKIN_TONE:
                    await self._handle_get_trait("Skin Tone")
                elif current_state == CreationState.GET_TRAIT_EAR_SHAPE:
                    await self._handle_get_trait("Ear Shape")
                elif current_state == CreationState.GET_TRAIT_BEARD_STYLE:
                    await self._handle_get_trait("Beard Style")
                elif current_state == CreationState.GET_TRAIT_HEAD_SHAPE:
                    await self._handle_get_trait("Head Shape")
                elif current_state == CreationState.GET_TRAIT_SHELL_COLOR:
                    await self._handle_get_trait("Shell Color")
                elif current_state == CreationState.GET_TRAIT_SKIN_PATTERN:
                    await self._handle_get_trait("Skin Pattern")
                elif current_state == CreationState.FINALIZE:
                    await self._handle_finalize()
                else:
                    log.error("Unhandled creation state %s for player %s", current_state, self.player.dbid)
                    self.state = CreationState.CANCELLED # Break loop on unknown state

                # Prevent tight loop if a state doesn't change on error/invalid input
                if self.state == current_state and current_state not in [CreationState.COMPLETE, CreationState.CANCELLED]:
                    await asyncio.sleep(0.1)
            except Exception:
                log.exception("Unexpected error during creation state %s for player %s:", current_state, self.player.dbid, exc_info=True)
                await self._send("\r\nAn unexpected error occurred. Cancelling creation.")
                self.state = CreationState.CANCELLED

    # --- Loop finished ---
        if self.state == CreationState.COMPLETE:
            log.info("Character creation complete for player %s.", self.player.dbid)
            await self._send("\r\nCharacter creation complete!")
            return self.creation_data.get("new_char_id")
        else: # CANCELLED state
            log.info("Character creation cancelled for player %s.", self.player.dbid)
            await self._send("\r\nCharacter creation cancelled.")
            return None