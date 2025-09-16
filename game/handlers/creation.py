# game/handlers/creation.py
"""
Handles the interactive character creation process.
"""
import textwrap
import asyncio
import logging
import json
from enum import Enum, auto
from typing import Optional, Dict, Any, List

from game.database import db_manager
from game import utils
from game.player import Player
from game.world import World
from game.definitions import traits as trait_defs, races as race_defs, classes as class_defs, abilities as ability_defs

log = logging.getLogger(__name__)

class CreationState(Enum):
    GET_FIRST_NAME = auto()
    GET_LAST_NAME = auto()
    GET_SEX = auto()
    GET_RACE = auto()
    GET_CLASS = auto()
    ROLL_STATS = auto()
    CONFIRM_STATS = auto()
    ASSIGN_STATS = auto()
    BUILD_DESCRIPTION_START = auto()
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
    FINALIZE = auto()
    COMPLETE = auto()
    CANCELLED = auto()

class CreationHandler:
    """Manages the state machine for creating a new character."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                 player: Player, world: World, db_manager_instance):
        self.reader = reader
        self.writer = writer
        self.player = player
        self.world = world
        self.db_manager = db_manager_instance
        self.state = CreationState.GET_FIRST_NAME
        self.addr = writer.get_extra_info('peername', 'Unknown Address')
        self.creation_data: Dict[str, Any] = {
            "first_name": None, "last_name": None, "sex": None, "race_id": None, "race_name": None, 
            "class_id": None, "class_name": None, "stats": {}, "base_stats": [], 
            "description_traits": {}, "description": ""
        }
        self._available_scores: List[int] = []
        self._assigning_stat_index: int = 0
        self._stat_order = ["might", "vitality", "agility", "intellect", "aura", "persona"]
        self._trait_keys: List[str] = []
        self._current_trait_index: int = 0

    async def _prompt(self, message: str):
        if not message.endswith(("\n\r", "\r\n")):
            message += ": "
        self.writer.write(message.encode('utf-8'))
        await self.writer.drain()

    async def _read_line(self) -> Optional[str]:
        try:
            data = await self.reader.readuntil(b'\n')
            decoded_data = data.decode('utf-8').strip()
            if decoded_data.lower() == 'quit':
                self.state = CreationState.CANCELLED
                return None
            return decoded_data
        except (ConnectionResetError, asyncio.IncompleteReadError, BrokenPipeError):
            self.state = CreationState.CANCELLED
            return None

    async def _send(self, message: str):
        if self.writer.is_closing(): return
        if not message.endswith('\r\n'):
            message += '\r\n'
        try:
            self.writer.write(utils.colorize(message).encode('utf-8'))
            await self.writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            self.state = CreationState.CANCELLED

    async def _handle_get_name(self, part: str):
        await self._prompt(f"Enter character {part} name (or 'quit')")
        name = await self._read_line()
        if name is None: return
        if not name or len(name) > 15 or not name.isalpha():
            await self._send(f"Invalid {part} name. Please use 1-15 letters only.")
            return
        self.creation_data[f"{part}_name"] = name
        self.state = CreationState.GET_LAST_NAME if part == "first" else CreationState.GET_SEX

    async def _handle_get_sex(self):
        options = {"m": "Male", "f": "Female", "t": "They/Them"}
        prompt = "\r\nSelect your character's sex:\r\n" + "\r\n".join([f" [{k.upper()}] {v}" for k, v in options.items()])
        await self._send(prompt)
        await self._prompt("Enter choice (m/f/t)")
        choice = await self._read_line()
        if choice is None: return
        chosen_sex = options.get(choice.lower())
        if not chosen_sex:
            await self._send("Invalid choice.")
            return
        self.creation_data["sex"] = chosen_sex
        self.state = CreationState.GET_RACE

    async def _handle_get_race(self):
        races = await self.db_manager.fetch_all("SELECT id, name, description FROM races ORDER BY id")
        if not races:
            await self._send("Error loading races. Cannot continue creation.")
            self.state = CreationState.CANCELLED
            return
        prompt = "\r\n--- Select a Race ---\r\n"
        race_map = {i + 1: dict(race_row) for i, race_row in enumerate(races)}
        prompt += "\r\n".join([f" {i}. {r['name']} - {r['description']}" for i, r in race_map.items()])
        await self._send(prompt)
        await self._prompt("Enter the number of your choice")
        choice = await self._read_line()
        if choice is None: return
        try:
            selected_race = race_map.get(int(choice))
            if not selected_race:
                await self._send("Invalid selection.")
                return
            self.creation_data["race_id"] = selected_race['id']
            self.creation_data["race_name"] = selected_race['name']
            self.state = CreationState.GET_CLASS
        except (ValueError, TypeError):
            await self._send("Invalid input. Please enter a number.")

    async def _handle_get_class(self):
        classes = await self.db_manager.fetch_all("SELECT id, name, description FROM classes ORDER BY id")
        if not classes:
            await self._send("Error loading classes. Cannot continue creation.")
            self.state = CreationState.CANCELLED
            return
        prompt = "\r\n--- Select a Class ---\r\n"
        class_map = {i + 1: dict(class_row) for i, class_row in enumerate(classes)}
        prompt += "\r\n".join([f" {i}. {c['name']} - {c['description']}" for i, c in class_map.items()])
        await self._send(prompt)
        await self._prompt("Enter the number of your choice")
        choice = await self._read_line()
        if choice is None: return
        try:
            selected_class = class_map.get(int(choice))
            if not selected_class:
                await self._send("Invalid selection.")
                return
            self.creation_data["class_id"] = selected_class['id']
            self.creation_data["class_name"] = selected_class['name']
            self.state = CreationState.ROLL_STATS
        except (ValueError, TypeError):
            await self._send("Invalid input. Please enter a number.")

    async def _handle_roll_stats(self):
        self.creation_data["base_stats"] = utils.generate_stat_set()
        stats_str = ", ".join(map(str, self.creation_data["base_stats"]))
        await self._send(f"\r\nYour generated stats: [ {stats_str} ]")
        await self._prompt("Type 'keep' to accept these scores, or 'reroll' to try again")
        self.state = CreationState.CONFIRM_STATS

    async def _handle_confirm_stats(self):
        choice = await self._read_line()
        if choice is None: return
        if choice.lower() == 'keep':
            race_name = self.creation_data.get("race_name", "Unknown")
            await self._send("\r\n" + race_defs.format_racial_modifiers(race_name))
            self._available_scores = list(self.creation_data["base_stats"])
            self._assigning_stat_index = 0
            self.state = CreationState.ASSIGN_STATS
        elif choice.lower() == 'reroll':
            self.state = CreationState.ROLL_STATS
        else:
            await self._send("Please type 'keep' or 'reroll'.")

    async def _handle_assign_stats(self):
        if self._assigning_stat_index >= len(self._stat_order):
            race_name = self.creation_data.get("race_name", "").lower()
            racial_mods = race_defs.get_racial_modifiers(race_name)
            final_stats = self.creation_data["stats"]
            for stat, bonus in racial_mods.items():
                if stat in final_stats:
                    final_stats[stat] = max(1, final_stats[stat] + bonus)
            self.state = CreationState.BUILD_DESCRIPTION_START
            return
        current_stat = self._stat_order[self._assigning_stat_index]
        scores_str = ", ".join(map(str, self._available_scores))
        await self._send(f"\r\nAvailable scores: [ {scores_str} ]\r\nAssign a score to {current_stat.capitalize()}:")
        choice_str = await self._read_line()
        if choice_str is None: return
        try:
            chosen_score = int(choice_str)
            if chosen_score not in self._available_scores:
                await self._send("That score is not available.")
                return
            self.creation_data["stats"][current_stat] = chosen_score
            self._available_scores.remove(chosen_score)
            self._assigning_stat_index += 1
        except (ValueError, TypeError):
            await self._send("Invalid input. Please enter a number.")
            
    async def _handle_build_description_start(self):
        race_name = self.creation_data.get("race_name", "").lower()
        options = trait_defs.get_trait_options(race_name)
        if not options:
            self.state = CreationState.FINALIZE
            return
        preferred_order = [ "Height", "Build", "Skin Tone", "Skin Pattern", "Shell Color", "Head Shape", 
                            "Hair Style", "Hair Color", "Eye Color", "Ear Shape", "Nose Type", "Beard Style", "Tusk Style" ]
        self._trait_keys = sorted(options.keys(), key=lambda k: preferred_order.index(k) if k in preferred_order else 99)
        self._current_trait_index = 0
        self.creation_data["description_traits"] = {}
        await self._transition_to_next_trait()

    async def _transition_to_next_trait(self):
        """Helper to move to the next trait state or finalize."""
        if self._current_trait_index >= len(self._trait_keys):
            self.state = CreationState.FINALIZE
            return
        next_trait_key = self._trait_keys[self._current_trait_index]
        try:
            enum_key = f"GET_TRAIT_{next_trait_key.upper().replace(' ', '_')}"
            self.state = CreationState[enum_key]
        except KeyError:
            log.error(f"Could not find CreationState for trait key '{next_trait_key}'")
            self.state = CreationState.FINALIZE

    async def _handle_get_trait(self, trait_key: str):
        race_name = self.creation_data.get("race_name", "").lower()
        options = trait_defs.get_trait_options(race_name).get(trait_key, [])
        if not options:
            self._current_trait_index += 1
            await self._transition_to_next_trait()
            return
        prompt = f"\r\n--- Select {trait_key} ---\r\n" + "\r\n".join([f" {i+1}. {opt}" for i, opt in enumerate(options)])
        await self._send(prompt)
        await self._prompt(f"Enter the number for your desired {trait_key}")
        choice = await self._read_line()
        if choice is None: return
        try:
            selection_num = int(choice)
            if 1 <= selection_num <= len(options):
                self.creation_data["description_traits"][trait_key] = options[selection_num - 1]
                self._current_trait_index += 1
                await self._transition_to_next_trait()
            else:
                await self._send("Invalid selection.")
        except (ValueError, TypeError):
            await self._send("Invalid input. Please enter a number.")

    def _build_description_string(self) -> str:
        """Builds the character description paragraph from selected traits."""
        traits = self.creation_data.get("description_traits", {})
        race_name = self.creation_data.get("race_name", "Unknown")
        class_name = self.creation_data.get("class_name", "Unknown")
        char_name = f"{self.creation_data.get('first_name','')} {self.creation_data.get('last_name','')}".strip()
        sex = self.creation_data.get("sex", "They/Them")
        defaults = trait_defs.get_default_traits(race_name)
        subj, _, poss, verb_is, _ = utils.get_pronouns(sex)
        
        height = traits.get("Height", defaults.get("Height", "average"))
        build = traits.get("Build", defaults.get("Build", "average"))
        
        description_parts = [f"You see {char_name}, a {height.lower()} {race_name} {class_name} with a {build.lower()} build."]
        return " ".join(description_parts)

    async def _handle_finalize(self):
        class_name = self.creation_data.get('class_name', '')
        stats_dict = self.creation_data.get("stats", {})
        vit_mod = utils.calculate_modifier(stats_dict.get("vitality", 10))
        aura_mod = utils.calculate_modifier(stats_dict.get("aura", 10))
        pers_mod = utils.calculate_modifier(stats_dict.get("persona", 10))
        
        hp_die = class_defs.CLASS_HP_DIE.get(self.creation_data.get("class_id"), 6)
        max_hp = float(hp_die + vit_mod)
        max_essence = float(aura_mod + pers_mod)

        spells, abilities = [], []
        for key, data in ability_defs.ABILITIES_DATA.items():
            reqs = data.get("class_req", [])
            if data.get("level_req", 99) == 1 and (not reqs or class_name.lower() in reqs):
                if data.get("type", "").upper() == "SPELL": spells.append(key)
                else: abilities.append(key)

        new_char_id = await self.db_manager.create_character(
            player_id=self.player.dbid, first_name=self.creation_data["first_name"],
            last_name=self.creation_data["last_name"], sex=self.creation_data["sex"],
            race_id=self.creation_data["race_id"], class_id=self.creation_data["class_id"],
            stats=stats_dict, description=self._build_description_string(), 
            hp=max_hp, max_hp=max_hp, essence=max_essence, max_essence=max_essence
        )

        if new_char_id:
            self.creation_data["new_char_id"] = new_char_id
            self.state = CreationState.COMPLETE
        else:
            await self._send("A database error occurred during character finalization.")
            self.state = CreationState.CANCELLED

    async def handle(self) -> Optional[int]:
        await self._send("\r\n--- Character Creation ---\r\nType 'quit' at any time to cancel.")
        
        state_map = {
            CreationState.GET_FIRST_NAME: lambda: self._handle_get_name("first"),
            CreationState.GET_LAST_NAME: lambda: self._handle_get_name("last"),
            CreationState.GET_SEX: self._handle_get_sex,
            CreationState.GET_RACE: self._handle_get_race,
            CreationState.GET_CLASS: self._handle_get_class,
            CreationState.ROLL_STATS: self._handle_roll_stats,
            CreationState.CONFIRM_STATS: self._handle_confirm_stats,
            CreationState.ASSIGN_STATS: self._handle_assign_stats,
            CreationState.BUILD_DESCRIPTION_START: self._handle_build_description_start,
            CreationState.GET_TRAIT_HEIGHT: lambda: self._handle_get_trait("Height"),
            CreationState.GET_TRAIT_BUILD: lambda: self._handle_get_trait("Build"),
            CreationState.GET_TRAIT_SKIN_TONE: lambda: self._handle_get_trait("Skin Tone"),
            CreationState.GET_TRAIT_HAIR_STYLE: lambda: self._handle_get_trait("Hair Style"),
            CreationState.GET_TRAIT_HAIR_COLOR: lambda: self._handle_get_trait("Hair Color"),
            CreationState.GET_TRAIT_EYE_COLOR: lambda: self._handle_get_trait("Eye Color"),
            CreationState.GET_TRAIT_NOSE_TYPE: lambda: self._handle_get_trait("Nose Type"),
            CreationState.GET_TRAIT_EAR_SHAPE: lambda: self._handle_get_trait("Ear Shape"),
            CreationState.GET_TRAIT_HEAD_SHAPE: lambda: self._handle_get_trait("Head Shape"),
            CreationState.GET_TRAIT_BEARD_STYLE: lambda: self._handle_get_trait("Beard Style"),
            CreationState.GET_TRAIT_SKIN_PATTERN: lambda: self._handle_get_trait("Skin Pattern"),
            CreationState.GET_TRAIT_SHELL_COLOR: lambda: self._handle_get_trait("Shell Color"),
            CreationState.FINALIZE: self._handle_finalize,
        }

        while self.state not in [CreationState.COMPLETE, CreationState.CANCELLED]:
            current_state = self.state
            handler_method = state_map.get(current_state)
            if handler_method:
                await handler_method()
            else:
                log.error("Unhandled creation state: %s", self.state.name)
                self.state = CreationState.CANCELLED
            if self.state == current_state:
                await asyncio.sleep(0.1)

        if self.state == CreationState.COMPLETE:
            await self._send("\r\nCharacter creation complete!")
        else:
            await self._send("\r\nCharacter creation cancelled.")
            
        return self.creation_data.get("new_char_id")