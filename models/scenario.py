from sqlalchemy import Integer, String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from core.database import Base


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    scenario_key: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)  # docker | vm
    path: Mapped[str] = mapped_column(String, nullable=False)  # relative path inside scenarios/

    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id"), nullable=True)