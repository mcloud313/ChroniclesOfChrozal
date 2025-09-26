# game/definitions/traits.py
"""
Defines options and defaults for character physical traits based on race.
Used during character creation by CreationHandler.
"""
import logging
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

# --- TRAIT OPTIONS PER RACE ---
# Keys are lowercase race names matching the 'name' column in the races table
TRAIT_OPTIONS: Dict[str, Dict[str, List[str]]] = {
    "chrozalin": {
        "Height": ["Very Short", "Short", "Slightly Short", "Average", "Slightly Tall", "Tall", "Notably Tall"],
        "Build": ["Frail", "Slender", "Lean", "Average", "Athletic", "Stocky", "Muscular", "Heavy"],
        "Skin Tone": ["Very Pale", "Pale", "Fair", "Light Tan", "Tanned", "Olive", "Ruddy", "Brown", "Dark Brown", "Black"],
        "Hair Style": ["Bald", "Clean-shaven Head", "Buzz-cut", "Short and Spiky", "Short and Tidy", "Bowl Cut", "Messy", "Shoulder-length", "Long Ponytail", "Intricate Braids", "Wild and Unkempt", "Long and Flowing"],
        "Hair Color": ["Black", "Jet Black", "Dark Brown", "Brown", "Chestnut", "Auburn", "Ginger", "Red", "Strawberry Blond", "Blond", "Dirty Blond", "Graying", "White"],
        "Eye Color": ["Dark Brown", "Brown", "Amber", "Hazel", "Green", "Deep Green", "Blue", "Pale Blue", "Gray", "Steel Gray"],
        "Nose Type": ["Aquiline", "Button", "Broad", "Narrow", "Hooked", "Straight", "Roman", "Upturned", "Slightly Crooked"],
        "Ear Shape": ["Average", "Large", "Small", "Slightly Pointed", "Round"],
        "Head Shape": ["Round", "Oval", "Square", "Square-jawed", "Heart-shaped", "Long"],
        "Beard Style": ["None", "Clean-shaven", "Stubble (5 o'clock shadow)", "Soul Patch", "Moustache", "Handlebar Moustache", "Goatee", "Van Dyke", "Chin Curtain", "Short Beard", "Full Beard", "Long Braided Beard", "Wizard Beard (Long)"]
    },
    "dwarf": {
        "Height": ["Stout", "Short", "Stocky", "Average (for a Dwarf)", "Surprisingly Tall (for a Dwarf)"],
        "Build": ["Stocky", "Broad", "Wiry", "Very Muscular", "Barrel-chested", "Solid", "Mountainous"],
        "Skin Tone": ["Ash-Gray", "Pale", "Ruddy", "Tanned", "Earth Brown", "Dark Stone", "Granite Gray"],
        "Hair Style": ["Bald", "Skullcap Fringe", "Tonsure", "Braided Mohawk", "Short Braids", "Long Single Braid", "Multiple Intricate Braids", "Long and Wild"],
        "Hair Color": ["Black", "Brown", "Deep Brown", "Red", "Fiery Red", "Gray", "Steel Gray", "White", "Stone Gray", "Salt and Pepper"],
        "Beard Style": ["None (Rare)", "Short Trimmed", "Mutton Chops", "Long Moustache", "Forked Beard", "Long Single Braid", "Two Braids", "Multiple Braids w/ Rings", "Square Cut Beard", "Flowing Epic Beard"],
        "Eye Color": ["Deep Brown", "Black", "Gray", "Steel Blue", "Dark Green", "Amber"],
        "Nose Type": ["Bulbous", "Broad", "Broken", "Strong Roman", "Button (Uncommon)"],
        "Ear Shape": ["Broad", "Round", "Slightly Pointed (Rare)"],
        "Head Shape": ["Blocky", "Round", "Square", "Wide"],
    },
    "elf": {
        "Height": ["Slightly Below Average", "Average", "Gracefully Tall", "Tall", "Very Tall", "Ethereally Tall"],
        "Build": ["Lithe", "Slender", "Willowy", "Lean", "Graceful", "Wiry", "Athletic"],
        "Skin Tone": ["Porcelain", "Ivory", "Fair", "Golden Hued", "Pale Silver", "Moonlit Silver", "Tanned", "Dusky", "Bronze"],
        "Hair Style": ["Long and Flowing", "Intricate Updo", "Single Long Braid", "Multiple Thin Braids", "Simple Ponytail", "Short and Neat", "High Half-ponytail", "Loose Waves", "Shoulder Length"],
        "Hair Color": ["Raven Black", "Midnight Blue", "Silver", "White", "Golden Blond", "Ash Blond", "Forest Green", "Deep Blue", "Copper", "Auburn", "Moonlit Silver"],
        "Eye Color": ["Deep Blue", "Sky Blue", "Emerald Green", "Forest Green", "Violet", "Amethyst", "Silver", "Gold", "Starry Black", "Amber"],
        "Nose Type": ["Delicate", "Straight", "Fine", "Slightly Upturned", "Aquiline"],
        "Ear Shape": ["Long and Pointed", "Swept-back Points", "High Pointed", "Downward Arcing Points", "Subtly Pointed", "Delicately Pointed"],
        "Head Shape": ["Oval", "Heart-shaped", "Angular", "Delicate"],
        "Beard Style": ["None", "Clean-shaven"], # Elves rarely have beards
    },
    "yan-tar": {
        "Height": ["Very Short", "Short", "Stocky Average", "Average", "Broad Average", "Surprisingly Large"],
        "Build": ["Stocky", "Solid", "Heavy", "Imposing", "Burly", "Rounded"],
        "Skin Pattern": ["Geometric", "Whorls", "Stripes", "Mottled", "Smooth", "Cracked Earth", "Scaled Patches", "Leathery"],
        "Shell Color": ["Dark Green", "Forest Green", "Brown", "Earthy Brown", "Gray-Black", "Charcoal", "Sandy", "Mossy Stone", "Patterned (multi-color)"],
        "Eye Color": ["Black", "Deep Brown", "Golden", "Amber", "Reptilian Slit (Gold)", "Reptilian Slit (Black)", "Reptilian Slit (Green)", "Milky White (Ancient)"],
        "Nose Type": ["Beak-like", "Snub", "Flat", "Ridged Beak", "Hooked Beak"],
        "Head Shape": ["Rotund", "Egg-Shaped", "Blocky", "Triangular", "Smooth-domed", "Slightly Ridged"],
        # No Hair/Ears/Beard categories
    },
    "grak": { # Corrected name from "grok"
        "Height": ["Tall", "Very Tall", "Towering", "Imposing", "Massive"],
        "Build" : ["Stocky", "Brawny", "Muscular", "Heavily Muscled", "Powerful", "Thickset", "Imposing"],
        "Skin Tone": ["Greyish", "Pale Grey", "Tanned Grey", "Stony Gray", "Slate Gray", "Ruddy Grey", "Mottled Grey-Brown"],
        "Head Shape": ["Blocky", "Square", "Heavy-Jawed", "Round", "Angular", "Rugged"],
        "Hair Style": ["None", "Bald", "Sparse Tufts", "Short and Bristly", "Coarse Topknot", "Matted Locks", "Shaved Sides", "Greasy Ponytail"],
        "Hair Color": ["Black", "Dark Brown", "Grey", "Salt and Pepper", "Charcoal", "Muddy Brown"],
        "Eye Color": ["Black", "Dark Brown", "Muddy Hazel", "Dull Green", "Bloodshot", "Fiery Orange (Rare)"],
        "Nose Type": ["Broad", "Flat", "Snub", "Pig-like Snout", "Broken"],
        "Ear Shape": ["Thick", "Rounded", "Slightly Pointed", "Torn/Notched", "Cauliflower"],
        "Tusk Style": ["None", "Small Underbite Tusks", "Medium Lower Tusks", "Prominent Tusks (Lower)", "Large Protruding Tusks", "Broken Tusk(s)"],
    },
    "kaiteen": {
        "Height": ["Slightly Short", "Lithe", "Average", "Gracefully Tall", "Tall"],
        "Build": ["Dainty", "Slender", "Lithe", "Wiry", "Sleek", "Muscular"],
        "Fur Pattern": ["Solid Color", "Tabby", "Spotted", "Marbled", "Ticked", "Colorpoint"],
        "Fur Color": ["Black", "Gray", "Brown", "Tawny", "Ginger", "White", "Silver", "Calico"],
        "Eye Color": ["Green", "Emerald", "Gold", "Amber", "Blue", "Peridot", "Copper"],
        "Ear Shape": ["Standard", "Tufted", "Rounded", "Tall and Pointed", "Folded"],
        "Tail Type": ["Long and Tufted", "Standard", "Fluffy", "Bobtail"],
        "Nose Type": ["Pink", "Black", "Speckled", "Brown"],
        "Head Shape": ["Round", "Wedge-shaped", "Square"],
    }
}

