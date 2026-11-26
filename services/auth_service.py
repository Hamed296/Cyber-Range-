from sqlalchemy.orm import Session
from sqlalchemy import select, text
from models.user import User
import secrets


class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def ensure_default_users(self):
        if not self.db.scalar(select(User).where(User.username == "admin")):
            self.db.add(User(username="admin", password="admin", role="admin"))
        if not self.db.scalar(select(User).where(User.username == "student")):
            self.db.add(User(username="student", password="student", role="student"))
        self.db.commit()

    def authenticate(self, username: str, password: str) -> User | None:
        user = self.db.scalar(select(User).where(User.username == username))
        if not user:
            return None
        if user.password != password:
            return None
        return user

    def _ensure_session_table(self):
        # ✅ SQLAlchemy 2.0 requires text(...)
        self.db.execute(text("""
            CREATE TABLE IF NOT EXISTS session_tokens (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL
            )
        """))
        self.db.commit()

    def create_session_token(self, user_id: int) -> str:
        self._ensure_session_table()
        token = secrets.token_urlsafe(32)
        self.db.execute(
            text("INSERT OR REPLACE INTO session_tokens (token, user_id) VALUES (:t, :u)"),
            {"t": token, "u": user_id},
        )
        self.db.commit()
        return token

    def get_user_by_session_token(self, token: str) -> User | None:
        self._ensure_session_table()
        row = self.db.execute(
            text("SELECT user_id FROM session_tokens WHERE token = :t"),
            {"t": token},
        ).fetchone()
        if not row:
            return None
        return self.db.get(User, int(row[0]))

    def delete_session_token(self, token: str):
        self._ensure_session_table()
        self.db.execute(text("DELETE FROM session_tokens WHERE token = :t"), {"t": token})
        self.db.commit()