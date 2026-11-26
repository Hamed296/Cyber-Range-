from pydantic import BaseModel


class LabStepOut(BaseModel):
    id: int
    scenario_id: int
    step_order: int
    title: str
    description: str
    points: int
    answer_type: str
    placeholder: str
    hint: str
    is_required: bool

    class Config:
        from_attributes = True


class LabStepSubmit(BaseModel):
    step_id: int
    submitted_answer: str = ""