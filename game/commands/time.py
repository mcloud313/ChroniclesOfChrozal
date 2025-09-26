# game/commands/time.py
"""
Implements the 'time' command for players.
"""
from game.character import Character
from game.world import World
from game.definitions import calendar as calendar_defs

def get_time_of_day(hour: int) -> str:
    """Returns a descriptive string for the time of day."""
    if 5 <= hour < 7: return "the crack of dawn"
    if 7 <= hour < 12: return "morning"
    if 12 <= hour < 14: return "mid-day"
    if 14 <= hour < 18: return "afternoon"
    if 18 <= hour < 21: return "evening"
    if 21 <= hour < 24: return "night"
    return "the dead of night"

async def cmd_time(character: Character, world: World, args_str: str) -> bool:
    """Displays the current in-game date and time."""
    
    # Calculate day of the week (0-indexed)
    # Total days elapsed in the year so far + current day - 1
    total_days_this_year = (world.game_month - 1) * calendar_defs.DAYS_PER_MONTH + (world.game_day - 1)
    day_of_week_index = total_days_this_year % calendar_defs.DAYS_PER_WEEK
    day_name = calendar_defs.DAY_NAMES[day_of_week_index]

    month_name = calendar_defs.MONTH_NAMES[world.game_month - 1]
    
    time_str = f"It is {get_time_of_day(world.game_hour)} on {day_name}, the {world.game_day}th of {month_name}, Year {world.game_year}."
    clock_str = f"The clock reads {world.game_hour:02d}:{world.game_minute:02d}."

    await character.send(time_str)
    await character.send(clock_str)
    return True