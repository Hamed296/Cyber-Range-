from sqlalchemy import Integer, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from core.database import Base


class StudentLabStep(Base):
    __tablename__ = "student_lab_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("scenario_sessions.id"), nullable=False, index=True)
    step_id: Mapped[int] = mapped_column(ForeignKey("lab_steps.id"), nullable=False, index=True)

    submitted_answer: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    awarded_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)