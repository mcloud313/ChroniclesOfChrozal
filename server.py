# server.py
"""
Main entry point for the Chronicles of Chrozal server.
Initializes the game world, starts the server, and handles graceful shutdown.
"""
import asyncio
import logging
import config
from typing import Optional
from game.database import db_manager # <-- Import the manager instance
from game.world import World
from game.handlers.connection import ConnectionHandler
from game import ticker

# --- Logging Setup ---
log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
log_handlers = [
    logging.FileHandler("server.log"),
    logging.StreamHandler()
]
logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    handlers=log_handlers
)
log = logging.getLogger(__name__)

# --- Global Game State ---
world: Optional[World] = None


async def handle_connection(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Coroutine called for each new client connection."""
    addr = writer.get_extra_info('peername', 'Unknown Address')
    log.info("Connection received from %s", addr)

    if not world:
        log.error("Server not fully initialized. Refusing connection from %s.", addr)
        writer.close(); await writer.wait_closed()
        return

    # Pass the global world object to the handler
    handler = ConnectionHandler(reader, writer, world, db_manager)
    await handler.handle()


async def _autosave_loop(world: World, interval_seconds: int):
    """Periodically saves the entire world state."""
    log.info("Autosave task started. Interval: %d seconds.", interval_seconds)
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            log.info("Autosave: Starting periodic world state save....")

            await world.save_state()

        except asyncio.CancelledError:
            log.info("Autosave task cancelled.")
            break
        except Exception:
            log.exception("Autosave: Unexpected error in autosave loop.")
            await asyncio.sleep(60)


async def main():
    """Main server entry point."""
    global world

    log.info("Starting Chronicles of Chrozal server...")

    # 1. Connect to the database and build the world
    await db_manager.connect()
    await db_manager.init_db()
    world = World(db_manager)
    if not await world.build():
        log.critical("!!! Failed to build world state. Server cannot start.")
        return
    world.subscribe_to_ticker()
    log.info("World loaded successfully.")

    # 2. Start the network server to listen for connections
    server = await asyncio.start_server(handle_connection, config.HOST, config.PORT)
    addr = server.sockets[0].getsockname()
    log.info(f"Server listening on {addr[0]}:{addr[1]}")

    # 3. Start background tasks AFTER the server is ready
    ticker_task = asyncio.create_task(ticker.start_ticker(config.TICKER_INTERVAL_SECONDS))
    autosave_task = None
    if config.AUTOSAVE_INTERVAL_SECONDS > 0:
        autosave_task = asyncio.create_task(_autosave_loop(world, config.AUTOSAVE_INTERVAL_SECONDS))

    # This block ensures graceful shutdown
    try:
        await server.serve_forever()
    except asyncio.CancelledError:
        log.info("Main server task cancelled.")
    finally:
        log.info("Shutting down server...")
        if ticker_task: ticker_task.cancel()
        if autosave_task: autosave_task.cancel()
        server.close()
        await server.wait_closed()
        if world:
            log.info("Performing final world state save...")
            await world.save_state()
        await db_manager.close()
        log.info("Server shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Server stopped manually.")