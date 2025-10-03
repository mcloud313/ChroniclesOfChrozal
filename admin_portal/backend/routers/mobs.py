from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
import json
from ..database import db

router = APIRouter(prefix="/mobs", tags=["mobs"])

@router.get("/")
async def get_mobs():
    """Get all mob templates"""
    query = """
    SELECT id, name, description, mob_type, level, stats, resistances,
    max_hp, max_coinage, flags, respawn_delay_seconds, variance, movement_chance,
    created_at, updated_at
    FROM mob_templates
    ORDER BY name
    """
    rows = await db.fetch_all(query)
    return [dict(row) for row in rows]

@router.get("/{mob_id}")
async def get_mob(mob_id: int):
    """Get a specific mob template with attacks and loot"""
    #Get mob template
    mob_query = """
    SELECT id, name, description, mob_type, level, stats, resistances,
    max_hp, max_coinage, flags, respawn_delay_seconds, variance, movement_chance,
    created_at, updated_at
    FROM mob_templates
    WHERE id = $1
    """
    mob = await db.fetch_one(mob_query, mob_id)
    if not mob:
        raise HTTPException(status_code=404, detail="Mob not found")
    
    # Get Attacks
    attacks_query = """
    SELECT id, name, damage_base, damage_rng, speed, attack_Type, effect_details
    FROM mob_attacks
    WHERE mob_template_id = $1
    """
    attacks = await db.fetch_all(attacks_query, mob_id)

    #Get loot table
    loot_query = """
        SELECT ml.id, ml.item_template_id, ml.drop_chance, ml.min_quantity, ml.max_quantity,
            it.name as item_name
        FROM mob_loot_table ml
        JOIN item_templates it ON ml.item_template_id = it.id
        WHERE ml.mob_template_id = $1
    """
    loot = await db.fetch_all(loot_query, mob_id)

    result = dict(mob)
    result['attacks'] = [dict(row) for row in attacks]
    result['loot_table'] = [dict(row) for row in loot]
    
    return result

@router.post("/")
async def create_mob(
    name: str,
    description: str = "A creature.",
    mob_type: str = None,
    level: int = 1,
    stats: Dict[str, Any] = {},
    resistances: Dict [str, Any] = {},
    max_hp: int = 10,
    max_coinage: int = 0,
    flags: List[str] = [],
    respawn_delay_seconds: int = 300,
    variance: Dict[str, Any] = {},
    movement_chance: float = 0.0
):
    """Create a new mob template."""
    query = """
        INSERT INTO mob_templates (
        name, description, mob_type, level, stats, resistances,
        max_hp, max_coinage, flags, respawn_delay_seconds, variance, movement_chance
        )
        VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8, $9::jsonb, $10, $11::jsonb, $12)
        RETURNING *
        """
    row = await db.fetch_one(
            query, name, description, mob_type, level, 
            json.dumps(stats), json.dumps(resistances), 
            max_hp, max_coinage, json.dumps(flags),
            respawn_delay_seconds, json.dumps(variance), movement_chance
        )
    return dict(row)

@router.put("/{mob_id}")
async def update_mob(mob_id: int, mob_data: dict):
    """Update an existing mob template."""
    current = await db.fetch_one("SELECT * FROM mob_templates WHERE id = $1", mob_id)
    if not current:
        raise HTTPException(status_code=404, detail="Mob not found")

    allowed_fields = {
        'name', 'description', 'mob_type', 'level', 'stats' 'resistances',
        'max_hp', 'max_coinage', 'flags', 'respawn_delay_seconds', 'variance', 
        'movement_chance'
    }
    updates = []
    params = [mob_id]
    param_idx = 2

    for field, value in mob_data.items():
        if field not in allowed_fields or value is None:
            continue

        if field in ['stats', 'resistances', 'flags', 'variance']:
            updates.append(f"{field} = ${param_idx}::jsonb")
            params.append(json.dumps(value))
        else:
            updates.append(f"{field} = ${param_idx}")
            params.append(value)
        param_idx += 1

    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    
    query = f"""
    UPDATE mob_templates
    SET {', '.join(updates)}, updated at = NOW()
    WHERE id = $1
    RETURNING *
    """

    row = await db.fetch_one(query, *params)
    return dict(row)

@router.delete("/{mob_id}")
async def delete_mob(mob_id: int):
    """Delete a mob template"""
    query = "DELETE FROM mob_templates WHERE id = $1 RETURNING id"
    row = await db.fetch_one(query, mob_id)
    if not row:
        raise HTTPException(status_code=404, detail="Mob not found")
    return {"message": f"Mob {mob_id} deleted successfully"}

#Attack endpoints
@router.post("/{mob_id}/attacks")
async def add_attack(
    mob_id: int,
    name: str,
    damage_base: int = 1,
    damage_rng: int = 0,
    speed: float = 2.0,
    attack_type: str = "physical",
    effect_details: Dict[str, Any] = None
):
    """Add an attack to a mob template"""
    query = """
        INSERT INTO mob_attacks (mob_template_id, name, damage_base, damage_rng, speed, attack_type, effect_details)
        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
        RETURNING *
    """
    row = await db.fetch_one(
        query, mob_id, name, damage_base, damage_rng, speed, attack_type,
        json.dumps(effect_details) if effect_details else None
    )
    return dict(row)

@router.delete("/attacks/{attack_id}")
async def delete_attack(attack_id: int):
    """Delete a mob attack"""
    query = "DELETE FROM mob_attacks WHERE id = $1 RETURNING id"
    row = await db.fetch_one(query, attack_id)
    if not row:
        raise HTTPException(status_code=404, detail="Attack not found")
    return {"message": "Attack deleted"}