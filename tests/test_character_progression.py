# tests/test_character_progression.py
import unittest
from unittest.mock import Mock
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from game.character import Character
from game.item import Item
import config

class TestCharacterProgression(unittest.TestCase):
    """Test suite for character leveling and advancement."""

    def setUp(self):
        """
        This special method runs before each test.
        It sets up a reusable character object for us to test with.
        """
        # We need to "mock" the objects that a Character needs to exist.
        # These are fake objects that will just pretend to be the real things.
        mock_writer = Mock()
        mock_world = Mock()

        # Create a dictionary of test data for a level 1 Warrior
        self.char_data = {
            "id": 1,
            "player_id": 1,
            "first_name": "Test",
            "last_name": "Warrior",
            "sex": "Male",
            "race_id": 1,
            "class_id": 1, # Warrior
            "level": 1,
            "hp": 60.0,
            "max_hp": 60.0,
            "essence": 30.0,
            "max_essence": 30.0,
            "xp_pool": 0.0,
            "xp_total": 0.0,
            "unspent_skill_points": 0,
            "unspent_attribute_points": 0,
            "spiritual_tether": 3,
            "description": "A test warrior.",
            "coinage": 100,
            "location_id": 1,
            "total_playtime_seconds": 0,
            "status": "ALIVE",
            "stance": "Standing",
            "stats": {"might": 15, "vitality": 15, "agility": 10, "intellect": 10, "aura": 10, "persona": 10},
            "skills": {},
            "inventory": [],
            "equipment": {},
            "known_spells": [],
            "known_abilities": []
        }
        
        self.character = Character(mock_writer, self.char_data, mock_world)

    def test_apply_level_up_gains(self):
        """Tests the direct level up gain calculation."""
        old_max_hp = self.character.max_hp
        old_max_essence = self.character.max_essence

        # The Warrior's HP die is a d10, and their vit_mod is +5
        # So the HP gain should be between (1+5) and (10+5), i.e., 6 and 15.
        hp_gain, essence_gain = self.character.apply_level_up_gains()

        self.assertGreaterEqual(hp_gain, 6)
        self.assertLessEqual(hp_gain, 15)
        self.assertEqual(self.character.max_hp, old_max_hp + hp_gain)
        self.assertEqual(self.character.max_essence, old_max_essence + essence_gain)

    def test_advance_command_logic(self):
        """Simulates the logic of the 'advance' command."""
        # Give the character enough XP to level up
        self.character.xp_total = config.XP_BASE # XP_BASE is the requirement for level 2

        # Simulate the command's actions
        self.character.level += 1
        self.character.unspent_skill_points += config.SKILL_POINTS_PER_LEVEL
        hp_gain, essence_gain = self.character.apply_level_up_gains()

        # Check the results
        self.assertEqual(self.character.level, 2)
        self.assertEqual(self.character.unspent_skill_points, 5)
        self.assertGreater(self.character.max_hp, self.char_data['max_hp'])

    def test_stat_bonuses_from_equipment(self):
        """Tests that stats are correctly modified by equipping and unequipping enchanted items."""
        # --- 1. Setup ---
        # Create mock templates (we only need a name)
        sword_template = {'name': 'a magical sword'}
        helmet_template = {'name': 'a magical helmet'}
        
        # Create magical item instances with bonuses in `instance_stats`
        sword_instance = Item(
            {'id': 'sword-enchanted-1', 'template_id': 999},
            sword_template
        )
        sword_instance.instance_stats = {"bonus_might": 5, "bonus_mar": 10}

        helmet_instance = Item(
            {'id': 'helmet-enchanted-1', 'template_id': 998},
            helmet_template
        )
        helmet_instance.instance_stats = {"bonus_might": 2}

        # --- 2. Baseline Check ---
        # Base stats: might=15 (mod 5), agility=10 (mod 3)
        # Base MAR = 5 + floor(3/2) = 6
        self.assertEqual(self.character.might_mod, 5)
        self.assertEqual(self.character.mar, 6)

        # --- 3. Equip Sword and Verify ---
        self.character._equipped_items['WIELD_MAIN'] = sword_instance
        
        # New might = 15 + 5 = 20. New mod = floor(20/3) = 6
        self.assertEqual(self.character.might_mod, 6)
        # New MAR = (new might_mod 6) + floor(3/2) + (bonus_mar 10) = 17
        self.assertEqual(self.character.mar, 17)

        # --- 4. Equip Helmet and Verify Stacking ---
        self.character._equipped_items['HEAD'] = helmet_instance

        # New might = 15 + 5 (sword) + 2 (helmet) = 22. New mod = floor(22/3) = 7
        self.assertEqual(self.character.might_mod, 7)
        # New MAR = (new might_mod 7) + floor(3/2) + (bonus_mar 10) = 18
        self.assertEqual(self.character.mar, 18)

        # --- 5. Unequip Sword and Verify ---
        del self.character._equipped_items['WIELD_MAIN']

        # Might = 15 + 2 (helmet) = 17. New mod = floor(17/3) = 5
        self.assertEqual(self.character.might_mod, 5)
        # MAR = (new might_mod 5) + floor(3/2) + (no bonus_mar) = 6
        self.assertEqual(self.character.mar, 6)