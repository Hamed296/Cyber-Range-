from sqlalchemy import Integer, String, Text, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from core.database import Base


class LabStep(Base):
    __tablename__ = "lab_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("scenarios.id"), nullable=False, index=True)

    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)

    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # info | text | flag
    answer_type: Mapped[str] = mapped_column(String, default="text", nullable=False)

    correct_answer: Mapped[str] = mapped_column(Text, default="", nullable=False)
    placeholder: Mapped[str] = mapped_column(String, default="", nullable=False)
    hint: Mapped[str] = mapped_column(Text, default="", nullable=False)

    is_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)