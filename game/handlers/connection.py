# game/handlers/connection.py
"""
Handles the lifecycle of a single client connection, including login,
character selection, and passing commands to the command handler.
"""
import time
import config
import asyncio
import logging
from typing import Optional, Dict, Any

from game.database import db_manager
from game.player import Player
from game.character import Character
from game.world import World
from game import utils
from game.commands import handler as command_handler
from game.handlers.creation import CreationHandler
from game.definitions import skills as skill_defs
from game.definitions import classes as class_defs

log = logging.getLogger(__name__)

MOTD = """
--- {CWelcome to Chronicles of Chrozal (Alpha 0.50) ---{x
... (Your ASCII art and welcome message) ...
{W--------------------------------------------------{x
"""

class ConnectionState:
    GETTING_USERNAME = "GETTING_USERNAME"
    GETTING_PASSWORD = "GETTING_PASSWORD"
    GETTING_NEW_ACCOUNT_EMAIL = "GETTING_NEW_ACCOUNT_EMAIL"
    GETTING_NEW_PASSWORD = "GETTING_NEW_PASSWORD"
    CONFIRM_NEW_PASSWORD = "CONFIRM_NEW_PASSWORD"
    ASK_CREATE_ACCOUNT = "ASK_CREATE_ACCOUNT"
    SELECTING_CHARACTER = "SELECTING_CHARACTER"
    CREATING_CHARACTER = "CREATING_CHARACTER"
    PLAYING = "PLAYING"
    DISCONNECTED = "DISCONNECTED"

