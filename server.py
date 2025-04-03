# server.py
import asyncio
import logging
import config

# Configure basic logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


async def handle_connection(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """
    Handles a single client connection.
    """
    addr = writer.get_extra_info("peername")
    logging.info(f"Connection established from {addr}")

    writer.write(
        "Welcome to Chronicles of Chrozal!\nPlease enter your name:\n".encode(
            config.ENCODING
        )
    )
    await writer.drain()
    # --- Placeholder for Login/Character Handling ---
    # For now, just read one line as the "name" and proceed
    try:
        name_data = await reader.readuntil(b"\n")
        name = name_data.decode(config.ENCODING).strip()
        if not name:  # Handle empty name entry
            name = f"Guest_{addr[1]}"  # Assign default guest name
        logging.info(f"{addr} identified as {name}")
        writer.write(f"Hello, {name}! Type 'quit to exit.\n> ".encode(config.ENCODING))
        await writer.drain()
        # --- End Placeholder ---

        while True:
            writer.write(b"> ")  # Simple prompt
            await writer.drain()

            try:
                data = await reader.readuntil(b"\n")
            except asyncio.IncompleteReadError:
                # Client disconnected abruptly without sending a full line ending with \n
                logging.info(
                    f"Client {addr} ({name}) discconected unexpectedly (incomplete read)."
                )
                break  # Exit the loop for this client

            if not data:
                # Usually indicates a clean disconnect from the client side after sending EOF
                logging.info(f"Client {addr} ({name}) sent EOF, disconnecting.")
                break  # Exit the loop

            message = data.decode(config.ENCODING).strip()
            logging.debug(f"Received from {name}: {message}")

            if not message:  # ignore empty lines
                continue

            if message.lower() == "quit":
                writer.write(b"Goodbye!\n")
                await writer.drain()
                logging.info(f"Client {addr} ({name}) requested quit.")
                break  # Exit the loop

            # --- Placeholder for Command Parsing ---
            # Echo back for now
            response = f"You said: {message}\n"
            writer.write(response.encode(config.ENCODING))
            await writer.drain()
            # --- End Placeholder ---

    except (ConnectionResetError, BrokenPipeError) as e:
        logging.warning(f"Connection error with {addr} ({name}): {e}")
    except Exception as e:
        logging.error(
            f"Unexpected error handling client {addr} ({name}): {e}", exc_info=True
        )  # Log full traceback
    finally:
        logging.info(f"Closing connection to {addr} ({name}).")
        # --- Placeholder for Player Saving ---
        # player.save() or similar would go here
        # --- End Placeholder ---
        writer.close()
        try:
            await writer.wait_closed()
        except Exception as e:
            logging.error(f"Error during writer close for {addr} ({name}): {e}")


async def main():
    """
    Main function to start the asyncio server
    """
    server = await asyncio.start_server(handle_connection, config.HOST, config.PORT)
    addr = server.sockets[0].getsockname()
    logging.info(f"Server started on {addr}")

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Server shutting down.")
