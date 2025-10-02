from fastapi import ApiRouter, HTTPException
from ..database import db

router = APIRouter(prefix="/areas", tags=["areas"])

@router.get("/")
async def get_areas():
    """Get all areas"""
    query = "SELECT * FROM areas ORDER BY name"
    rows = await db.fetch_all(query)
    return [dict(row) for row in rows]

@router.get("/{area_id}")
async def get_area(area_id: int):
    """Get a specific area"""
    query = "SELECT * FROM areas where id = $1"
    row = await db.fetch_one(query, area_id)
    if not row:
        raise HTTPException(status_code=404, detail="Area not found")
    return dict(row)
