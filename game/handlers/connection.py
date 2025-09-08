# game/handlers/connection.py
"""
Handles the lifecycle of a single client connection, including login,
character selection, and passing commands to the command handler.
"""
import time
import config
import asyncio
import logging
import aiosqlite
from enum import Enum, auto
from typing import Optional, Dict, Any

from game import database
from game.player import Player
from game.character import Character
from game.world import World
from game import utils
from game.commands import handler as command_handler
from game.handlers.creation import CreationHandler
from game.definitions import skills as skill_defs
from game.definitions import classes as class_defs

log = logging.getLogger(__name__)

# Simple Message of the Day
MOTD = """
--- {CWelcome to Chronicles of Chrozal (Alpha 0.50) ---{x
___  _  _  ____   __   __ _  __  ___  __    ____  ____       
/ __)/ )( \(  _ \ /  \ (  ( \(  )/ __)(  )  (  __)/ ___)      
( (__ ) __ ( )   /(  O )/    / )(( (__ / (_/\ ) _) \___ \      
\___)\_)(_/(__\_) \__/ \_)__)(__)\___)\____/(____)(____/      
                    __  ____                                 
                    /  \(  __)                                
                    (  O )) _)                                 
                    \__/(__)                                  
                        ___  _  _  ____   __  ____   __   __   
                    / __)/ )( \(  _ \ /  \(__  ) / _\ (  )  
                    ( (__ ) __ ( )   /(  O )/ _/ /    \/ (_/\
                    \___)\_)(_/(__\_) \__/(____)\_/\_/\____/
{W--------------------------------------------------{x
"""

class ConnectionState(Enum):
    GETTING_USERNAME = auto()
    GETTING_PASSWORD = auto()
    GETTING_NEW_ACCOUNT_EMAIL = auto()
    GETTING_NEW_PASSWORD = auto()
    CONFIRM_NEW_PASSWORD = auto()
    ASK_CREATE_ACCOUNT = auto()
    SELECTING_CHARACTER = auto()
    CREATING_CHARACTER = auto()
    PLAYING = auto()
    DISCONNECTED = auto()

