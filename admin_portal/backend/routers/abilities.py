import json
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from ..database import db

router = APIRouter(prefix="/abilities", tags=["abilities"])

@router.get("/")
async def get_abilities():
    """Get all ability templates"""
    query = """
        SELECT id, internal_name, name, ability_type, class_req, level_req, cost,
               target_type, effect_type, effect_details, cast_time, roundtime, messages, description
        FROM ability_templates
        ORDER BY name
    """
    rows = await db.fetch_all(query)
    return [dict(row) for row in rows]

@router.get("/{ability_id}")
async def get_ability(ability_id: int):
    """Get a specific ability by ID"""
    query = """
        SELECT id, internal_name, name, ability_type, class_req, level_req, cost,
               target_type, effect_type, effect_details, cast_time, roundtime, messages, description
        FROM ability_templates
        WHERE id = $1
    """
    row = await db.fetch_one(query, ability_id)
    if not row:
        raise HTTPException(status_code=404, detail="Ability not found")
    return dict(row)

@router.post("/")
async def create_ability(
    internal_name: str,
    name: str,
    ability_type: str,
    class_req: List[str] = [],
    level_req: int = 1,
    cost: int = 0,
    target_type: str = None,
    effect_type: str = None,
    effect_details: Dict[str, Any] = {},
    cast_time: float = 0.0,
    roundtime: float = 1.0,
    messages: Dict[str, Any] = {},
    description: str = None
):
    """Create a new ability template"""
    query = """
        INSERT INTO ability_templates (
        internal_name, name, ability_type, class_req, level_req, cost,
        target_type, effect_type, effect_details, cast_time, roundtime, messages, description
        )
        VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9::jsonb, $10, $11, $12::jsonb, $13)
        RETURNING *
    """
    row = await db.fetch_one(
        query,
        internal_name, name, ability_type,
        json.dumps(class_req), level_req, cost,
        target_type, effect_type,
        json.dumps(effect_details),
        cast_time, roundtime,
        json.dumps(messages),
        description
    )
    return dict(row)
