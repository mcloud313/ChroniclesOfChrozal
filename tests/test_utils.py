# tests/test_utils.py
import unittest
from unittest.mock import Mock
import sys
import os

# This adds the project's root directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from game import utils

class TestUtils(unittest.TestCase):
    """Test suite for functions in utils.py."""

    def test_calculate_modifier(self):
        """Tests that the calculate_modifier function returns correct values."""
        self.assertEqual(utils.calculate_modifier(10), 3)
        self.assertEqual(utils.calculate_modifier(15), 5)
        self.assertEqual(utils.calculate_modifier(9), 3)
        self.assertEqual(utils.calculate_modifier(1), 0)
        self.assertEqual(utils.calculate_modifier(0), -5)
        self.assertEqual(utils.calculate_modifier(-5), -5)

    def test_format_coinage(self):
        """Tests the coinage formatting function."""
        self.assertEqual(utils.format_coinage(0), "0 Talons")
        self.assertEqual(utils.format_coinage(5), "5 Talons")
        self.assertEqual(utils.format_coinage(1234), "1 Crown, 2 Orbs, 3 Shards, 4 Talons")
        self.assertEqual(utils.format_coinage(1020), "1 Crown, 2 Shards")
        self.assertEqual(utils.format_coinage(100), "1 Orb")

    def test_get_opposite_direction(self):
        """Tests that opposite directions are returned correctly."""
        self.assertEqual(utils.get_opposite_direction("north"), "south")
        self.assertEqual(utils.get_opposite_direction("s"), "n")
        self.assertEqual(utils.get_opposite_direction("ne"), "sw")
        self.assertIsNone(utils.get_opposite_direction("portal"))

    # --- NEW TESTS ---

    def test_generate_stat_set(self):
        """Tests that a generated set of stats is valid."""
        stats = utils.generate_stat_set()
        # Test that it returns the correct number of stats
        self.assertEqual(len(stats), 6)
        # Test that each stat is within the valid range (4d6 = 4 to 24)
        for stat in stats:
            self.assertGreaterEqual(stat, 4)
            self.assertLessEqual(stat, 24)

    def test_skill_check(self):
        """Tests the skill check logic for success and failure."""
        # Create a "mock" character. It's a fake object that pretends to be a
        # character just for this test.
        mock_character = Mock()

        # --- Test Success Case ---
        # We'll tell our mock character to always return a high skill value of 20.
        mock_character.get_skill_modifier.return_value = 20
        # A roll of 1-20 plus 20 skill will always beat a Difficulty Class (DC) of 10.
        result = utils.skill_check(mock_character, "climbing", dc=10)
        self.assertTrue(result['success'])

        # --- Test Failure Case ---
        # Now we'll tell our mock character to return a low skill value of 5.
        mock_character.get_skill_modifier.return_value = 5
        # A roll of 1-20 plus 5 skill can never beat a DC of 30.
        result = utils.skill_check(mock_character, "climbing", dc=30)
        self.assertFalse(result['success'])