# --- DEFAULT TRAITS PER RACE ---
# Used if a player somehow skips a choice or for races missing categories
DEFAULT_TRAITS: Dict[str, Dict[str, str]] = {
    "chrozalin": { "Height": "Average", "Build": "Average", "Skin Tone": "Tanned", "Hair Style": "Short and tidy", "Hair Color": "Brown", "Eye Color": "Brown", "Nose Type": "Straight", "Ear Shape": "Average", "Head Shape": "Oval", "Beard Style": "None" },
    "dwarf": { "Height": "Short", "Build": "Stocky", "Skin Tone": "Ruddy", "Hair Style": "Long braided", "Hair Color": "Brown", "Beard Style": "Long single braid", "Eye Color": "Deep Brown", "Nose Type": "Broad", "Ear Shape": "Broad", "Head Shape": "Blocky" },
    "elf": { "Height": "Gracefully Tall", "Build": "Slender", "Skin Tone": "Fair", "Hair Style": "Long and flowing", "Hair Color": "Silver", "Eye Color": "Blue", "Nose Type": "Straight", "Ear Shape": "Long and Pointed", "Head Shape": "Oval", "Beard Style": "None" },
    "yan-tar": { "Height": "Average", "Build": "Solid", "Skin Pattern": "Smooth", "Shell Color": "Dark Green", "Eye Color": "Black", "Nose Type": "Beak-like", "Head Shape": "Rotund" },
    "grak": { "Height": "Towering", "Build": "Brawny", "Skin Tone": "Greyish", "Head Shape": "Blocky", "Hair Style": "Sparse Tufts", "Hair Color": "Black", "Eye Color": "Dark Brown", "Nose Type": "Flat", "Ear Shape": "Thick", "Tusk Style": "Small Underbite Tusks" },
    "kaiteen": { "Height": "Average", "Build": "Lithe", "Fur Pattern": "Tabby", "Fur Color": "Brown", "Eye Color": "Green", "Ear Shape": "Standard", "Tail Type": "Standard", "Nose Type": "Pink", "Head Shape": "Round" }
}

def get_trait_options(race_name: str) -> dict:
    """Returns the trait options dictionary for a given race name (case-insensitive)."""
    return TRAIT_OPTIONS.get(race_name.lower(), {})

def get_default_traits(race_name: str) -> dict:
    """Returns the default traits dictionary for a given race name (case-insensitive)."""
    return DEFAULT_TRAITS.get(race_name.lower(), {})
