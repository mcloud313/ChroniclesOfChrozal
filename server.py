# server.py
"""
Main asynchronous server start script
"""
import asyncio
import aiosqlite
import logging
import os
import sys
import config
from game import database
from game.world import World
# --- V V V Import the new handler V V V ---
from game.handlers.connection import ConnectionHandler

# Configure basic logging
log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s"
)

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
    global world, db_conn # Allow modification of the global world instance

    log.info("Starting Chronicles of Chrozal server...")

    # 1. Connect to Database
    db_conn = await database.connect_db(database.DATABASE_PATH)
    if not db_conn:
        log.critical("!!! Failed to connect to database. Server cannot start.")
        return # Stop server startup

    # 2. Build World State
    # Assign to the global variable directly
    world = World()
    build_successful = await world.build(db_conn)
    if not build_successful:
        log.critical("!!! Failed to build world state from database. Server cannot start.")
        if db_conn: await db_conn.close() # Close DB if build fails
        return
    
    log.info("World loaded successfully.")

    # --- V V V ADD DEBUG LOGS HERE V V V ---
    log.debug("MAIN: Pre-start check - world object: %s (ID: %s)", world, id(world))
    log.debug("MAIN: Pre-start check - db_conn object: %s (ID: %s)", db_conn, id(db_conn))
    # --- ^ ^ ^ END DEBUG LOGS ^ ^ ^ ---

    # 3. Start Network Server
    sever = None # Define server variable outside try
    try:
        server_host = getattr(config, 'HOST', '0.0.0.0') # Listen on all interfaces default
        server_port = getattr(config, 'PORT', 4000) # Default MUD port

        log.info("MAIN: Configuration - HOST=%s, PORT=%s", server_host, server_port) # Log config being used

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
