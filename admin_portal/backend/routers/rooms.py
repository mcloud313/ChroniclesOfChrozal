from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any, Optional
import json
from ..database import db

router = APIRouter(prefix="/rooms", tags=["rooms"])

@router.get("/",)
async def get_rooms(skip: int = 0, limit: int = 100):
    """Get all rooms with pagination - returns raw JSON"""
    query = """
        SELECT id, area_id, name, description, spawners, flags, coinage, 
               created_at, updated_at, shop_buy_filter, shop_sell_modifier
        FROM rooms
        ORDER BY id
        LIMIT $1 OFFSET $2
    """
    rows = await db.fetch_all(query, limit, skip)
    # Return raw dicts without Pydantic validation
    return [dict(row) for row in rows]

@router.get("/{room_id}")
async def get_room(room_id: int):
    """Get a specific room by ID"""
    query = """
        SELECT id, area_id, name, description, spawners, flags, coinage,
               created_at, updated_at, shop_buy_filter, shop_sell_modifier
        FROM rooms
        WHERE id = $1
    """
    row = await db.fetch_one(query, room_id)
    if not row:
        raise HTTPException(status_code=404, detail="Room not found")
    return dict(row)

@router.get("/{room_id}/exits")
async def get_room_exits(room_id: int):
    """Get all exits from a specific room"""
    query = """
        SELECT id, source_room_id, direction, destination_room_id, is_hidden, details
        FROM exits
        WHERE source_room_id = $1
        ORDER BY direction
    """
    rows = await db.fetch_all(query, room_id)
    return [dict(row) for row in rows]

@router.delete("/{room_id}")
async def delete_room(room_id: int):
    """Delete a room"""
    query = "DELETE FROM rooms WHERE id = $1 RETURNING id"
    row = await db.fetch_one(query, room_id)
    if not row:
        raise HTTPException(status_code=404, detail="Room not found")
    return {"message": f"Room {room_id} deleted successfully"}

@router.post("/")
async def create_room(
    area_id: int,
    name: str,
    description: str = "You see nothing special.",
    spawners: Dict[str, Any] = {},
    flags: List[str] = [],
    coinage: int = 0
):
    """Create a new room."""
    query = """
        INSERT INTO rooms (area_id, name, description, spawners, flags, coinage)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id, area_id, name, description, spawners, flags, coinage, created_at, updated_at
    """
    row = await db.fetch_one(
        query,
        area_id,
        name,
        description,
        json.dumps(spawners),
        json.dumps(flags),
        coinage
    )
    return dict(row)

@router.put("/{room_id}")
async def update_room(
    room_id: int,
    area_id: int = None,
    name: str = None,
    description: str = None,
    spawners: Dict[str, Any] = None,
    flags: List[str] = None,
    coinage: int = None
):
    """Update an existing room - only updates provided fields"""
    # Get current room first
    current = await db.fetch_one("SELECT * FROM rooms WHERE id = $1", room_id)
    if not current:
        raise HTTPException(status_code=404, detail="room not found")
    
    #build update with only provided fields
    updates = []
    params = [room_id]
    param_idx = 2

    if area_id is not None:
        updates.append(f"area_id = ${param_idx}")
        params.append(area_id)
        param_idx += 1

    if name is not None:
        updates.append(f"name = ${param_idx}")
        params.append(name)
        param_idx += 1

    if description is not None:
        updates.append(f"description = ${param_idx}")
        params.append(description)
        param_idx += 1

    if spawners is not None:
        updates.append(f"spawners = ${param_idx}::jsonb")
        params.append(json.dumps(spawners))
        param_idx += 1

    if flags is not None:
        updates.append(f"flags = ${param_idx}::jsonb")
        params.append(json.dumps(flags))
        param_idx += 1

    if coinage is not None:
        updates.append(f"coinage = ${param_idx}")
        params.append(coinage)
        param_idx += 1

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update.")
    

    query = f"""
        UPDATE rooms
        SET {', '.join(updates)}, updated_at = NOW()
        WHERE id = $1
        RETURNING *
    """

    row = await db.fetch_one(query, *params)
    return dict(row)

