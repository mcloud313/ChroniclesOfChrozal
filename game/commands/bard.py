# game/commands/bard.py
"""
Commands specific to the Bard class.
"""
import logging
from typing import TYPE_CHECKING
from ..definitions import abilities as ability_defs

if TYPE_CHECKING:
    from ..world import World
    from ..character import Character

log = logging.getLogger(__name__)

async def cmd_sing(character: Character, world: 'World', args_str: str) -> bool:
    """Handles the 'sing <song_name>' command."""
    if not args_str:
        if character.active_song:
            await character.send(f"You are currently singing the '{character.active_song_name}'.")
        else:
            await character.send("Sing which song? (Or type 'sing stop' to cease singing).")
        return True

    song_input = args_str.strip().lower()

    # --- Stop Singing ---
    if song_input == "stop":
        if not character.active_song:
            await character.send("You are not currently singing.")
            return True

        song_data = world.abilities.get(character.active_song)
        if song_data:
            messages = song_data.get("messages", {})
            if msg_self := messages.get("stop_sing_self"):
                await character.send(msg_self)
            if msg_room := messages.get("stop_sing_room"):
                await character.location.broadcast(
                    f"\r\n{msg_room.format(caster_name=character.name)}\r\n",
                    exclude={character}
                )

        character.active_song = None
        character.active_song_name = None
        return True

    # --- Find and Start Singing a Song ---
    found_key: str | None = None
    for key, data in world.abilities.items():
        if data.get("type") == "SONG" and song_input in key:
            found_key = key
            break

    if not found_key:
        await character.send("You don't know a song by that name.")
        return True

    song_data = world.abilities.get(found_key)

    if not character.knows_ability(found_key):
        await character.send("You have not yet learned that song.")
        return True

    if character.essence < song_data.get("cost", 0):
        await character.send("You don't have enough essence to begin that song.")
        return True

    # Stop any current song before starting a new one
    if character.active_song:
        await cmd_sing(character, world, "stop")

    # Start the new song
    character.essence -= song_data.get("cost", 0)
    character.active_song = found_key
    character.active_song_name = song_data.get("name", "an unknown song")

    messages = song_data.get("messages", {})
    if msg_self := messages.get("start_sing_self"):
        await character.send(msg_self)
    if msg_room := messages.get("start_sing_room"):
        await character.location.broadcast(
            f"\r\n{msg_room.format(caster_name=character.name)}\r\n",
            exclude={character}
        )

    return True