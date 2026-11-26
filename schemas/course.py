from pydantic import BaseModel


class CourseOut(BaseModel):
    id: int
    code: str
    name: str
    description: str = ""

    class Config:
        from_attributes = True