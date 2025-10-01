# game/commands/time.py
"""
Implements the 'time' command for players.
"""
import logging
from game.character import Character
from game.world import World
from game.definitions import calendar as calendar_defs

log = logging.getLogger(__name__)

def get_celestial_body_position(hour: int) -> str:
    """Returns a descriptive string for the sun or moons' position."""
    if 5 <= hour < 7: return "The sun hangs low on the eastern horizon."
    if 7 <= hour < 11: return "The sun climbs higher in the morning sky."
    if 11 <= hour < 14: return "The sun is high overhead."
    if 14 <= hour < 18: return "The sun begins its slow descent in the west."
    if 18 <= hour < 21: return "The sun dips below the western horizon, painting the sky in fiery colors."
    if 21 <= hour < 24: return "The twin moons of Chrozal cast a silvery glow across the land."
    return "The twin moons hang high in the sky, marking the dead of night."

def get_general_time_of_day(hour: int) -> str:
    """Returns a generic description of the time of day for indoor players."""
    if 5 <= hour < 12: return "morning"
    if 12 <= hour < 18: return "afternoon"
    if 18 <= hour < 21: return "evening"
    return "night"

async def cmd_time(character: Character, world: World, args_str: str) -> bool:
    """Displays the current in-game date and time with weather information."""
    from game.definitions import weather as weather_defs
    
    # Date calculation
    total_days_this_year = (world.game_month - 1) * calendar_defs.DAYS_PER_MONTH + (world.game_day - 1)
    day_of_week_index = total_days_this_year % calendar_defs.DAYS_PER_WEEK
    day_name = calendar_defs.DAY_NAMES[day_of_week_index]
    month_name = calendar_defs.MONTH_NAMES[world.game_month - 1]
    
    date_str = f"It is {day_name}, the {world.game_day}th day of the month of {month_name}, in the Year of the Drifting Star, {world.game_year}."
    
    await character.send(date_str)
    
    # Time of day display
    if character.location and "OUTDOORS" in character.location.flags:
        celestial_str = get_celestial_body_position(world.game_hour)
        await character.send(celestial_str)

        area_id = character.location.area_id
        log.info(f"TIME DEBUG: Checking weather for area {area_id}")
        log.info(f"TIME DEBUG: area_weather keys: {list(world.area_weather.keys())}")
        
        # Weather information for outdoor characters
        current_weather = world.area_weather.get(character.location.area_id)
        if current_weather:
            condition = current_weather.get('condition', 'CLEAR')
            weather_effect = weather_defs.WEATHER_EFFECTS.get(condition, {})
            description = weather_effect.get('description', 'The weather is unremarkable.')
            
            await character.send(f"{description}")
            
            # Show tactical effects if present
            room_flags = weather_effect.get('room_flags', [])
            if room_flags:
                flag_str = ", ".join(f"<y>{flag}<x>" for flag in room_flags)
                await character.send(f"<i>[Active conditions: {flag_str}]<x>")
    
    else:  # Character is indoors
        general_time_str = get_general_time_of_day(world.game_hour)
        await character.send(f"Judging by the light from outside, it is currently {general_time_str}.")
        
        # Show area weather even if indoors (you can hear/sense it)
        if character.location:
            current_weather = world.area_weather.get(character.location.area_id)
            if current_weather:
                condition = current_weather.get('condition', 'CLEAR')
                if condition != 'CLEAR':
                    await character.send(f"<i>You sense the weather outside is: {condition.lower()}.<x>")
    
    return True