class ConnectionHandler:
    """Handles a single client connection and its state transitions."""

    MAX_PASSWORD_ATTEMPTS = 3

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, world: World, db_manager_instance):
        self.reader = reader
        self.writer = writer
        self.world = world
        self.db_manager = db_manager_instance
        self.state = ConnectionState.GETTING_USERNAME
        self.addr = writer.get_extra_info('peername', 'Unknown Address')
        self.player_account: Optional[Player] = None
        self.active_character: Optional[Character] = None
        self.password_attempts: int = 0
        self.new_account_data: Dict[str, Any] = {}
        log.info("ConnectionHandler initialized for %s", self.addr)

    async def _prompt(self, message: str):
        if not message.endswith(("\n\r", "\r\n")):
            message += ": "
        self.writer.write(message.encode(config.ENCODING))
        await self.writer.drain()

    async def _read_line(self) -> Optional[str]:
        try:
            data = await self.reader.readuntil(b'\n')
            decoded_data = data.decode(config.ENCODING).strip()
            if decoded_data.lower() == 'quit':
                self.state = ConnectionState.DISCONNECTED
                return None
            return decoded_data
        except (ConnectionResetError, asyncio.IncompleteReadError, BrokenPipeError):
            self.state = ConnectionState.DISCONNECTED
            return None

    async def _send(self, message: str, add_newline: bool = True):
        if self.writer.is_closing(): return
        message_to_send = utils.colorize(message)
        if add_newline and not message_to_send.endswith('\r\n'):
            message_to_send += '\r\n'
        self.writer.write(message_to_send.encode(config.ENCODING))
        await self.writer.drain()

    async def _handle_get_username(self):
        await self._prompt("Enter your account name")
        username = await self._read_line()
        if username is None: return

        player_data = await self.db_manager.load_player_account(username)
        if player_data:
            self.player_account = Player(**dict(player_data))
            self.state = ConnectionState.GETTING_PASSWORD
        else:
            self.new_account_data = {"username": username}
            self.state = ConnectionState.ASK_CREATE_ACCOUNT
    
    async def _handle_ask_create_account(self):
        username = self.new_account_data.get("username", "Unknown")
        await self._prompt(f"Account '{username}' not found. Create it? (yes/no)")
        choice = await self._read_line()
        if choice is None: return
        if choice.lower() in ['yes', 'y']:
            self.state = ConnectionState.GETTING_NEW_ACCOUNT_EMAIL
        else:
            self.state = ConnectionState.GETTING_USERNAME

    async def _handle_get_new_account_email(self):
        await self._prompt("Enter your email address")
        email = await self._read_line()
        if email and '@' in email and '.' in email.split('@')[-1]:
            self.new_account_data['email'] = email
            self.state = ConnectionState.GETTING_NEW_PASSWORD
        else:
            await self._send("Invalid email format.")

    async def _handle_get_new_password(self):
        await self._prompt("Choose a password (min 6 characters)")
        password = await self._read_line()
        if password and len(password) >= 6:
            self.new_account_data['password'] = password
            self.state = ConnectionState.CONFIRM_NEW_PASSWORD
        else:
            await self._send("Password too short.")
    
    async def _handle_confirm_new_password(self):
        await self._prompt("Confirm password")
        confirm_password = await self._read_line()
        if confirm_password == self.new_account_data.get('password'):
            hashed = utils.hash_password(self.new_account_data['password'])
            new_id = await self.db_manager.create_player_account(self.new_account_data['username'], hashed, self.new_account_data['email'])
            if new_id:
                player_data = await self.db_manager.load_player_account(self.new_account_data['username'])
                self.player_account = Player(**dict(player_data))
                self.state = ConnectionState.CREATING_CHARACTER
            else:
                await self._send("Failed to create account (username or email may be taken).")
                self.state = ConnectionState.GETTING_USERNAME
        else:
            await self._send("Passwords do not match. Please try again.")
            self.state = ConnectionState.GETTING_NEW_PASSWORD

    async def _handle_get_password(self):
        await self._prompt(f"Password for {self.player_account.username}")
        password = await self._read_line()
        if password is None: return

        is_match, needs_rehash = self.player_account.check_password(password)
        if is_match:
            if needs_rehash:
                log.info("Password for %s needs rehash. Upgrading now.", self.player_account.username)
                new_hash = utils.hash_password(password)
                await self.db_manager.execute_query("UPDATE players SET hashed_password = $1 WHERE id = $2", new_hash, self.player_account.dbid)
                self.player_account.hashed_password = new_hash
            self.state = ConnectionState.SELECTING_CHARACTER
        else:
            self.password_attempts += 1
            if self.password_attempts >= self.MAX_PASSWORD_ATTEMPTS:
                await self._send("Too many incorrect attempts. Disconnecting.")
                self.state = ConnectionState.DISCONNECTED
            else:
                await self._send(f"Incorrect password. ({self.MAX_PASSWORD_ATTEMPTS - self.password_attempts} attempts remaining)")

    async def _handle_select_character(self):
        char_list = await self.db_manager.load_characters_for_account(self.player_account.dbid)
        if not char_list:
            self.state = ConnectionState.CREATING_CHARACTER
            return

        output = ["\r\n--- Your Characters ---"]
        char_map = {i + 1: char['id'] for i, char in enumerate(char_list)}
        for i, char_row in enumerate(char_list):
            output.append(f" {i+1}. {char_row['first_name']} {char_row['last_name']} (Lvl {char_row['level']})")
        output.append("-----------------------\r\nEnter the number of a character, or type 'new':")
        await self._send("\r\n".join(output))

        selection = await self._read_line()
        if selection is None: return
        if selection.lower() == 'new':
            self.state = ConnectionState.CREATING_CHARACTER
            return

        try:
            char_id = char_map.get(int(selection))
            if char_id:
                char_data = await self.db_manager.load_character_data(char_id)
                self.active_character = Character(self.writer, dict(char_data), self.world, self.player_account.is_admin)
                await self._handle_post_load()
            else:
                await self._send("Invalid selection.")
        except ValueError:
            await self._send("Invalid input.")

    async def _handle_post_load(self):
        room = self.world.get_room(self.active_character.location_id) or self.world.get_room(1)
        self.active_character.update_location(room)
        room.add_character(self.active_character)
        self.world.add_active_character(self.active_character)
        self.active_character.login_timestamp = time.monotonic()
        await self._send(MOTD)
        await command_handler.process_command(self.active_character, self.world, "look")
        await room.broadcast(f"\r\n{self.active_character.name} has entered the realm.\r\n", {self.active_character})
        self.state = ConnectionState.PLAYING

    async def _handle_playing(self):
        while self.state == ConnectionState.PLAYING:
            prompt = (f"<{int(self.active_character.hp)}/{int(self.active_character.max_hp)}hp "
                      f"{int(self.active_character.essence)}/{int(self.active_character.max_essence)}e | "
                      f"{self.active_character.stance}> ")
            await self._send(prompt, add_newline=False)
            line = await self._read_line()
            if line is None: return
            if not await command_handler.process_command(self.active_character, self.world, line):
                self.state = ConnectionState.DISCONNECTED

    async def _handle_character_creation(self):
        creator = CreationHandler(self.reader, self.writer, self.player_account, self.world, self.db_manager)
        new_char_id = await creator.handle()
        if new_char_id:
            char_data = await self.db_manager.load_character_data(new_char_id)
            self.active_character = Character(self.writer, dict(char_data), self.world, self.player_account.is_admin)
            await self._handle_post_load()
        else:
            self.state = ConnectionState.SELECTING_CHARACTER

    async def handle(self):
        """Main connection state machine loop."""
        try:
            while self.state != ConnectionState.DISCONNECTED:
                handler_method = getattr(self, f"_handle_{self.state.lower()}", None)
                if handler_method:
                    await handler_method()
                else:
                    log.error("Unhandled connection state: %s", self.state)
                    self.state = ConnectionState.DISCONNECTED
        except Exception:
            log.exception("Unexpected error in ConnectionHandler for %s:", self.addr)
        finally:
            await self.cleanup()

    async def cleanup(self):
        log.info("Cleaning up connection for %s.", self.addr)
        if self.active_character:
            await self.active_character.save()
            if self.active_character.location:
                self.active_character.location.remove_character(self.active_character)
                await self.active_character.location.broadcast(f"\r\n{self.active_character.name} has left the realm.\r\n", {self.active_character})
            self.world.remove_active_character(self.active_character.dbid)
        if self.writer and not self.writer.is_closing():
            self.writer.close()
            await self.writer.wait_closed()
        log.info("Connection handler finished for %s.", self.addr)