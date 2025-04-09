# game/definitions/traits.py
"""
Defines options for character physical traits based on race.
Used during character creation.
"""

# Using lists of strings for simplicity. Could be lists of tuples (id, display_name) later.
# Keys are lowercase race names matching the 'name' column in the races table

TRAIT_OPTIONS = {
    # Use 'human' key to match DB race name if you stored 'Human' not 'Chrozalin'
    # If you stored 'Chrozalin' in DB, use "chrozalin" key here. Assuming 'human'.
    "chrozalin": {
        "Height": ["Short", "Average", "Tall"],
        "Build": ["Slender", "Average", "Stocky", "Muscular"],
        "Skin Tone": ["Pale", "Fair", "Tanned", "Ruddy", "Brown", "Dark Brown", "Black"], # Added more
        "Hair Style": ["Bald", "Buzz-cut", "Short and tidy", "Messy", "Shoulder-length", "Long ponytail", "Braided", "Wild and unkempt"], # Added more
        "Hair Color": ["Black", "Brown", "Dark Brown", "Auburn", "Blond", "Red", "Graying", "White"], # Added more
        "Eye Color": ["Brown", "Blue", "Green", "Hazel", "Gray", "Amber"], # Added more
        "Nose Type": ["Aquiline", "Button", "Broad", "Hooked", "Straight", "Upturned"], # Added more
        "Ear Shape": ["Average", "Slightly Pointed", "Large", "Small"], # Added
        "Head Shape": ["Round", "Oval", "Square-jawed"], # Added
        "Beard Style": ["None", "Clean-shaven", "Stubble", "Moustache", "Goatee", "Short Beard", "Full Beard", "Long Beard"] # Added more, including None/Clean
    },
    "dwarf": {
        "Height": ["Very Short", "Short", "Average (for a Dwarf)"],
        "Build": ["Stocky", "Broad", "Very Muscular", "Barrel-chested"], # Added
        "Skin Tone": ["Ash-Gray", "Pale", "Ruddy", "Tanned", "Dark Stone"], # Added more
        "Hair Style": ["Bald", "Skullcap", "Tonsure", "Braided mohawk", "Long braided", "Long and wild"], # Added more
        "Hair Color": ["Black", "Brown", "Deep Brown", "Red", "Gray", "White", "Stone Gray"], # Added more
        "Beard Style": ["None", "Short trimmed", "Mutton Chops", "Forked", "Long single braid", "Multiple braids", "Flowing epic"], # Added more
        "Eye Color": ["Deep Brown", "Gray", "Steel Blue", "Black"], # Added more
        "Nose Type": ["Bulbous", "Broad", "Broken", "Strong Roman"], # Added more
        "Ear Shape": ["Broad", "Round", "Slightly Pointed (rare)"], # Added
        "Head Shape": ["Blocky", "Round", "Wide"], # Added
    },
    "elf": {
        "Height": ["Average", "Tall", "Very Tall", "Gracefully Tall"], # Added
        "Build": ["Lithe", "Slender", "Willowy", "Athletic"], # Added
        "Skin Tone": ["Porcelain", "Fair", "Golden Hued", "Pale Silver", "Tanned", "Dusky"], # Corrected key, added more
        "Hair Style": ["Long and flowing", "Intricate braids", "Simple ponytail", "Short and neat", "High half-ponytail", "Loose waves"], # Added more
        "Hair Color": ["Black", "Silver", "Golden Blond", "White", "Forest Green", "Deep Blue", "Auburn"], # Added more
        "Eye Color": ["Blue", "Green", "Violet", "Silver", "Gold", "Starry Black"], # Added more
        "Nose Type": ["Delicate", "Straight", "Slightly Upturned"], # Added more
        "Ear Shape": ["Long and Pointed", "Swept-back Points", "Downward Arcing Points", "Subtly Pointed"], # Added more options
        "Head Shape": ["Oval", "Heart-shaped", "Angular"], # Added
        # Elves typically don't have beards by default in many fantasies
        # "Beard Style": ["None"], # Optional: Add if Elven beards are possible
    },
    "yan-ter": {
        "Height": ["Short", "Average", "Stocky Average", "Broad Average"], # Added
        "Build": ["Stocky", "Solid", "Heavy", "Imposing"], # Added
        "Skin Pattern": ["Geometric", "Whorls", "Stripes", "Mottled", "Smooth", "Cracked Earth"], # Added more
        "Shell Color": ["Dark Green", "Forest Green", "Brown", "Gray-Black", "Sandy", "Mossy Stone"], # Added more
        "Eye Color": ["Black", "Deep Brown", "Golden", "Amber", "Reptilian Slit (Gold)", "Reptilian Slit (Black)"], # Added more
        "Nose Type": ["Beak-like", "Snub", "Flat", "Ridged Beak"], # Added more options
        "Head Shape": ["Rotund", "Egg-Shaped", "Blocky", "Triangular"], # Added
        # Yan-tar likely don't have hair/beards/ears in the same way
    }
}

# It's highly recommended to also define DEFAULT_TRAITS matching these options
# def get_trait_options(...): ... # Keep this function
# def get_default_traits(...): ... # Keep this function (and populate DEFAULT_TRAITS)

def get_trait_options(race_name: str) -> dict:
    """Returns the trait options dictionary for a given race name (case-insensitive)."""
    return TRAIT_OPTIONS.get(race_name.lower(), {})



