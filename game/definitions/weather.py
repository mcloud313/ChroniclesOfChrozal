# game/definitions/weather.py
"""
Defines climate types, weather conditions, and weather generation tables.
"""
from typing import Dict, List, Tuple

# --- Climate Flags (to be placed on Areas) ---
CLIMATE_TEMPERATE = "TEMPERATE"
CLIMATE_ARID = "ARID"
CLIMATE_TROPICAL = "TROPICAL"
CLIMATE_FRIGID = "FRIGID"

# --- Weather Condition Types ---
COND_CLEAR = "Clear"
COND_CLOUDY = "Cloudy"
COND_OVERCAST = "Overcast"
COND_LIGHT_RAIN = "Light Rain"
COND_HEAVY_RAIN = "Heavy Rain"
COND_THUNDERSTORM = "Thunderstorm"
COND_LIGHT_SNOW = "Light Snow"
COND_HEAVY_SNOW = "Heavy Snow"
COND_BLIZZARD = "Blizzard"
COND_FOGGY = "Foggy"
COND_HAZY = "Hazy"

# --- Weather Tables ---
# Maps Season -> Climate -> List of (Condition, Weight)
# Higher weights mean a higher chance of that weather occurring.
WEATHER_TABLES: Dict[str, Dict[str, List[Tuple[str, int]]]] = {
    "Spring": {
        CLIMATE_TEMPERATE: [
            (COND_CLEAR, 20), (COND_CLOUDY, 30), (COND_LIGHT_RAIN, 40),
            (COND_HEAVY_RAIN, 10), (COND_FOGGY, 15)
        ],
        CLIMATE_ARID: [(COND_CLEAR, 80), (COND_CLOUDY, 15), (COND_HAZY, 10)],
        # Add more climates for Spring
    },
    "Summer": {
        CLIMATE_TEMPERATE: [
            (COND_CLEAR, 50), (COND_CLOUDY, 30), (COND_LIGHT_RAIN, 10),
            (COND_THUNDERSTORM, 15)
        ],
        CLIMATE_ARID: [(COND_CLEAR, 90), (COND_HAZY, 20)],
        # Add more climates for Summer
    },
    "Autumn": {
        CLIMATE_TEMPERATE: [
            (COND_CLEAR, 25), (COND_CLOUDY, 35), (COND_OVERCAST, 25),
            (COND_LIGHT_RAIN, 30), (COND_FOGGY, 20)
        ],
        CLIMATE_ARID: [(COND_CLEAR, 70), (COND_CLOUDY, 20), (COND_HAZY, 15)],
        # Add more climates for Autumn
    },
    "Winter": {
        CLIMATE_TEMPERATE: [
            (COND_OVERCAST, 40), (COND_FOGGY, 20), (COND_LIGHT_SNOW, 30),
            (COND_HEAVY_SNOW, 10), (COND_BLIZZARD, 5), (COND_CLEAR, 10)
        ],
        CLIMATE_ARID: [(COND_CLEAR, 60), (COND_CLOUDY, 25), (COND_LIGHT_SNOW, 5)],
        # Add more climates for Winter
    },
}