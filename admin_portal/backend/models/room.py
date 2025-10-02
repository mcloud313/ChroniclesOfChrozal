from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime

class RoomBase(BaseModel):
    area_id: int
    name: str
    description: Optional[str] = "You see nothing special."
    spawners: Optional[Dict[str, Any]] = Field(default_factory=dict)
    flags: Optional[List[str]] = Field(default_factory=list)
    coinage: int = 0
    shop_buy_filter: Optional[Dict[str, Any]] = Field(default_factory=dict)  # Changed from List to Dict
    shop_sell_modifier: float = 0.5

class RoomCreate(RoomBase):
    pass

class RoomUpdate(RoomBase):
    area_id: Optional[int] = None
    name: Optional[str] = None

class Room(RoomBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class Exit(BaseModel):
    id: int
    source_room_id: int
    direction: str
    destination_room_id: int
    is_hidden: bool = False
    details: Optional[Dict[str, Any]] = Field(default_factory=dict)
    
    model_config = ConfigDict(from_attributes=True)