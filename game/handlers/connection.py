# game/handlers/connection.py
"""
Handles the lifecycle of a single client connection, including login,
character selection, and passing commands to the command handler.
"""

import asyncio
import logging
import aiosqlite
from enum import Enum, auto
from typing import Optional, Dict, Any
# Import necessary game components using relative paths
from game import database
from game.player import Player
from game.character import Character
from game.world import World
from game import utils

# Assume command handler will exist later
# from ..comands import handler as command_handler

log = logging.getLogger(__name__)

# Simple Message of the Day
MOTD = """
\r\n--- Welcome to Chronicles of Chrozal (Alpha) ---
\r\n                 .''--''.
\r\n                /        `.
\r\n               |  O    O  |
\r\n               `.________.'
\r\n              .-'------'-.
\r\n            .'   :-..-;   `.
\r\n           /   .'      `.   \\
\r\n          |   /          \\   |
\r\n          \\   |          |   /
\r\n           \\  \\.--""--.//  /
\r\n            `._        _.'
\r\n               `------'
\r\n--------------------------------------------------
\r\n"""

# Define connection states
class ConnectionState(Enum):
    GETTING_USERNAME = auto()
    GETTING_PASSWORD = auto()
    SELECTING_CHARACTER = auto()
    PLAYING = auto()
    DISCONNECTED = auto()

