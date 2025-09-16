# tests/test_movement.py
import unittest
from unittest.mock import Mock, AsyncMock, MagicMock
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from game.world import World
from game.room import Room
from game.character import Character
from game.commands import movement as move_cmds

class TestMovement(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Basic setup with a mock database and writer
        self.mock_db_manager = AsyncMock()
        mock_writer = MagicMock()
        mock_writer.drain = AsyncMock()
        
        # Create a world and two rooms
        self.world = World(self.mock_db_manager)
        self.start_room = Room({'id': 1, 'area_id': 1, 'name': 'Start Room', 'description': 'A room.'})
        self.end_room = Room({'id': 2, 'area_id': 1, 'name': 'End Room', 'description': 'Another room.'})
        self.world.rooms = {1: self.start_room, 2: self.end_room}

        # VERY IMPORTANT: Create the exit data as it would be loaded from the DB
        self.start_room.exits = {
            'north': {
                'id': 1,
                'source_room_id': 1,
                'direction': 'north',
                'destination_room_id': 2
            }
        }
        self.end_room.exits = {} # No exits from the end room

        # Create a character and place them in the start room
        char_data = {
        "id": 1, "player_id": 1, "first_name": "Mover", "last_name": "Test", 
        "sex": "Male", "race_id": 1, "class_id": 1, "level": 1, 
        "description": "A test character.", "hp": 50, "max_hp": 50,
        "essence": 20, "max_essence": 20, "xp_pool": 0, "xp_total": 0,
        "unspent_skill_points": 0, "unspent_attribute_points": 0,
        "spiritual_tether": 1, "coinage": 0, "location_id": 1,
        "total_playtime_seconds": 0, "status": "ALIVE", "stance": "Standing"
    }
        self.character = Character(mock_writer, char_data, self.world)
        self.character.location = self.start_room
        self.start_room.add_character(self.character)

    async def test_successful_move(self):
        """Tests that a character can move through a valid exit."""
        # Pre-condition: Character is in the start room
        self.assertEqual(self.character.location, self.start_room)
        self.assertIn(self.character, self.start_room.characters)
        self.assertNotIn(self.character, self.end_room.characters)

        # Action: Perform the move command
        await move_cmds.cmd_move(self.character, self.world, "north")

        # Post-condition: Character is now in the end room
        self.assertEqual(self.character.location, self.end_room)
        self.assertNotIn(self.character, self.start_room.characters)
        self.assertIn(self.character, self.end_room.characters)

    async def test_failed_move(self):
        """Tests that a character cannot move in a direction without an exit."""
        initial_location = self.character.location
        await move_cmds.cmd_move(self.character, self.world, "south")
        
        # Character should not have moved
        self.assertEqual(self.character.location, initial_location)