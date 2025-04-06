# server.py
"""
Main asynchronous server start script
"""
import asyncio
import logging
import os
import sys
import config
from game import database
from game.world import World

# Configure basic logging
log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# --- Global World Instance ---
# This holds the loaded game state
world: World | None = None

async def handle_connection(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """
    Coroutine called for each new client connection.
    (Will contain login/command handling logic later)
    """
    addr = writer.get_extra_info("peername")
    log.info("Connection received from %s", addr)

    # TODO: Implement Phase 1 Task 7 - Login/Character Selection Logic here
    #       - Prompt username/password
    #       - Authenticate against Player account
    #       - Load/Select Character
    #       - Instantiate Character object, pass writer
    #       - Place character in world
    #       - Enter main command loop

    writer.write(f"Welcome to Chronicles of Chrozal MUD! (Not implemented yet)\n\r".encode('utf-8'))
    await writer.drain()

    # Keep connection open briefly for testing startup, then close
    await asyncio.sleep(2)

    log.info("Closing connection from %s", addr)
    writer.close()
    await writer.wait_closed()

async def main():
    """Main server entry point."""
    global world # Allow modification of the global world instance

    log.info("Starting Chronicles of Chrozal server...")

    # 1. Connect to Database
    db_conn = await database.connect_db(database.DATABASE_PATH)
    if not db_conn:
        log.critical("!!! Failed to connect to database. Server cannot start.")
        return # Stop server startup

    # 2. Build World State
    world = World()
    build_successful = await world.build(db_conn)
    if not build_successful:
        log.critical("!!! Failed to build world state from database. Server cannot start.")
        await db_conn.close()
        return # stop server startup
    
    # Database connection might be closed after build if not needed continuously,
    # or kept open if needed for frequent dynamic lookups. For now, let's
    # assume we might need it later and keep it open, but pass 'world' around.
    # If keeping open, ensure it's closed gracefully on shutdown.

    log.info("World loaded successfully.")

    # 3. Start Network Server
    try:
        server_host = getattr(config, 'HOST', '0.0.0.0') # Listen on all interfaces default
        server_port = getattr(config, 'PORT', 4000) # Default MUD port

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
        log.exception("!!! An unexpected error occurred during server setup or runtime.", exc_info=True)
    finally:
        # Graceful shutdown
        log.info("Shutting down server...")
        if db_conn:
            log.info("Closing database connection.")
            await db_conn.close()
            log.info("Database connection closed.")
        log.info("Server shutdown complete.")

if __name__ == "__main__":
    # Ensure config is loaded if possible (for HOST/PORT)
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
