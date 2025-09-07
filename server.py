# server.py
"""
Main entry point for the Chronicles of Chrozal server.
Initializes the game world, starts the server, and handles graceful shutdown.
"""
import asyncio
import logging
import config
import aiosqlite
from typing import Optional

from game import database
from game.world import World
from game.handlers.connection import ConnectionHandler
from game import ticker  # <-- FIX: Corrected the import statement
import time

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger(__name__)

# --- Global Game State ---
world: Optional[World] = None


async def handle_connection(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Coroutine called for each new client connection."""
    addr = writer.get_extra_info('peername', 'Unknown Address')
    log.info("Connection received from %s", addr)

    if not world or not world.db_conn:
        log.error("Server not fully initialized. Refusing connection from %s.", addr)
        writer.close()
        await writer.wait_closed()
        return

    # Pass the global world object and its database connection to the handler
    handler = ConnectionHandler(reader, writer, world, world.db_conn)
    await handler.handle()


async def _autosave_loop(world: World, db_conn: aiosqlite.Connection, interval_seconds: int):
    """Periodically saves all active characters."""
    log.info("Autosave task started. Interval: %d seconds.", interval_seconds)
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            log.info("Autosave: Starting periodic save...")
            
            active_chars = world.get_active_characters_list()
            if not active_chars:
                log.info("Autosave: No active characters to save.")
                continue

            count = 0
            start_time = time.monotonic()
            for character in active_chars:
                try:
                    await character.save(db_conn)
                    count += 1
                except Exception:
                    log.exception("Autosave: Error saving character %s (%d):",
                                  getattr(character, 'name', '?'), getattr(character, 'dbid', 0))
            
            duration = time.monotonic() - start_time
            log.info("Autosave: Finished saving %d characters in %.2f seconds.", count, duration)

        except asyncio.CancelledError:
            log.info("Autosave task cancelled.")
            break
        except Exception:
            log.exception("Autosave: Unexpected error in autosave loop:")
            await asyncio.sleep(60) # Wait a minute before retrying after a major error


async def main():
    """Main server entry point."""
    global world

    db_conn: Optional[aiosqlite.Connection] = None
    server: Optional[asyncio.AbstractServer] = None
    autosave_task: Optional[asyncio.Task] = None

    try:
        log.info("Starting Chronicles of Chrozal server...")

        # 1. Connect to and initialize the database
        db_conn = await database.connect_db(config.DB_NAME)
        if not db_conn:
            log.critical("!!! Failed to connect to database. Server cannot start.")
            return
        await database.init_db(db_conn)

        # 2. Create and build the world instance
        world = World(db_conn)
        if not await world.build():
            log.critical("!!! Failed to build world state. Server cannot start.")
            return
        log.info("World loaded successfully.")
        
        # 3. Start background tasks (Ticker, Autosave)
        await ticker.start_ticker(config.TICKER_INTERVAL_SECONDS)
        ticker.subscribe(world.update_roundtimes)
        ticker.subscribe(world.update_mob_ai)
        ticker.subscribe(world.update_respawns)
        ticker.subscribe(world.update_effects)
        ticker.subscribe(world.update_death_timers)
        ticker.subscribe(world.update_regen)
        ticker.subscribe(world.update_xp_absorption)
        
        if config.AUTOSAVE_INTERVAL_SECONDS > 0:
            autosave_task = asyncio.create_task(_autosave_loop(world, db_conn, config.AUTOSAVE_INTERVAL_SECONDS))

        # 4. Start the network server
        server = await asyncio.start_server(handle_connection, config.HOST, config.PORT)
        addr = server.sockets[0].getsockname()
        log.info(f"Server listening on {addr[0]}:{addr[1]}")

        async with server:
            await server.serve_forever()

    except Exception:
        log.exception("A critical error occurred in the main server function.")
    finally:
        log.info("Shutting down server...")
        if server:
            server.close()
            await server.wait_closed()
        if autosave_task:
            autosave_task.cancel()
        await ticker.stop_ticker()
        if world:
            # A final save for all players on shutdown
            log.info("Performing final save for all active characters...")
            for char in world.get_active_characters_list():
                await char.save(db_conn)
        if db_conn:
            await db_conn.close()
        log.info("Server shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Server stopped manually.")