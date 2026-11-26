from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Dict, Any


class ScenarioSessionOut(BaseModel):
    id: int
    user_id: int
    scenario_id: int
    status: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    runtime_data: Dict[str, Any]

    class Config:
        from_attributes = True