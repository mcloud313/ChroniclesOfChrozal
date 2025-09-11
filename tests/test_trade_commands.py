# tests/test_trade_commands.py
import unittest
from unittest.mock import MagicMock, AsyncMock
import sys
import os
import asyncio
import json

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from game.world import World
from game.room import Room
from game.character import Character
from game.item import Item
from game.commands import trade as trade_cmds

class TestTradeCommands(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        """Set up a mock world, character, and shop for testing."""
        self.mock_db_manager = AsyncMock()
        # Configure the return value for when an item instance is created
        self.mock_db_manager.create_item_instance.return_value = {
            'id': 'potion-uuid-1', 'template_id': 100, 'owner_char_id': 1
        }
        self.mock_db_manager.update_shop_stock = AsyncMock()

        mock_writer = MagicMock(spec=asyncio.StreamWriter)
        mock_writer.drain = AsyncMock()
        
        self.world = World(self.mock_db_manager)
        
        # Add a "healing potion" template to the world
        potion_stats = json.dumps({'value': 50})
        self.world.item_templates[100] = {'id': 100, 'name': 'a healing potion', 'type': 'POTION', 'stats': potion_stats}

        # Create a shop room with the SHOP flag
        shop_room_data = {'id': 10, 'area_id': 1, 'name': 'General Store', 'description': 'A store.', 'flags': ['SHOP']}
        self.shop_room = Room(shop_room_data)
        self.world.rooms[10] = self.shop_room

        # Create the shop's inventory and add it to the world's cache
        self.world.shop_inventories[10] = [{
            'id': 1,
            'room_id': 10,
            'item_template_id': 100,
            'stock_quantity': 5,
            'buy_price_modifier': 1.2, # 20% markup
            'sell_price_modifier': 0.8
        }]

        # Create a character with enough money to buy the potion
        char_data = {
            "id": 1, "player_id": 1, "first_name": "Buyer", "last_name": "Test", 
            "sex": "Male", "race_id": 1, "class_id": 1, "level": 1, "hp": 50.0, 
            "max_hp": 50.0, "essence": 50.0, "max_essence": 50.0, "stats": {}, 
            "skills": {}, "equipment": {}, "inventory": [], "status": "ALIVE", 
            "stance": "Standing", "coinage": 100, "location_id": 10,
            "xp_pool": 0, "xp_total": 0, "unspent_skill_points": 0, 
            "unspent_attribute_points": 0, "spiritual_tether": 1, "description": "", 
            "total_playtime_seconds": 0, "known_spells": [], "known_abilities": []
        }
        self.character = Character(mock_writer, char_data, self.world)
        self.character = Character(mock_writer, char_data, self.world)
        
        # Place the character in the shop
        self.character.update_location(self.shop_room)
        self.shop_room.add_character(self.character)

    async def test_buy_item_from_shop(self):
        """Verify a character can buy an item, their coinage decreases, and they receive the item."""
        initial_coinage = self.character.coinage
        initial_inv_count = len(self.character._inventory_items)
        
        # Potion base value is 50, markup is 1.2. Final price = 60
        expected_price = 60

        # --- Act ---
        await trade_cmds.cmd_buy(self.character, self.world, "potion")

        # --- Assert ---
        # 1. Check that money was subtracted correctly
        self.assertEqual(self.character.coinage, initial_coinage - expected_price)
        
        # 2. Check that the player received one new item
        self.assertEqual(len(self.character._inventory_items), initial_inv_count + 1)
        
        # 3. Check that the new item is the correct one
        new_item = list(self.character._inventory_items.values())[0]
        self.assertEqual(new_item.template_id, 100)
        self.assertEqual(new_item.id, 'potion-uuid-1')

        # 4. Check that the database was called to update stock
        self.mock_db_manager.update_shop_stock.assert_called_once_with(1, -1)