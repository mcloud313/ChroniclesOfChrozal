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
