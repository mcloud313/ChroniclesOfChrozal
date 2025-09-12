# game/commands/rogue.py
import logging
from typing import TYPE_CHECKING
from .. import utils
from .. character import Character

if TYPE_CHECKING:
    from ..character import Character
    from ..world import World

log = logging.getLogger(__name__)

async def cmd_hide(character: 'Character', world: 'World', args_str: str) -> bool:
    """Attempts to hide from observers in the current room."""
    if character.is_fighting:
        await character.send("You can't hide while in combat!")
        return True
    if character.is_hidden:
        await character.send("You are already hidden.")
        return True

    # Your stealth is checked against every observer's perception
    stealth_mod = character.get_skill_modifier("stealth")
    observers = [c for c in character.location.characters if c != character] + \
                [m for m in character.location.mobs if m.is_alive()]

    spotted = False
    for observer in observers:
        # For mobs, we'll estimate their perception skill
        perception_mod = observer.get_skill_modifier("perception") if isinstance(observer, Character) \
            else observer.level * 3 # Mobs get a base perception

        # The observer's perception check is the DC for your stealth check
        if utils.skill_check(character, "stealth", dc=perception_mod)['success']:
            continue # You successfully hid from this observer
        else:
            spotted = True
            await character.send(f"You fail to hide from {observer.name}.")
            # Optional: await observer.send(f"You notice {character.name} trying to hide.")
            break # One spot is all it takes

    if not spotted:
        character.is_hidden = True
        await character.send("You slip into the shadows.")

    return True