@router.get("/{room_id}/exits")
async def get_room_exits(room_id: int):
    """Get all exits from a specific room."""
    query = """
        SELECT id, source_room_id, direction, destination_room_id, is_hidden, details
        FROM exits
        WHERE source_room_id = $1
        ORDER BY
            CASE direction
                WHEN 'north' THEN 1
                WHEN 'northeast' THEN 2
                WHEN 'east' THEN 3
                WHEN 'southeast' THEN 4
                WHEN 'south' THEN 5
                WHEN 'southwest' THEN 6
                WHEN 'west' THEN 7
                WHEN 'northwest' THEN 8
                WHEN 'up' THEN 9
                WHEN 'down' THEN 10
                ELSE 11
            END
    """
    rows = await db.fetch_all(query, room_id)
    return [dict(row) for row in rows]

@router.post("/{room_id}/exits")
async def create_exit(
    room_id: int,
    direction: str,
    destination_room_id: int,
    is_hidden: bool = False,
    details: Dict[str, Any] = {},
    create_reverse: bool = True
):
    """Create an exit from this room to another"""
    #Verify both rooms exist
    source_room = await db.fetch_one("SELECT id FROM rooms WHERe id = $1", room_id)
    dest_room = await db.fetch_one("SELECT id FROM rooms WHERE id = $1", destination_room_id)

    if not source_room or not dest_room:
        raise HTTPException(status_code=404, detail="One or both rooms not found")
    
    # Check if exit already exists
    existing = await db.fetch_one(
        "SELECT id FROM exits WHERE source_room_id = $1 AND direction = $2",
        room_id, direction
    )
    if existing:
        raise HTTPException(status_code=400, detail=f"Exit {direction} already exists from this room")
    
    #Create the exit
    query = """
        INSERT INTO exits (source_room_id, direction, destination_room_id, is_hidden, details)
        VALUES ($1, $2, $3, $4, $5::jsonb)
        RETURNING *
    """
    exit_row = await db.fetch_one(
        query, room_id, direction, destination_room_id, is_hidden, json.dumps(details)
    )

    # Create reverse exit if requested
    if create_reverse:
        reverse_dir = get_reverse_direction(direction)
        if reverse_dir:
            reverse_exists = await db.fetch_one(
                "SELECT id FROM exits WHERE source_room_id = $1 AND direction = $2",
                destination_room_id, reverse_dir
            )
            if not reverse_exists:
                await db.fetch_one(
                    query, destination_room_id, reverse_dir, room_id, is_hidden, json.dumps(details)
                )

    return dict(exit_row)

@router.delete("/exits/{exit_id}")
async def delete_exit(exit_id: int, delete_reverse: bool = False):
    """Delete an exit"""
    # Get exit details before deleting
    exit_data = await db.fetch_one("SELECT * FROM exits WHERE id = $1", exit_id)
    if not exit_data:
        raise HTTPException(status_code=404, detail="Exit not found")
    
    #Delete the exit
    await db.fetch_one("DELETE FROM exits WHERE id = $1", exit_id)

    #Optionally delete reverse exit
    if delete_reverse:
        reverse_dir = get_reverse_direction(exit_data['direction'])
        if reverse_dir:
            await db.fetch_one(
                "DELETE FROM exits WHERE source_room_id = $1 AND direction = $2 AND destination_room_id = $3",
                exit_data['destination_room_id'], reverse_dir, exit_data['source_room_id']
            )

        return {"message": "Exit deleted"}
    
def get_reverse_direction(direction: str) -> Optional[str]:
    """Returns the opposite direction for creating reverse exits"""
    opposites = {
        'north': 'south',
        'south': 'north',
        'east': 'west',
        'west': 'east',
        'northeast': 'southwest',
        'southwest': 'northeast',
        'northwest': 'southeast',
        'southeast': 'northwest',
        'up': 'down',
        'down': 'up'
    }
    return opposites.get(direction.lower())