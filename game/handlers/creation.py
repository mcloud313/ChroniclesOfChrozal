# game/handlers/creation.py

"""
Handles the interactive character creation process.
"""
import asyncio
import logging
import json
from enum import Enum, auto
from typing import Optional, Dict, Any, List
# Imports from game package
from game import database
from game import utils
from game.player import Player
from game.character import Character
from game.world import World
# Import trait definitions (assuming traits.py is in game/definitions/)
try:
    from ..definitions import traits as trait_defs
except ImportError:
    log.error("Could not import trait definitions! Creation menus will fail.")
    trait_defs = None
# Need a reference back to ConnectionState? Or just return success/fail?
# Let's return new Character on success, None on failure/quit.
from .connection import ConnectionState # Needed for setting state on ConnectionHandler

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
            # TODO: Show racial bonuses here before assignment?
            # racial_bonus_text = self._get_racial_bonus_text()
            # await self._send(racial_bonus_text)
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
            "Height", "Build", "Hair Style", "Hair Color", "Eye Color", "Nose Type"
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
        """Constructs the description string from selected traits."""
        # Basic Pronoun logic
        sex = self.creation_data.get("sex")
        pronoun_subj = "They" # Default
        pronoun_obj = "them"
        pronoun_poss = "their"
        verb_is = "are"
        verb_has = "have"

        if sex == "Male":
            pronoun_subj = "He"
            pronoun_obj = "him"
            pronoun_poss = "his"
            verb_is = "is"
            verb_has = "has"
        elif sex == "Female":
            pronoun_subj = "She"
            pronoun_obj = "her"
            pronoun_poss = "her"
            verb_is = "is"
            verb_has = "has"

        # Get traits with defaults if missing
        traits = self.creation_data.get("description_traits", {})
        height = traits.get("Height", "average height")
        build = traits.get("Build", "an average build")
        hair_style = traits.get("Hair Style", "nondescript hair")
        hair_color = traits.get("Hair Color", "") # Color might be included in style
        eye_color = traits.get("Eye Color", "dark eyes")
        nose_type = traits.get("Nose Type", "an unremarkable nose")
        # Add other traits here

        # Construct sentence (can be much more elaborate)
        desc = (
            f"You see {self.creation_data['first_name']} {self.creation_data['last_name']}, "
            f"a {self.creation_data.get('race_name', 'Unknown Race')} {self.creation_data.get('class_name', 'Unknown Class')}.\r\n" # Need class name!
            f"{pronoun_subj} {verb_is} {height} with {build}.\r\n"
            f"{pronoun_subj} {verb_has} {hair_style} {hair_color} hair, {eye_color} eyes, and {nose_type}."
            # Add more sentences for other traits
        )
        # Need class name - fetch it maybe? Or store it earlier? Let's store it.
        # Need to modify _handle_get_class to store class_name.
        return desc

    async def _handle_finalize(self):
        """Calculates derived stats, builds description, creates DB entry."""
        log.info("Finalizing character creation for player %s", self.player.dbid)

        # 1. Build Description String
        self.creation_data["description"] = self._build_description_string()
        log.debug("Generated Description: %s", self.creation_data["description"])

        # 2. Calculate Initial Derived Stats (HP/Essence)
        # We need the assigned stats from creation_data['stats']
        stats_dict = self.creation_data.get("stats", {})
        vitality = stats_dict.get("vitality", 10)
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
            location_id=1 # Start in default room
        )

        if new_char_id:
            log.info("Character ID %d created successfully in DB.", new_char_id)
            self.creation_data["new_char_id"] = new_char_id # Store ID to return
            self.state = CreationState.COMPLETE
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
                # Add elif for other GET_TRAIT_ states...
                elif current_state == CreationState.FINALIZE:
                    await self._handle_finalize()
                else:
                    log.error("Unhandled creation state %s for player %s", current_state, self.player.dbid)
                    self.state = CreationState.CANCELLED # Break loop on unknown state

                # Prevent tight loop if a state doesn't change on error/invalid input
                if self.state == current_state and current_state not in [CreationState.COMPLETE, CreationState.CANCELLED]:
                    await asyncio.sleep(0.1)
            except Exception as e:
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