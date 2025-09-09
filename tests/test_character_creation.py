# tests/test_character_creation.py
import unittest
from unittest.mock import Mock, patch, AsyncMock
import sys
import os
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from game.handlers.creation import CreationHandler
from game.player import Player

class TestCharacterCreation(unittest.IsolatedAsyncioTestCase):
    """Test suite for the full character creation flow."""

    async def test_full_dwarf_warrior_creation(self):
        """
        Tests the entire creation flow by simulating player input and
        verifying the final data that would be saved to the database.
        """
        # --- SETUP MOCKS ---
        mock_reader = AsyncMock()
        
        # FIX: Create a standard Mock and make ONLY the .drain() method async.
        # This perfectly mimics the real StreamWriter and will clear all warnings.
        mock_writer = Mock()
        mock_writer.get_extra_info.return_value = ('127.0.0.1', 12345)
        mock_writer.is_closing.return_value = False
        mock_writer.drain = AsyncMock()
        
        mock_db_manager = AsyncMock()
        mock_player = Player(id=1, username="test", email="t@t.com", hashed_password="...")
        mock_world = Mock()

        mock_db_manager.fetch_all.side_effect = [
            [{'id': 1, 'name': 'Chrozalin', 'description': '...'}, {'id': 2, 'name': 'Dwarf', 'description': '...'}],
            [{'id': 1, 'name': 'Warrior', 'description': '...'}, {'id': 2, 'name': 'Mage', 'description': '...'}]
        ]
        
        player_inputs = [
            b"Gimli\n", b"SonofGloin\n", b"m\n", b"2\n", b"1\n", b"keep\n",
            b"18\n", b"16\n", b"15\n", b"12\n", b"10\n", b"8\n",
            b"1\n", b"1\n", b"1\n", b"1\n", b"1\n", b"1\n", b"1\n", b"1\n", b"1\n", b"1\n",
        ]
        mock_reader.readuntil.side_effect = player_inputs
        
        with patch('game.utils.generate_stat_set') as mock_generate_stats:
            mock_generate_stats.return_value = [18, 16, 15, 12, 10, 8]
            handler = CreationHandler(mock_reader, mock_writer, mock_player, mock_world, mock_db_manager)
            await handler.handle()

        # --- VERIFY THE RESULTS ---
        mock_db_manager.create_character.assert_called_once()
        saved_data = mock_db_manager.create_character.call_args.kwargs
        
        self.assertEqual(saved_data['first_name'], "Gimli")
        self.assertEqual(saved_data['last_name'], "SonofGloin")
        self.assertEqual(saved_data['stats']['vitality'], 16 + 9)
        self.assertEqual(saved_data['max_hp'], 18)
        self.assertIn("You see Gimli SonofGloin", saved_data['description'])