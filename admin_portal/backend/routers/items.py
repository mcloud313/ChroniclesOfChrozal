from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
import json
from ..database import db

router = APIRouter(prefix="/items", tags=["items"])

@router.get("/")
async def get_items():
    """Get all item templates."""
    query = """
    SELECT id, name, description, item_type, subtype, value, weight,
        stats, flags, equip_slot, damage, armor, consumable_effect,
        max_stack, created_at, updated_at
    FROM item_templates
    ORDER BY name
    """
    rows = await db.fetch_all(query)
    return [dict(row) for row in rows]

@router.get("/{item_id}")
async def get_item(item_id: int):
    """Get a specific item template"""
    query = """
    SELECT id, name, description, item_type, subtype, value, weight,
    stats, flags, equip_slot, damage, armor, consumable_effect, 
    max_stack, created_at, updated_at
    FROM item_templates
    WHERE id = $1
    """
    row = await db.fetch_one(query, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Item not found")
    return dict(row)

@router.post("/")
async def create_item(
    name: str,
    description: str = "An item.",
    item_type: str = "misc",
    subtype: str = None,
    value: int = 0,
    weight: float = 0.0,
    stats: Dict[str, Any] = {},
    flags: List[str] = [],
    equip_slot: str = None,
    damage: Dict[str, Any] = None,
    armor: Dict[str, Any] = None,
    consumable_effect: Dict[str, Any] = None,
    max_stack: int = 1
):
    """Create a new item template"""
    query = """
    INSER INTO item_templates (
    name, description, item_type, subtype, value, weight, stats, flags,
    equip_slot, damage, armor, consumable_effect, max_stack
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9, $10::jsonb, $11:jsonb, $12::jsonb, $13)
    RETURNING *
    """
    row = await db.fetch_one(
        query,
        name, description, item_type, subtype, value, weight,
        json.dumps(stats), json.dumps(flags), equip_slot,
        json.dumps(damage) if damage else None,
        json.dumps(armor) if armor else None,
        json.dumps(consumable_effect) if consumable_effect else None,
        max_stack
    )
    return dict(row)

@router.put("/{item_id}")
async def update_item(item_id: int, item_data: dict):
    """Update an existing item template"""
    current = await db.fetch_one("SELECT * FROM item_templates WHERE id = $1", item_id)
    if not current:
        raise HTTPException(status_code=404, detail="Item not found")
    
    allowed_fields = {
        'name', 'description', 'item_type', 'subtype', 'value', 'weight', 'stats',
        'flags', 'equip_slot', 'damage', 'armor', 'consumable_effect', 'max_stack'
    }
    updates = []
    params = [item_id]
    param_idx = 2

    for field, value in item_data.items():
        if field not in allowed_fields or value is None:
            continue

        if field in ['stats', 'flags', 'damage', 'armor', 'consumable_effect']:
            updates.append(f"{field} = ${param_idx}::jsonb")
            params.append(json.dumps(value))
        else:
            updates.append(f"{field} = ${param_idx}")
            params.append(value)
        param_idx += 1

    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields to update.")
    
    query = f"""
    UPDATE item_templates
    SET {', '.join(updates)}, updated_at = NOW()
    WHERE id = $1
    RETURNING *
    """

    row = await db.fetch_one(query, *params)
    return dict(row)

@router.delete("/{item_id}")
async def delete_item(item_id: int):
    """Delete an item template"""
    query = "DELETE FROM item_templates WHERE id = $1 RETURNING id"
    row = await db.fetch_one(query, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"message": f"Item {item_id} deleted successfully."}