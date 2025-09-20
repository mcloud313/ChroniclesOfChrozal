# game/definitions/item_defs.py
"""
Central definitions for item types and other item-related constants.
"""

# --- Item Type Constants ---
GENERAL = "GENERAL"
WEAPON = "WEAPON"
RANGED_WEAPON = "RANGED_WEAPON" # New
AMMO = "AMMO"                   # New
ARMOR = "ARMOR"
CONTAINER = "CONTAINER"
QUIVER = "QUIVER"               # New
QUEST = "QUEST"
FOOD = "FOOD"
DRINK = "DRINK"
KEY = "KEY"
LIGHT = "LIGHT"

# A list of tuples for use in Django model choices
ITEM_TYPE_CHOICES = [
    (GENERAL, "General"),
    (WEAPON, "Melee Weapon"),
    (RANGED_WEAPON, "Ranged Weapon"),
    (AMMO, "Ammunition"),
    (ARMOR, "Armor"),
    (CONTAINER, "Container"),
    (QUIVER, "Quiver"),
    (QUEST, "Quest Item"),
    (FOOD, "Food"),
    (DRINK, "Drink"),
    (KEY, "Key"),
    (LIGHT, "Light Source"),
]