class ConnectionHandler:
    """Handles a single client connection and its state transitions"""

    MAX_PASSWORD_ATTEMPTS = 3

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, world: World, db_conn: aiosqlite.Connection):
        self.reader = reader
        self.writer = writer
        self.world = world
        self.db_conn = db_conn # Keep connection if needed for transactions later
        self.state = ConnectionState.GETTING_USERNAME
        self.addr = writer.get_extra_info('peername', 'Unknown Address')

        self.player_account: Optional[Player] = None # Holds loaded player account
        self.active_character: Optional[Character] = None # Holds loaded character object
        self.password_attempts: int = 0

        log.info("ConnectionHandler initialized for %s", self.addr)

    async def _prompt(self, message: str, hide_input: bool = False):
        """Sends a prompt to the client. Adds newline if needed."""
        # In Telnet, hiding input requires specific negotiation (IAC WILL ECHO / WON'T ECHO)
        # For simplicity now, we don't hide password input, just indicate it.
        if not message.endswith("\n\r") and not message.endswith("\r\n"):
            message += ": " # Simple prompt indicator
        # Add newline for prompt display separation if desired, or keep it on same line
        # message = "\r\n" + message

        self.writer.write(message.encode('utf-8'))
        await self.writer.drain()

    async def _read_line(self) -> str | None:
        """Reads a line of input from the client, handles errors."""
        try:
            # Read until newline character, common for Telnet clients
            data = await self.reader.readuntil(b'\n')
            decoded_data = data.decode('utf-8').strip() # Decode and remove whitespace/newlines
            log.debug("Received from %s: %r", self.addr, decoded_data)
            return decoded_data
        except (ConnectionResetError, asyncio.IncompleteReadError, BrokenPipeError) as e:
            log.warning("Connection lost from %s during read: %s", self.addr, e)
            self.state = ConnectionState.DISCONNECTED
            return None
        except Exception as e:
            log.exception("Unexpected error reading from %s:", self.addr, exc_info=True)
            self.state = ConnectionState.DISCONNECTED
            return None
        
    async def _send(self, message: str):
        """Safely sends a message to the client using writer."""
        if self.writer.is_closing():
            return
        if not message.endswith('\r\n'):
            message += '\r\n' # Ensure proper newline for telnet
        try: 
            self.writer.write(message.encode('utf-8'))
            await self.writer.drain()
        except (ConnectionResetError, BrokenPipeError) as e:
            log.warning("Connection lost from %s during write: %s", self.addr, e)
            self.state = ConnectionState.DISCONNECTED
        except Exception as e:
            log.exception("Unexpected error writing to %s:", self.addr, exc_info=True)
            self.state = ConnectionState.DISCONNECTED

    async def _handle_get_username(self):
        """Handles prompting for and receiving the username."""
        await self._prompt("Enter your account name")
        username = await self._read_line()
        if username is None: return # Connection lost

        if not username: #Empty input
            await self._send("Username cannot be empty.")
            return # Stay in current state, prompt again
        
        # Try to load account
        player_data = await database.load_player_account(self.db_conn, username)

        if player_data:
            # Instantiate player object (only holds account data)
            self.player_account = Player(
                dbid=player_data['id'],
                username=player_data['username'],
                email=player_data['email'],
                hashed_password=player_data['hashed_password']
            )
            log.info("Player account '%s' found for %s.", username, self.addr)
            self.password_attempts = 0
            self.state = ConnectionState.GETTING_PASSWORD
        else:
            # Defer account creation to phase 2
            log.info("Player account '%s' not found for %s.", username, self.addr)
            await self._send(f"Account '{username}' not found. Account creation not yet implemented.")
            # For now, disconnect or loop. Let's loop back.
            # self.state = ConnectionState.DISCONNECTED # Option: Disconnect
            await self._send("Please try again or type 'quit'.") # Option: Loop
            # Stay in GETTING_USERNAME state

    async def _handle_get_password(self):
        """Handles prompting for and verifying the password."""
        if not self.player_account:
            log.error("Reached GETTING_PASSWORD state without a loaded player account for %s.", self.addr)
            self.state = ConnectionState.DISCONNECTED
            return
        
        await self._prompt(f"Password for {self.player_account.username}") # Don't hide input yet
        password = await self._read_line()
        if password is None: return # Connection lost

        if self.player_account.check_password(password):
            log.info("Password correct for player %s (%s).", self.player_account.username, self.addr)
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
                # Stay in GETTING_PASSWORD state

    async def _handle_select_character(self):
        """Handles listing characters and processing selection."""
        if not self.player_account:
            log.error("Reached SELECTING_CHARACTER state without player account for %s.", self.addr)
            self.state = ConnectionState.DISCONNECTED
            return
        
        # --- V V V ADD DEBUG LOGGING HERE V V V ---
        player_id_to_query = self.player_account.dbid
        log.debug("Querying characters for player_id: %s", player_id_to_query)
        # --- ^ ^ ^ END DEBUG LOGGING ^ ^ ^ ---
        
        char_list_data = await database.load_characters_for_account(self.db_conn, self.player_account.dbid)

        if not char_list_data:
            log.info("No characters found for player %s (%s).", self.player_account.username, self.addr)
            # Defer character creation to Phase 2
            await self._send("\r\nYou have no characters on this account. Character creation is not yet implemented.")
            await self._send("Disconnecting.")
            self.state = ConnectionState.DISCONNECTED
            return

        # Format Character List
        output = "\r\n --- Your Characters ---\r\n"
        char_map: Dict[int, int] = {} # Map selection number to character dbid
        for i, char_row in enumerate(char_list_data):
            selection_num = i + 1
            char_map[selection_num] = char_row['id']
            # TODO: Fetch Race/Class names later instead of showing IDs
            output += (f" {selection_num}. {char_row['first_name']} {char_row['last_name']} "
                    f"(Level {char_row['level']} R:{char_row['race_id']} C:{char_row['class_id']})\r\n") # Show IDs for now
        output += "----------------------\r\n"
        output += "Enter the number of the character to play:"

        await self._send(output)
        selection = await self._read_line()
        if selection is None: return # Connection lost

        try:
            selection_num = int(selection)
            selected_char_id = char_map.get(selection_num)

            if not selected_char_id:
                await self._send("Invalid selection.")
                # Stay in SELECTING_CHARACTER state
                return
            
            # Load the full character data
            char_data = await database.load_character_data(self.db_conn, selected_char_id)
            if not char_data:
                # Should be rare if listed, but handle DB inconsistency
                log.error("Failed to load character data for selected ID %s for player %s.", selected_char_id, self.player_account.username)
                await self._send("Error loading selected character. Please try again.")
                return # Stay in SELECTING_CHARACTER state
            
            # Instantiate the Character object
            self.active_character = Character(writer=self.writer, db_data=char_data)
            log.info("Character '%s' loaded for player %s (%s).", self.active_character.name, self.player_account.username, self.addr)

            # Proceed to place character in world (Post-Load steps)
            await self._handle_post_load()

        except ValueError:
            await self._send("Invalid input. Please enter a number.")
            # Stay in SELECTING_CHARACTER state
            return
        except Exception as e:
            log.exception("Error during character selection/loading for %s:", self.addr, exc_info=True)
            await self._send("An internal error occurred. Disconnecting.")
            self.state = ConnectionState.DISCONNECTED

    async def _handle_post_load(self):

        """Actions performed immediately after a character is loaded and active."""
        if not self.active_character:
            log.error("Reached _handle_post_load without active character for %s.", self.addr)
            self.state = ConnectionState.DISCONNECTED
            return
        
        # 1 Add to World Tracking
        self.world.add_active_character(self.active_character)

        # 2. Set Location
        room = self.world.get_room(self.active_character.location_id)
        if not room:
            log.warning("Charcter %s loaded into non-existent room %d! Moving to room 1.",
                self.active_character.name, self.active_character.location_id)
            room = self.world.get_room(1) # Fallback to default room
            if not room: #Should absolutely exist, but safety check
                log.critical("!!! Default room 1 not found! Cannot place character %s.", self.active_character.name)
                await self._send("Critical error: Starting room not found. Disconnecting.")
                self.state = ConnectionState.DISCONNECTED
                # Also remove from active list if added
                self.world.remove_active_character(self.active_character.dbid)
                return
            self.active_character.location_id = 1 # Update DB ID to match
        self.active_character.update_location(room)

        # 3. Add Character to Room Occupants
        room.add_character(self.active_character)

        # 4. Send MOTD
        await self.active_character.send(MOTD)

        # 5. Send Initial Look
        look_string = room.get_look_string(self.active_character)
        await self.active_character.send(look_string)

        #6 Announce Arrival to Room
        arrival_msg = f"\r\n{self.active_character.name} slowly approaches.\r\n"
        room.broadcast(arrival_msg, exclude={self.active_character})

        # 7. Change State to Playing
        self.state = ConnectionState.PLAYING
        log.info("Character %s entered game world in room %d.", self.active_character.name, room.dbid)

    async def _handle_playing(self):
        """Handles input when the player is fully in the game."""
        if not self.active_character: # Should not happen in this state
            log.error("Reached PLAYING state without active character for %s.", self.addr)
            self.state = ConnectionState.DISCONNECTED
            return
        
        # Main command loop
        await self._send("\r\n> ") # Send initial prompt
        line = await self._read_line()
        if line is None: return # Connection lost

        # Basic quit command handling here until Task 9
        if line.lower().strip() == "quit":
            log.info("Character %s initiated quit.", self.active_character.name)
            # Saving happens in the main handle() finally block
            self.state = ConnectionState.DISCONNECTED
            return
        # TODO: Pass line to Command Handler (Task 9)
        # Command_handler.process(self.active_character, line)
        await self.active_character.send(f"Command processing not implemented yet: '{line}'\r\n")

        # Loop back to read next command (stay in PLAYING state)

    async def handle(self):
        """Main handling loop driven by state machine."""
        log.debug("Handler starting for %s", self.addr)
        try:
            while self.state != ConnectionState.DISCONNECTED:
                if self.state == ConnectionState.GETTING_USERNAME:
                    await self._handle_get_username()
                elif self.state == ConnectionState.GETTING_PASSWORD:
                    await self._handle_get_password()
                elif self.state == ConnectionState.SELECTING_CHARACTER:
                    await self._handle_select_character()
                elif self.state == ConnectionState.PLAYING:
                    await self._handle_playing() # Will loop internally until state changes
                else:
                    log.error("Unhandled connection state %s for %s. Disconnecting.", self.state, self.addr)
                    self.state = ConnectionState.DISCONNECTED

                # Small sleep to prevent tight loop on error/staying in same state without read
                if self.state != ConnectionState.DISCONNECTED and self.state != ConnectionState.PLAYING:
                    await asyncio.sleep(0.1)
        except Exception as e:
            #Catch-all for unexpected errors in the handler logic
            log.exception("Unexpected error in Connectionhandler for %s:", self.addr, exc_info=True)
        finally:
            await self.cleanup()

    async def cleanup(self):
        """Perform cleanup when connection ends."""
        log.info("Cleaning up connection for %s.", self.addr)
        # Ensure state reflects disconnect
        self.state = ConnectionState.DISCONNECTED

        #Save character if one was active
        if self.active_character:
            char_to_clean = self.active_character
            char_name = char_to_clean.name # Get name before clearing reference
            char_id = char_to_clean.dbid

            log.debug("Cleanup: removing active character %s (%s)", char_name, char_id)
            # Remove from world tracking FIRST
            self.world.remove_active_character(char_id)
            self.active_character = None # Clear reference on handler
            # Remove from room and announce
            if char_to_clean.location:
                #Announce departure
                departure_msg = f"\r\n{char_name} slowly departs.\r\n"
                try:
                    # Use try block as broadcast could fail if room/other players have issues
                    char_to_clean.location.broadcast(departure_msg, exclude={char_to_clean})
                except Exception as e:
                    log.error("Error broadcasting departure for %s: %s", char_name, e)
                char_to_clean.location.remove_character(char_to_clean)

            log.info("Attempting final save for character %s (%s).", char_name, char_id)
            # pass the database connection stored in the handler
            await char_to_clean.save(self.db_conn)

        # Close network connection
        if self.writer and not self.writer.is_closing():
            try:
                self.writer.close()
                await self.writer.wait_closed()
                log.debug("Writer closed for %s", self.addr)
            except Exception as e:
                log.warning("Error closing writer for %s: %s", self.addr, e)
        log.info("Connection handler finished for %s.", self.addr)


