from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    password: Mapped[str] = mapped_column(String, nullable=False)  # NO hashing (per requirements)
    role: Mapped[str] = mapped_column(String, default="student", nullable=False)  # student | admin
