# server.py
"""
Main asynchronous server start script
"""

import logging
import os
import sys
import time
import asyncio
import aiosqlite
import config
from game import database
from game.world import World
from game.handlers.connection import ConnectionHandler
from game import ticker

# Configure basic logging
log_level = logging.DEBUG # Or load from config: getattr(config, 'LOG_LEVEL', logging.INFO)
log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(level=log_level, format=log_format)

log = logging.getLogger(__name__)

print(f"Root logger level after basicConfig: {logging.getLogger().getEffectiveLevel()}")
# --- Global World Instance ---
# This holds the loaded game state
world: World | None = None
# --- Global DB Connection (Optional - can pass to handler) ---
# Keep DB connection global for now for simplicity, or manage pool later
db_conn: aiosqlite.Connection | None = None

async def handle_connection(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """
    Coroutine called for each new client connection.
    (Will contain login/command handling logic later)
    """
    addr = writer.get_extra_info('peername', 'Unknown Address')
    log.info("Connection received from %s", addr)

    # --- V V V ADD DEBUG LOGS HERE V V V ---
    log.debug("HANDLER: Entry check - world object: %s (ID: %s)", world, id(world) if world else 'None')
    log.debug("HANDLER: Entry check - db_conn object: %s (ID: %s)", db_conn, id(db_conn) if db_conn else 'None')
    # --- ^ ^ ^ END DEBUG LOGS ^ ^ ^ ---


    if not world or not db_conn: # Safety check
        log.error("Server not fully initialized (world or db_conn missing). Refusing connection from %s.", addr)
        writer.close()
        await writer.wait_closed()
        return
    
    # Create a handler instance for this connection
    handler = ConnectionHandler(reader, writer, world, db_conn)
    # Run the handler's main loop
    await handler.handle()
    #Cleanup is handled within handler.cleanup() called by handle()'s finally block

async def main():
    """Main server entry point."""
    # Use global keyword to modify module-level variables
    global world, db_conn
    # Initialize task variable outside try block so finally can access it
    autosave_task = None
    # Initialize ticker task variable
    ticker_task_started = False
    # Ensure db_conn is also initialized for finally block safety
    db_conn = None # Start as None

    try: # Outer try to catch early failures and still attempt cleanup
        log.info("Starting Chronicles of Chrozal server...")

        # 1. Connect to Database
        db_conn = await database.connect_db(database.DATABASE_PATH)
        if not db_conn:
            log.critical("!!! Failed to connect to database. Server cannot start.")
            return # Stop server startup

        # 1b. Initialize Database Schema (Create tables IF they don't exist)
        log.info("Initializing database schema if needed...")
        await database.init_db(db_conn)
        log.info("Database initialization check complete.")

        # 2. Build World State
        world = World() # Assign to global world
        build_successful = await world.build(db_conn)
        if not build_successful:
            log.critical("!!! Failed to build world state from database. Server cannot start.")
            # No need to close db_conn here, finally block will handle it
            return # Stop server startup

        log.info("World loaded successfully.")

        # 3. Start Network Server and Autosave Task
        server = None # Define server variable outside inner try
        try:
            server_host = getattr(config, 'HOST', '0.0.0.0')
            server_port = getattr(config, 'PORT', 4000)

            log.info("MAIN: Configuration - HOST=%s, PORT=%s", server_host, server_port)

            # --- Start Autosave Task ---
            save_interval = getattr(config, 'AUTOSAVE_INTERVAL_SECONDS', 300) # Default 5 mins
            if save_interval > 0 and world and db_conn: # Check globals again just to be safe
                autosave_task = asyncio.create_task(_autosave_loop(world, db_conn, save_interval))
            else:
                log.warning("Autosave disabled (interval <= 0 or world/db missing)")
            # --- End Autosave Task ---

            ticker_interval = getattr(config, 'TICKER_INTERVAL_SECONDS', 1.0)
            await ticker.start_ticker(ticker_interval)
            ticker_task_started = True # Mark as started

            if world:
                ticker.subscribe(world.update_roundtimes)
                ticker.subscribe(world.update_mob_ai)
                ticker.subscribe(world.update_respawns)
                ticker.subscribe(world.update_xp_absorption)
                ticker.subscribe(world.update_death_timers)
                log.info("Subscribed world roundtime updates to ticker.")

            # --- Start Network Server ---
            server = await asyncio.start_server(
                handle_connection, server_host, server_port
            )
            addr = server.sockets[0].getsockname()
            log.info("Server listening on %s:%s", addr[0], addr[1])

            # Keep server running until interrupted
            async with server:
                await server.serve_forever()

        except OSError as e:
            log.critical("!!! Failed to start server on %s:%s - %s", server_host, server_port, e)
        except Exception as e:
            # Catch runtime errors from serve_forever or other setup
            log.exception("!!! An unexpected error occurred during server setup or runtime.", exc_info=True)

    # This outer finally block ensures cleanup happens even if DB connect/World build failed
    finally:
        # Graceful shutdown
        log.info("Shutting down server...")

        if ticker_task_started: # only stop if we attempted to start it
            log.info("Stopping game ticker...")
            if world: # Unsubscribe if world exists
                ticker.unsubscribe(world.update_roundtimes)
                ticker.unsubscribe(world.update_mob_ai) # <<< ADDED
                ticker.unsubscribe(world.update_respawns)
                ticker.unsubscribe(world.update_xp_absorption)
                ticker.unsubscribe(world.update_death_timers)
                log.info("Unsubscribed world updates from ticker.")
            await ticker.stop_ticker()
            log.info("Game ticker stopped.")

        # --- Cancel Autosave Task ---
        if autosave_task:
            log.info("Cancelling autosave task...")
            autosave_task.cancel()
            try:
                # Give task a moment to finish ongoing save if any, handle cancellation
                await asyncio.wait_for(autosave_task, timeout=5.0)
            except asyncio.CancelledError:
                log.info("Autosave task successfully cancelled.")
            except asyncio.TimeoutError:
                log.warning("Autosave task did not finish cancelling within timeout.")
            except Exception:
                log.exception("Exception during autosave task cancellation:", exc_info=True)
        # --- End Task Cancellation ---

        # Close DB Connection
        if db_conn:
            log.info("Closing database connection.")
            # Ensure db_conn is awaitable (it should be from aiosqlite)
            if asyncio.iscoroutinefunction(getattr(db_conn, 'close', None)) or isinstance(getattr(db_conn, 'close', None), asyncio.Future):
                await db_conn.close()
            else: # Fallback for safety, though aiosqlite conn should be awaitable
                try:
                    db_conn.close()
                except Exception as db_e:
                    log.error("Error during synchronous close fallback: %s", db_e)

            log.info("Database connection closed.")
        log.info("Server shutdown complete.")

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
