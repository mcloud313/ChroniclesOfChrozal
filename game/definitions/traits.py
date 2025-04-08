# game/definitions/traits.py
"""
Defines options for character physical traits based on race.
Used during character creation.
"""

# Using lists of strings for simplicity. Could be lists of tuples (id, display_name) later.
# Keys are lowercase race names matching the 'name' column in the races table

TRAIT_OPTIONS = {
    "chrozalin": {
        "Height": ["Short", "Average", "Tall"],
        "Build": ["Slender", "Average", "Stocky", "Muscular"],
        "Hair Style": ["Bald", "Buzz-cut", "Short and tidy", "Shoulder-length", "Long ponytail", "Wild and unkempt"],
        "Hair Color": ["Black", "Brown", "Blond", "Red", "Graying", "White"],
        "Eye Color": ["Brown", "Blue", "Green", "Hazel", "Gray"],
        "Nose Type": ["Aquiline", "Button", "Broad", "Hooked"],
        "Skin Tone": ["Pale", "Ruddy", "Brown", "Dark", "Black"]
        "Facial Hair": ["Stubble", "Moustache", "Average beard", "Thick Beard", "Long Beard"]
    },
    "dwarf": {
        "Height": ["Very Short", "Short", "Average (for a Dwarf)"],
        "Build": ["Stocky", "Broad", "Very Muscular"],
        "Hair Style": ["Bald", "Skullcap", "Braided", "Long and wild"],
        "Hair Color": ["Black", "Brown", "Red", "Gray", "White"],
        "Beard Style": ["None", "Short trimmed", "Forked", "Long braided", "Flowing epic"], # Race specific
        "Eye Color": ["Brown", "Gray", "Steel Blue"],
        "Nose Type": ["Bulbous", "Broad", "Broken"],
        "Skin Tone": ["Ash-Gray", "Pale", "Tanned", "Dark"]
    },
    "elf": {
        "Height": ["Average", "Tall", "Very Tall"],
        "Build": ["Lithe", "Slender", "Willowy"],
        "Hair Style": ["Long and flowing", "Intricate braids", "Simple ponytail", "Short and neat"],
        "Hair Color": ["Black", "Silver", "Golden Blond", "White", "Forest Green"], # Race specific colors
        "Eye Color": ["Blue", "Green", "Violet", "Silver", "Gold"], # Race specific colors
        "Nose Type": ["Delicate", "Straight", "Pointed (subtly)"]
        "Ear Shape": ["Long", "Downward Arcing", "Upward Arcing"]
        "Skin tone": ["Golden Hued", "Pale", "Tanned", "Black"]
    },
    "yan-tar": {
        "Height": ["Short", "Average", "Stocky Average"],
        "Build": ["Stocky", "Solid", "Heavy"],
        "Skin Pattern": ["Geometric", "Whorls", "Stripes", "Mottled", "Smooth"], # Race specific
        "Shell Color": ["Dark Green", "Brown", "Gray-Black", "Sandy"], # Race specific
        "Eye Color": ["Black", "Deep Brown", "Golden", "Amber"],
        "Nose Type": ["Beak-like", "Snub", "Flat"], # More like snout/beak
        "Head Shape": ["Rotund", "Egg-Shaped", "Blocky"]
    }
}

def get_trait_options(race_name: str) -> dict:
    """Returns the trait options dictionary for a given race name (case-insensitive)."""
    return TRAIT_OPTIONS.get(race_name.lower(), {})

def get_default_traits(race_name: str) -> dict:
    """Returns the default trait selections for a given race name (case-insensitive)."""
    return DEFAULT_TRAITS.get(race_name.lower(), {})


