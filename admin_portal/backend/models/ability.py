from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any

class AbilityBase(BaseModel):
    internal_name: str
    name: str
    ability_type: str
    class_req: Optional[List[str]] = []
    level_req: int = 1
    cost: int = 0
    target_type: Optional[str] = None
    effect_type: Optional[str] = None
    effect_details: Optional[Dict[str, Any]] = {}
    cast_time: float = 0.0
    roundtime: float = 1.0
    messages: Optional[Dict[str, Any]] = {}
    description: Optional[str] = None

class AbilityCreate(AbilityBase):
    pass

class AbilityUpdate(AbilityBase):
    internal_name: Optional[str] = None
    name: Optional[str] = None
    ability_type: Optional[str] = None

class Ability(AbilityBase):
    id: int
    
    model_config = ConfigDict(from_attributes=True)