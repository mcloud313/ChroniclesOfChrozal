# Fully Corrected main() function for server.py
# Ensure these imports are present at the top of server.py:
import asyncio
import logging
import os
import sys
import config # Make sure config is imported
import aiosqlite # Needed for type hint
from typing import Optional # Needed for type hints
from game import database
from game.world import World
from game.handlers.connection import ConnectionHandler
from game import ticker
import time # Needed for autosave loop

# --- Logging Setup (should be done once, early) ---
log_level = logging.INFO # Or getattr(config, 'LOG_LEVEL', logging.INFO)
log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(level=log_level, format=log_format)
print(f"Root logger level after basicConfig: {logging.getLogger().getEffectiveLevel()} ({logging.getLevelName(logging.getLogger().getEffectiveLevel())})") # Debug print
# --- End Logging Setup ---

log = logging.getLogger(__name__) # Logger for this file

# --- Global World Variable ---
# Define world at module level so handle_connection can potentially see it if needed
# (Though currently it gets passed to the handler instance)
world: Optional[World] = None

# --- Connection Handler Function ---
# Ensure this is defined correctly before main()
async def handle_connection(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """ Coroutine called for each new client connection. """
    global world, db_conn # Access globals defined/assigned in main
    addr = writer.get_extra_info('peername', 'Unknown Address')
    log.info("Connection received from %s", addr)

    # Initial check - ensure world and db_conn (from main's scope) are ready
    # NOTE: Accessing db_conn directly from main's scope like this isn't ideal.
    # It's better passed via world or explicitly to the handler if needed persistently.
    # Let's rely on the 'world' object having its internal db_conn.
    if not world or not world.db_conn: # Check world and its internal db_conn
        log.error("Server not fully initialized (world or world.db_conn missing). Refusing connection from %s.", addr)
        writer.close()
        await writer.wait_closed()
        return

    # Pass world and its db_conn to the handler
    handler = ConnectionHandler(reader, writer, world, world.db_conn)
    await handler.handle()

# --- Autosave Loop ---
# Ensure this is defined correctly before main()
async def _autosave_loop(world: World, db_conn: aiosqlite.Connection, interval_seconds: int):
    # ... (Implementation from response [185] - looks correct) ...
    pass # Replace with full implementation

# --- Main Function ---
async def main():
    """Main server entry point."""
    global world # Declare intent to modify module-level world

    # Initialize variables outside try block for finally clause access
    db_conn: Optional[aiosqlite.Connection] = None # Initialize as None
    autosave_task: Optional[asyncio.Task] = None
    ticker_task_started: bool = False
    server: Optional[asyncio.AbstractServer] = None

    try: # Outer try to catch early failures and ensure cleanup
        log.info("Starting Chronicles of Chrozal server...")

        # 1. Connect to Database (Assign to local variable)
        db_conn = await database.connect_db(database.DATABASE_PATH)
        if not db_conn:
            log.critical("!!! Failed to connect to database. Server cannot start.")
            return

        # 1b. Initialize Database Schema
        log.info("Initializing database schema if needed...")
        await database.init_db(db_conn) # init_db still needs the connection passed
        log.info("Database initialization check complete.")

        # 2. Create World Instance (Pass connection)
        # Assign to the *global* world variable AFTER it's created
        world = World(db_conn) # Pass db_conn to __init__

        # 2b. Build World State (Uses internal self.db_conn now)
        build_successful = await world.build() # <<< CORRECTED: Call build() without arguments
        if not build_successful:
            log.critical("!!! Failed to build world state from database. Server cannot start.")
            # Clear globals if build fails?
            world = None
            # db_conn will be closed in finally
            return

        log.info("World loaded successfully.")

        # 3. Start Network Server, Ticker, Autosave
        try:
            server_host = getattr(config, 'HOST', '0.0.0.0')
            server_port = getattr(config, 'PORT', 4000)
            log.info("MAIN: Configuration - HOST=%s, PORT=%s", server_host, server_port)

            # Start Autosave Task (passes local db_conn)
            save_interval = getattr(config, 'AUTOSAVE_INTERVAL_SECONDS', 300)
            if save_interval > 0 and world and db_conn:
                autosave_task = asyncio.create_task(_autosave_loop(world, db_conn, save_interval))
            else: log.warning("Autosave disabled...")

            # Start Game Ticker & Subscribe (world methods access world.db_conn)
            ticker_interval = getattr(config, 'TICKER_INTERVAL_SECONDS', 1.0)
            await ticker.start_ticker(ticker_interval)
            ticker_task_started = True
            if world:
                log.info("Subscribing world updates to ticker...")
                ticker.subscribe(world.update_roundtimes)
                ticker.subscribe(world.update_mob_ai)
                ticker.subscribe(world.update_respawns)
                ticker.subscribe(world.update_xp_absorption)
                ticker.subscribe(world.update_death_timers)
                ticker.subscribe(world.update_effects)

            # Start Network Server
            # Pass the handle_connection function defined above
            server = await asyncio.start_server(
                handle_connection, server_host, server_port
            )
            addr = server.sockets[0].getsockname()
            log.info("Server listening on %s:%s", addr[0], addr[1])

            # Keep server running
            async with server:
                await server.serve_forever()

        except OSError as e: log.critical(...)
        except Exception as e: log.exception(...)

    finally:
        # Graceful shutdown
        log.info("Shutting down server...")
        if ticker_task_started:
            log.info("Stopping game ticker...")
            if world: # Unsubscribe world methods
                ticker.unsubscribe(world.update_roundtimes)
                ticker.unsubscribe(world.update_mob_ai)
                ticker.unsubscribe(world.update_respawns)
                ticker.unsubscribe(world.update_xp_absorption)
                ticker.unsubscribe(world.update_death_timers)
                ticker.unsubscribe(world.update_effects)
                log.info("Unsubscribed world updates from ticker.")
            await ticker.stop_ticker()

        if autosave_task:
            log.info("Cancelling autosave task...")
            autosave_task.cancel()
            try: await asyncio.wait_for(autosave_task, timeout=5.0)
            except asyncio.CancelledError: log.info("Autosave task successfully cancelled.")
            except asyncio.TimeoutError: log.warning("Autosave task did not finish cancelling within timeout.")
            except Exception: log.exception(...)

        if db_conn: # Close DB using variable from main's scope
            log.info("Closing database connection.")
            try: await db_conn.close()
            except Exception as db_e: log.error("Error closing database connection: %s", db_e)
            log.info("Database connection closed.")
        else: log.info("No database connection to close.")

        log.info("Server shutdown complete.")


# --- if __name__ == "__main__": remains the same ---
if __name__ == "__main__":
    # ... (config loading check) ...
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Server stopped manually (KeyboardInterrupt).")

async def _autosave_loop(world: World, db_conn: aiosqlite.Connection, interval_seconds: int = 300):
    """Periodically saves all active characters."""
    log.info("Autosave task started. Interval: %d seconds.", interval_seconds)
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            log.info("Autosave: Starting periodic save...")
            active_chars = world.get_active_characters_list() # Get current list
            count = 0
            start_time = time.monotonic()
            for character in active_chars:
                try:
                    # Use try/except for each character's save
                    await character.save(db_conn)
                    count += 1
                except Exception:
                    # Log specific character save error but continue loop
                    log.exception("Autosave: Error saving character %s (%s):",
                                getattr(character, 'name', 'Unknown'),
                                getattr(character, 'dbid', 'Unknown'), exc_info=True)
            end_time = time.monotonic()
            duration = end_time - start_time
            log.info("Autosave: Finished saving %d characters in %.2f seconds.", count, duration)

        except asyncio.CancelledError:
            log.info("Autosave task cancelled.")
            break # Exit loop if cancelled
        except Exception:
            # Log unexpected errors in the autosave loop itself
            log.exception("Autosave: Unexpected error in autosave loop:", exc_info=True)
            # Optional: Add a short sleep before retrying after major loop error
            await asyncio.sleep(60)

if __name__ == "__main__":
    # Ensure config is loaded if possible (for HOST/PORT)
    # This block needs os and sys imported at the top
    if not config:
        current_script_path = os.path.abspath(__file__)
        # Assume server.py is in root, adjust if needed
        project_root = os.path.dirname(current_script_path)
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        try:
            import config
        except ModuleNotFoundError:
            log.warning("config.py not found. Using default HOST/PORT.")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Server stopped manually (KeyboardInterrupt).")
