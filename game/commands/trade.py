#game/commands/trade.py
import logging
import json
from typing import TYPE_CHECKING
from .. import utils

if TYPE_CHECKING:
    from ..character import Character
    from ..world import World

log = logging.getLogger(__name__)

async def cmd_list(character: 'Character', world: 'World', args_str: str) -> bool:
    """Displays items for sale in the current room if it's a shop."""
    # 1. Check if the current room is a shop
    if "SHOP" not in character.location.flags:
        await character.send("This is not a shop.")
        return True
    
    # 2. Get the shop's inventory from the world cache
    inventory = world.get_shop_inventory(character.location.dbid)
    if not inventory:
        await character.send("This shop has nothing for sale.")
        return True
    
    # 3. Build the formatted output
    output = ["\n\r{c--- Items for Sale ---{x"]
    for shop_item in inventory:
        template = world.get_item_template(shop_item['item_template_id'])
        if not template:
            continue

        # Calculate the price
        try:
            stats = json.loads(template.get('stats', '{}') or '{}')
            base_value = stats.get('value', 0)
        except (json.JSONDecodeError, TypeError):
            base_value = 0

        price = int(base_value * shop_item['buy_price_modifier'])

        #Determine stock display
        stock = shop_item['stock_quantity']
        stock_display = f"(Stock: {stock})" if stock != -1 else "(Stock: Unlimited)"

        # Format the line
        price_str = f"[{utils.format_coinage(price):>10}]"
        output.append(f" {price_str} {template['name']} {stock_display}")

    output.append("{c----------------------{x")
    await character.send("\n\r".join(output))
    return True