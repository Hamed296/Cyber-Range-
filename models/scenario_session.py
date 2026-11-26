from sqlalchemy import Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from core.database import Base


class ScenarioSession(Base):
    __tablename__ = "scenario_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    scenario_id: Mapped[int] = mapped_column(Integer, ForeignKey("scenarios.id"), nullable=False)

    status: Mapped[str] = mapped_column(String, default="running", nullable=False)  # running | ended

    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # JSON string (ports/container names/urls/vm id...)
    runtime_data: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
