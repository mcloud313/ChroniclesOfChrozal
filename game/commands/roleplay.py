# game/commands/roleplay.py
"""
Roleplay and social interaction commands.
"""
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..character import Character
    from ..world import World

log = logging.getLogger(__name__)

async def cmd_me(character: 'Character', world: 'World', args_str: str) -> bool:
    """Custom emote: /me <action>"""
    if not args_str.strip():
        await character.send("Usage: /me <action>")
        await character.send("Example: /me scratches his head thoughtfully.")
        return True
    
    if not character.location:
        return True
    
    message = f"\r\n{character.name} {args_str.strip()}\r\n"
    await character.location.broadcast(message)
    return True

async def cmd_pose(character: 'Character', world: 'World', args_str: str) -> bool:
    """Sets a temporary pose shown in room descriptions."""
    if not args_str.strip():
        character.pose = None
        await character.send("You clear your pose.")
        return True
    
    character.pose = args_str.strip()
    await character.send(f"Your pose is now: {character.pose}")
    return True

async def cmd_whisper(character: 'Character', world: 'World', args_str: str) -> bool:
    """Whisper to a specific character: whisper <name> <message>"""
    if not character.location:
        return True
    
    parts = args_str.strip().split(maxsplit=1)
    if len(parts) < 2:
        await character.send("Usage: whisper <name> <message>")
        return True
    
    target_name, message = parts
    target = character.location.get_character_by_name(target_name)

    if not target:
        await character.send(f"You don't see {target_name} here.")
        return True
    
    if target == character:
        await character.send("You mutter to yourself quietly.")
        return True
    
    #Send to whisperer and target
    await character.send(f"You whisper to {target.name}, \"{message}\"")
    await target.send(f"{character.name} whispers to you, \"{message}\"")

    await character.location.broadcast(
        f"\r\n{character.name} whispers something to {target.name}.\r\n",
        exclude={character, target}
    )
    return True

async def cmd_wave(character: 'Character', world: 'World', args_str: str) -> bool:
    """Wave at someone or generally"""
    if not character.location:
        return True
    
    target_name = args_str.strip()
    if target_name:
        target = character.location.get_character_by_name(target_name)
        if target:
            await character.send(f"You wave at {target_name}.")
            await target.send(f"{character.name} waves at you.")
            await character.location.broadcast(
                f"\r\n{character.name} waves at {target.name}.\r\n",
                exclude={character, target}
            )
        else:
            await character.send(f"You don't see {target_name} here.")
    else:
        await character.location.broadcast(f"\r\n{character.name} waves.\r\n")
        return True
    
async def cmd_nod(character: 'Character', world: 'World', args_str: str) -> bool:
    """Nod in agreement."""
    if character.location:
        await character.location.broadcast(f"\r\n{character.name} nods.\r\n")
    return True

async def cmd_shake(character: 'Character', world: 'World', args_str: str) -> bool:
    """Shake your head."""
    if character.location:
        await character.location.broadcast(f"\r\n{character.name} shakes their head.\r\n")
    return True

async def cmd_salute(character: 'Character', world: 'World', args_str: str) -> bool:
    """Salute someone or generally."""
    if not character.location:
        return True
    
    target_name = args_str.strip()
    if target_name:
        target = character.location.get_character_by_name(target_name)
        if target:
            await character.send(f"You salute {target.name}.")
            await target.send(f"{character.name} salutes you.")
            await character.location.broadcast(
                f"\r\n{character.name} salutes {target.name}.\r\n",
                exclude={character, target}
            )
        else:
            await character.send(f"You don't see {target_name} here.")
    else:
        await character.location.broadcast(f"\r\n{character.name} salutes sharply.\r\n")
    return True

async def cmd_bow(character: 'Character', world: 'World', args_str: str) -> bool:
    """Bow respectfully."""
    if not character.location:
        return True
    
    target_name = args_str.strip()
    if target_name:
        target = character.location.get_character_by_name(target_name)
        if target:
            await character.send(f"You bow respectfully to {target.name}.")
            await target.send(f"{character.name} bows respectfully to you.")
            await character.location.broadcast(
                f"\r\n{character.name} bows respectfully to {target.name}.\r\n",
                exclude={character, target}
            )
        else:
            await character.send(f"You don't see {target_name} here.")
    else:
        await character.location.broadcast(f"\r\n{character.name} bows respectfully.\r\n")
    return True

async def cmd_laugh(character: 'Character', world: 'World', args_str: str) -> bool:
    """Laugh out loud."""
    if character.location:
        await character.location.broadcast(f"\r\n{character.name} laughs.\r\n")
    return True

async def cmd_chuckle(character: 'Character', world: 'World', args_str: str) -> bool:
    """Chuckle quietly."""
    if character.location:
        await character.location.broadcast(f"\r\n{character.name} chuckles.\r\n")
    return True

async def cmd_grin(character: 'Character', world: 'World', args_str: str) -> bool:
    """Grin widely."""
    if character.location:
        await character.location.broadcast(f"\r\n{character.name} grins widely.\r\n")
    return True

async def cmd_smile(character: 'Character', world: 'World', args_str: str) -> bool:
    """Smile."""
    if character.location:
        await character.location.broadcast(f"\r\n{character.name} smiles.\r\n")
    return True

async def cmd_frown(character: 'Character', world: 'World', args_str: str) -> bool:
    """Frown."""
    if character.location:
        await character.location.broadcast(f"\r\n{character.name} frowns.\r\n")
    return True

async def cmd_sigh(character: 'Character', world: 'World', args_str: str) -> bool:
    """Sigh deeply."""
    if character.location:
        await character.location.broadcast(f"\r\n{character.name} sighs deeply.\r\n")
    return True

async def cmd_shrug(character: 'Character', world: 'World', args_str: str) -> bool:
    """Shrug your shoulders."""
    if character.location:
        await character.location.broadcast(f"\r\n{character.name} shrugs.\r\n")
    return True

async def cmd_flex(character: 'Character', world: 'World', args_str: str) -> bool:
    """Flex your muscles."""
    if character.location:
        await character.location.broadcast(f"\r\n{character.name} flexes their muscles impressively.\r\n")
    return True

async def cmd_whistle(character: 'Character', world: 'World', args_str: str) -> bool:
    """Whistle a tune."""
    if character.location:
        await character.location.broadcast(f"\r\n{character.name} whistles a cheerful tune.\r\n")
    return True

async def cmd_yawn(character: 'Character', world: 'World', args_str: str) -> bool:
    """Yawn tiredly."""
    if character.location:
        await character.location.broadcast(f"\r\n{character.name} yawns tiredly.\r\n")
    return True

async def cmd_point(character: 'Character', world: 'World', args_str: str) -> bool:
    """Point at something or someone."""
    if not character.location:
        return True
    
    target_name = args_str.strip()
    if target_name:
        await character.location.broadcast(f"\r\n{character.name} points at {target_name}.\r\n")
    else:
        await character.location.broadcast(f"\r\n{character.name} points.\r\n")
    return True
