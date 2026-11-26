from pydantic import BaseModel
from datetime import datetime


class StudentLabStepOut(BaseModel):
    id: int
    user_id: int
    session_id: int
    step_id: int
    submitted_answer: str
    is_correct: bool
    awarded_points: int
    submitted_at: datetime

    class Config:
        from_attributes = True