class ConnectionHandler:
    """Handles a single client connection and its state transitions."""

    MAX_PASSWORD_ATTEMPTS = 3

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, world: World, db_conn: aiosqlite.Connection):
        self.reader = reader
        self.writer = writer
        self.world = world
        self.db_conn = db_conn
        self.state = ConnectionState.GETTING_USERNAME
        self.addr = writer.get_extra_info('peername', 'Unknown Address')

        self.player_account: Optional[Player] = None
        self.active_character: Optional[Character] = None
        self.password_attempts: int = 0
        self.new_account_data: Dict[str, Any] = {}

        log.info("ConnectionHandler initialized for %s", self.addr)

    async def _prompt(self, message: str, hide_input: bool = False):
        """Sends a prompt to the client."""
        if not message.endswith("\n\r") and not message.endswith("\r\n"):
            message += ": "
        self.writer.write(message.encode('utf-8'))
        await self.writer.drain()

    async def _read_line(self) -> str | None:
        """Reads a line of input from the client."""
        try:
            data = await self.reader.readuntil(b'\n')
            if data.startswith(b'\xff'):
                log.debug("Received Telnet IAC sequence from %s: %r", self.addr, data)
                return ""
            decoded_data = data.decode('utf-8').strip()
            log.debug("Received from %s: %r", self.addr, decoded_data)
            if decoded_data.lower() == 'quit':
                self.state = ConnectionState.DISCONNECTED
                return None
            return decoded_data
        except (ConnectionResetError, asyncio.IncompleteReadError, BrokenPipeError) as e:
            log.warning("Connection lost from %s during read: %s", self.addr, e)
            self.state = ConnectionState.DISCONNECTED
            return None
        except Exception:
            log.exception("Unexpected error reading from %s:", self.addr)
            self.state = ConnectionState.DISCONNECTED
            return None

    async def _send(self, message: str, add_newline: bool = True):
        """Safely sends a message to the client, applying color codes."""
        if self.writer.is_closing():
            return
        message_to_send = utils.colorize(message)
        if add_newline and not message_to_send.endswith('\r\n'):
            message_to_send += '\r\n'
        try:
            log.debug("Sending to %s: %r", self.addr, message)
            self.writer.write(message_to_send.encode(config.ENCODING))
            await self.writer.drain()
        except (ConnectionResetError, BrokenPipeError) as e:
            log.warning("Connection lost from %s during write: %s", self.addr, e)
            self.state = ConnectionState.DISCONNECTED
        except Exception:
            log.exception("Unexpected error writing to %s:", self.addr)
            self.state = ConnectionState.DISCONNECTED

    async def _handle_get_username(self):
        """Handles prompting for and receiving the username."""
        await self._prompt("Enter your account name")
        username = await self._read_line()
        if username is None: return

        if not username or not username.isalnum() or len(username) < 3 or len(username) > 20:
            await self._send("Invalid username. Must be 3-20 letters/numbers only.")
            return

        player_data = await database.load_player_account(self.db_conn, username)
        if player_data:
            self.player_account = Player(
                dbid=player_data['id'],
                username=player_data['username'],
                email=player_data['email'],
                hashed_password=player_data['hashed_password'],
                is_admin=player_data['is_admin']
            )
            log.info("Player account '%s' found for %s.", username, self.addr)
            self.password_attempts = 0
            self.state = ConnectionState.GETTING_PASSWORD
        else:
            log.info("Player account '%s' not found for %s.", username, self.addr)
            self.new_account_data = {"username": username}
            self.state = ConnectionState.ASK_CREATE_ACCOUNT

    async def _handle_ask_create_account(self):
        """Asks the user if they want to create a new account."""
        username = self.new_account_data.get("username", "Unknown")
        await self._prompt(f"Account '{username}' not found. Create it? (yes/no)")
        choice = await self._read_line()
        if choice is None: return

        if choice.lower() in ['yes', 'y']:
            self.state = ConnectionState.GETTING_NEW_ACCOUNT_EMAIL
        elif choice.lower() in ['no', 'n']:
            self.new_account_data = {}
            self.state = ConnectionState.GETTING_USERNAME
        else:
            await self._send("Please enter 'yes' or 'no'.")

    async def _handle_get_new_account_email(self):
        """Prompts for and validates new account email."""
        await self._prompt("Enter your email address")
        email = await self._read_line()
        if email is None: return

        if not email or '@' not in email or '.' not in email.split('@')[-1]:
            await self._send("Invalid email format. Please try again.")
            return

        self.new_account_data['email'] = email
        self.state = ConnectionState.GETTING_NEW_PASSWORD

    async def _handle_get_new_password(self):
        """Prompts for new account password."""
        await self._prompt("Choose a password (min 6 characters)")
        password = await self._read_line()
        if password is None: return

        if not password or len(password) < 6:
            await self._send("Password too short. Must be at least 6 characters.")
            return

        self.new_account_data['password'] = password
        self.state = ConnectionState.CONFIRM_NEW_PASSWORD

    async def _handle_confirm_new_password(self):
        """Prompts for password confirmation and creates account if match."""
        await self._prompt("Confirm password")
        confirm_password = await self._read_line()
        if confirm_password is None: return

        if confirm_password != self.new_account_data.get('password'):
            await self._send("Passwords do not match. Please try setting password again.")
            self.new_account_data.pop('password', None)
            self.state = ConnectionState.GETTING_NEW_PASSWORD
            return

        username = self.new_account_data['username']
        email = self.new_account_data['email']
        password = self.new_account_data['password']
        hashed = utils.hash_password(password)

        new_player_id = await database.create_player_account(self.db_conn, username, hashed, email)
        self.new_account_data = {}

        if new_player_id:
            await self._send(f"Account '{username}' created successfully!")
            player_data = await database.load_player_account(self.db_conn, username)
            if player_data:
                self.player_account = Player(
                    dbid=player_data['id'],
                    username=player_data['username'],
                    email=player_data['email'],
                    hashed_password=player_data['hashed_password'],
                    is_admin=player_data['is_admin']
                )
                self.state = ConnectionState.CREATING_CHARACTER
            else:
                await self._send("Error loading your new account data. Disconnecting.")
                self.state = ConnectionState.DISCONNECTED
        else:
            await self._send("Failed to create account (possibly email already in use?). Please try again.")
            self.state = ConnectionState.GETTING_USERNAME

    async def _handle_get_password(self):
        """Handles prompting for and verifying the password, with migration logic."""
        if not self.player_account:
            log.error("Reached GETTING_PASSWORD state without a loaded player account for %s.", self.addr)
            self.state = ConnectionState.DISCONNECTED
            return

        await self._prompt(f"Password for {self.player_account.username}")
        password = await self._read_line()
        if password is None: return

        is_match, needs_rehash = self.player_account.check_password(password)

        if is_match:
            log.info("Password correct for player %s (%s).", self.player_account.username, self.addr)
            
            # This is the core of the seamless upgrade.
            if needs_rehash:
                log.info("Password for %s needs rehash. Upgrading now.", self.player_account.username)
                try:
                    # 1. Generate the new Argon2 hash for the correct password.
                    new_hash = utils.hash_password(password)
                    # 2. Update the hash in the database.
                    await database.update_player_password(self.db_conn, self.player_account.dbid, new_hash)
                    # 3. Update the hash on the in-memory player object.
                    self.player_account.hashed_password = new_hash
                    log.info("Password for %s successfully upgraded to Argon2.", self.player_account.username)
                except Exception:
                    log.exception("Failed to rehash and save new password for %s.", self.player_account.username)
                    # Don't lock the user out if this fails; they can still play this session.
                    await self._send("{rNote: Could not update your password to the new secure format. Please report this.{x")

            await self._send("\r\nPassword accepted.")
            self.state = ConnectionState.SELECTING_CHARACTER
        else:
            self.password_attempts += 1
            log.warning("Incorrect password attempt %d/%d for player %s (%s).",
                        self.password_attempts, self.MAX_PASSWORD_ATTEMPTS, self.player_account.username, self.addr)
            if self.password_attempts >= self.MAX_PASSWORD_ATTEMPTS:
                await self._send("\r\nToo many incorrect attempts. Disconnecting.")
                self.state = ConnectionState.DISCONNECTED
            else:
                await self._send(f"\r\nIncorrect password. ({self.MAX_PASSWORD_ATTEMPTS - self.password_attempts} attempts remaining)")

    async def _handle_select_character(self):
        """Handles listing characters and processing selection."""
        if not self.player_account:
            self.state = ConnectionState.DISCONNECTED
            return

        char_list_data = await database.load_characters_for_account(self.db_conn, self.player_account.dbid)

        if not char_list_data:
            await self._send("\r\nYou have no characters on this account.")
            self.state = ConnectionState.CREATING_CHARACTER
            return

        output = "\r\n --- Your Characters ---\r\n"
        char_map: Dict[int, int] = {}
        for i, char_row in enumerate(char_list_data):
            selection_num = i + 1
            char_map[selection_num] = char_row['id']
            race_name = self.world.get_race_name(char_row['race_id'])
            class_name = self.world.get_class_name(char_row['class_id'])
            output += f" {selection_num}. {char_row['first_name']} {char_row['last_name']} ({race_name} {class_name} {char_row['level']})\r\n"
        output += "----------------------------------\r\n"
        output += "Enter the number of the character to play, or type 'new' to create another:"

        await self._send(output)
        selection = await self._read_line()
        if selection is None: return

        if selection.lower() == 'new':
            self.state = ConnectionState.CREATING_CHARACTER
            return
            
        try:
            selection_num = int(selection)
            selected_char_id = char_map.get(selection_num)

            if not selected_char_id:
                await self._send("Invalid selection.")
                return

            char_data = await database.load_character_data(self.db_conn, selected_char_id)
            if not char_data:
                await self._send("Error loading selected character. Please try again.")
                return
            
            self.active_character = Character(
                writer=self.writer,
                db_data=dict(char_data),
                world=self.world,
                player_is_admin=self.player_account.is_admin
            )
            await self._handle_post_load()

        except ValueError:
            await self._send("Invalid input. Please enter a number or 'new'.")
            return
        except Exception:
            log.exception("Error during character selection/loading for %s:", self.addr)
            await self._send("An internal error occurred. Disconnecting.")
            self.state = ConnectionState.DISCONNECTED

    async def _handle_post_load(self):
        """Actions performed immediately after a character is loaded and active."""
        if not self.active_character:
            self.state = ConnectionState.DISCONNECTED
            return

        self.world.add_active_character(self.active_character)
        room = self.world.get_room(self.active_character.location_id)
        if not room:
            log.warning("Character %s loaded into non-existent room %d! Moving to room 1.",
                self.active_character.name, self.active_character.location_id)
            room = self.world.get_room(1)
            if not room:
                log.critical("!!! Default room 1 not found! Cannot place character %s.", self.active_character.name)
                await self._send("Critical error: Starting room not found. Disconnecting.")
                self.state = ConnectionState.DISCONNECTED
                self.world.remove_active_character(self.active_character.dbid)
                return
            self.active_character.location_id = 1
        
        self.active_character.update_location(room)
        room.add_character(self.active_character)
        await self.active_character.send(MOTD)
        look_string = room.get_look_string(self.active_character, self.world)
        await self.active_character.send(look_string)
        arrival_msg = f"\r\n{self.active_character.name} slowly approaches.\r\n"
        await room.broadcast(arrival_msg, exclude={self.active_character})

        # NEW: Set the login timestamp to begin tracking playtime for this session.
        self.active_character.login_timestamp = time.monotonic()
        
        self.state = ConnectionState.PLAYING
        log.info("Character %s entered game world in room %d.", self.active_character.name, room.dbid)

    async def _handle_playing(self):
        """Handles input when the player is fully in the game."""
        if not self.active_character:
            self.state = ConnectionState.DISCONNECTED
            return

        while self.state == ConnectionState.PLAYING:
            # We will send a prompt that includes HP, Essence, and Stance
            hp = int(self.active_character.hp)
            max_hp = int(self.active_character.max_hp)
            essence = int(self.active_character.essence)
            max_essence = int(self.active_character.max_essence)
            stance = self.active_character.stance
            
            prompt = f"<{hp}/{max_hp}hp {essence}/{max_essence}e|{stance}> "
            await self._send(prompt, add_newline=False)
            
            line = await self._read_line()
            if line is None: return

            should_continue = await command_handler.process_command(
                self.active_character, self.world, line
            )
            if not should_continue:
                self.state = ConnectionState.DISCONNECTED

    async def handle(self):
        """Main handling loop driven by state machine."""
        try:
            while self.state != ConnectionState.DISCONNECTED:
                current_state = self.state
                log.debug("Handler loop for %s, state: %s", self.addr, current_state)

                if current_state == ConnectionState.GETTING_USERNAME:
                    await self._handle_get_username()
                elif current_state == ConnectionState.ASK_CREATE_ACCOUNT:
                    await self._handle_ask_create_account()
                elif current_state == ConnectionState.GETTING_NEW_ACCOUNT_EMAIL:
                    await self._handle_get_new_account_email()
                elif current_state == ConnectionState.GETTING_NEW_PASSWORD:
                    await self._handle_get_new_password()
                elif current_state == ConnectionState.CONFIRM_NEW_PASSWORD:
                    await self._handle_confirm_new_password()
                elif current_state == ConnectionState.GETTING_PASSWORD:
                    await self._handle_get_password()
                elif current_state == ConnectionState.SELECTING_CHARACTER:
                    await self._handle_select_character()
                elif current_state == ConnectionState.CREATING_CHARACTER:
                    await self._handle_character_creation()
                elif self.state == ConnectionState.PLAYING:
                    await self._handle_playing()
                else:
                    log.error("Unhandled connection state %s for %s. Disconnecting.", self.state, self.addr)
                    self.state = ConnectionState.DISCONNECTED
        except Exception:
            log.exception("Unexpected error in ConnectionHandler for %s:", self.addr)
        finally:
            await self.cleanup()

    async def _handle_character_creation(self):
        """Orchestrates the character creation process."""
        if not self.player_account:
            log.error("Reached CREATING_CHARACTER without player account! Disconnecting %s.", self.addr)
            self.state = ConnectionState.DISCONNECTED
            return

        creation_handler = CreationHandler(
            self.reader, self.writer, self.player_account, self.world, self.db_conn
        )
        new_character_id = await creation_handler.handle()

        if new_character_id:
            char_data = await database.load_character_data(self.db_conn, new_character_id)
            if char_data:
                self.active_character = Character(
                    writer=self.writer,
                    db_data=dict(char_data),
                    world=self.world,
                    player_is_admin=self.player_account.is_admin
                )
                
                # Grant initial skills and points
                for skill_name in skill_defs.INITIAL_SKILLS:
                    if skill_name not in self.active_character.skills:
                        self.active_character.skills[skill_name] = 0

                int_mod = self.active_character.int_mod
                initial_sp = 5 + int_mod
                race_name = self.world.get_race_name(self.active_character.race_id)
                if race_name.lower() == "chrozalin":
                    initial_sp += 5

                class_name = self.world.get_class_name(self.active_character.class_id)
                skill_bonuses = class_defs.get_starting_skill_bonuses(class_name)
                for skill, bonus in skill_bonuses.items():
                    self.active_character.skills[skill] = self.active_character.skills.get(skill, 0) + bonus
                
                self.active_character.unspent_skill_points = initial_sp
                
                await self.active_character.send(f"\r\nYour class grants you proficiency in several skills.")
                await self.active_character.send(f"You have {initial_sp} skill points to begin your journey!")
                
                await self._handle_post_load()
            else:
                await self._send("Critical error loading your new character. Disconnecting.")
                self.state = ConnectionState.DISCONNECTED
        else:
            await self._send("\r\nReturning to character selection.")
            self.state = ConnectionState.SELECTING_CHARACTER

    async def cleanup(self):
        """Perform cleanup when connection ends."""
        log.info("Cleaning up connection for %s.", self.addr)
        self.state = ConnectionState.DISCONNECTED

        if self.active_character:
            char_to_clean = self.active_character
            self.world.remove_active_character(char_to_clean.dbid)
            self.active_character = None
            if char_to_clean.location:
                departure_msg = f"\r\n{char_to_clean.name} slowly departs.\r\n"
                try:
                    await char_to_clean.location.broadcast(departure_msg, exclude={char_to_clean})
                except Exception as e:
                    log.error("Error broadcasting departure for %s: %s", char_to_clean.name, e)
                char_to_clean.location.remove_character(char_to_clean)
            
            await char_to_clean.save(self.db_conn)

        if self.writer and not self.writer.is_closing():
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception as e:
                log.warning("Error closing writer for %s: %s", self.addr, e)
        log.info("Connection handler finished for %s.", self.addr)