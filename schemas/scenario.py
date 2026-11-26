from pydantic import BaseModel
from typing import Optional


class ScenarioOut(BaseModel):
    id: int
    scenario_key: str
    name: str
    type: str
    path: str
    description: str = ""
    course_id: Optional[int] = None

    class Config:
        from_attributes = True