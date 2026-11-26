from pydantic import BaseModel
from typing import List, Optional
from schemas.scenario import ScenarioOut
from schemas.scenario_session import ScenarioSessionOut


class StudentDashboardResponse(BaseModel):
    user: dict
    scenarios: List[ScenarioOut]
    running_session: Optional[ScenarioSessionOut] = None
