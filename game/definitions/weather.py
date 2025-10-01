# game/definitions/weather.py
"""
Weather system definitions including conditions, climates, and tactical effects.
"""

# Climate types for areas
CLIMATE_TEMPERATE = "temperate"
CLIMATE_TROPICAL = "tropical"
CLIMATE_ARID = "arid"
CLIMATE_ARCTIC = "arctic"
CLIMATE_COASTAL = "coastal"

#Season based weather tables (condition, weight)
WEATHER_TABLES = {
    "spring": {
        CLIMATE_TEMPERATE: [
            ("CLEAR", 40),
            ("RAIN", 25),
            ("FOGGY", 15),
            ("WINDY", 10),
            ("THUNDERSTORM", 10)
        ],
        CLIMATE_TROPICAL: [
            ("CLEAR", 30),
            ("RAIN", 30),
            ("HEAVY_RAIN", 20),
            ("THUNDERSTORM", 15),
            ("WINDY", 5)
        ],
        CLIMATE_ARID: [
            ("CLEAR", 60),
            ("WINDY", 20),
            ("SANDSTORM", 10),
            ("BLAZING", 10)
        ],
        CLIMATE_ARCTIC: [
            ("SNOWY", 40),
            ("WINDY", 30),
            ("CLEAR", 20),
            ("BLIZZARD", 10)
        ],
        CLIMATE_COASTAL: [
            ("CLEAR", 35),
            ("FOGGY", 25),
            ("RAIN", 20),
            ("WINDY", 20)
        ]
    },
    "summer": {
        CLIMATE_TEMPERATE: [
            ("CLEAR", 60),
            ("WINDY", 15),
            ("RAIN", 10),
            ("THUNDERSTORM", 10),
            ("BLAZING", 5)
        ],
        CLIMATE_TROPICAL: [
            ("HEAVY_RAIN", 30),
            ("THUNDERSTORM", 25),
            ("RAIN", 20),
            ("CLEAR", 15),
            ("BLAZING", 10)
        ],
        CLIMATE_ARID: [
            ("BLAZING", 50),
            ("CLEAR", 30),
            ("SANDSTORM", 15),
            ("WINDY", 5)
        ],
        CLIMATE_ARCTIC: [
            ("CLEAR", 60),
            ("WINDY", 25),
            ("SNOWY", 10),
            ("FOGGY", 5)
        ],
        CLIMATE_COASTAL: [
            ("CLEAR", 50),
            ("WINDY", 20),
            ("FOGGY", 15),
            ("RAIN", 15)
        ]
    },
    "fall": {
        CLIMATE_TEMPERATE: [
            ("CLEAR", 35),
            ("RAIN", 25),
            ("FOGGY", 20),
            ("WINDY", 15),
            ("THUNDERSTORM", 5)
        ],
        CLIMATE_TROPICAL: [
            ("RAIN", 35),
            ("HEAVY_RAIN", 25),
            ("CLEAR", 20),
            ("THUNDERSTORM", 15),
            ("WINDY", 5)
        ],
        CLIMATE_ARID: [
            ("CLEAR", 55),
            ("WINDY", 25),
            ("SANDSTORM", 15),
            ("BLAZING", 5)
        ],
        CLIMATE_ARCTIC: [
            ("SNOWY", 45),
            ("WINDY", 30),
            ("BLIZZARD", 15),
            ("CLEAR", 10)
        ],
        CLIMATE_COASTAL: [
            ("FOGGY", 30),
            ("RAIN", 25),
            ("WINDY", 25),
            ("CLEAR", 20)
        ]
    },
    "winter": {
        CLIMATE_TEMPERATE: [
            ("SNOWY", 30),
            ("FREEZING", 25),
            ("CLEAR", 20),
            ("FOGGY", 15),
            ("WINDY", 10)
        ],
        CLIMATE_TROPICAL: [
            ("RAIN", 40),
            ("CLEAR", 30),
            ("HEAVY_RAIN", 20),
            ("WINDY", 10)
        ],
        CLIMATE_ARID: [
            ("CLEAR", 60),
            ("WINDY", 20),
            ("FREEZING", 15),
            ("SANDSTORM", 5)
        ],
        CLIMATE_ARCTIC: [
            ("BLIZZARD", 40),
            ("SNOWY", 30),
            ("FREEZING", 20),
            ("WINDY", 10)
        ],
        CLIMATE_COASTAL: [
            ("FOGGY", 35),
            ("WINDY", 25),
            ("FREEZING", 20),
            ("RAIN", 15),
            ("CLEAR", 5)
        ]
    }
}

WEATHER_EFFECTS = {
    "CLEAR": {
        "description": "The sky is clear and the weather is pleasant.",
        "room_flags": [],
        "movement_penalty": 0.0,
        "visibility_penalty": 0
    },
    "RAIN": {
        "description": "Rain falls steadily from the sky.",
        "room_flags": ["WET"],
        "movement_penalty": 0.5,
        "visibility_penalty": -1
    },
    "HEAVY_RAIN": {
        "description": "Heavy rain pounds down, soaking everything.",
        "room_flags": ["WET"],
        "movement_penalty": 1.0,
        "visibility_penalty": -2
    },
    "THUNDERSTORM": {
        "description": "Thunder crashes as lightning splits the sky.",
        "room_flags": ["WET", "STORMY"],
        "movement_penalty": 1.5,
        "visibility_penalty": -3
    },
    "FOGGY": {
        "description": "Thick fog obscures your vision.",
        "room_flags": ["FOGGY"],
        "movement_penalty": 0.5,
        "visibility_penalty": -4
    },
    "WINDY": {
        "description": "Strong winds buffet you.",
        "room_flags": ["WINDY"],
        "movement_penalty": 0.5,
        "visibility_penalty": 0
    },
    "SNOWY": {
        "description": "Snow falls gently from the sky.",
        "room_flags": ["SNOWY", "WET"],
        "movement_penalty": 1.0,
        "visibility_penalty": -2
    },
    "BLIZZARD": {
        "description": "A howling blizzard blinds you with snow.",
        "room_flags": ["SNOWY", "WINDY", "FREEZING"],
        "movement_penalty": 2.0,
        "visibility_penalty": -6
    },
    "FREEZING": {
        "description": "The air is bitterly cold.",
        "room_flags": ["FREEZING"],
        "movement_penalty": 0.5,
        "visibility_penalty": 0
    },
    "BLAZING": {
        "description": "The sun beats down mercilessly.",
        "room_flags": ["BLAZING"],
        "movement_penalty": 1.0,
        "visibility_penalty": 0
    },
    "SANDSTORM": {
        "description": "Stinging sand whips through the air.",
        "room_flags": ["SANDSTORM", "WINDY"],
        "movement_penalty": 2.0,
        "visibility_penalty": -5
    }
}