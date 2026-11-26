from sqlalchemy.orm import Session
from sqlalchemy import select
from models.scenario_session import ScenarioSession
from datetime import datetime
import json


class ScenarioSessionService:
    def __init__(self, db: Session):
        self.db = db



    def update_runtime_data(self, session_id: int, runtime_data: dict):
        sess = self.db.get(ScenarioSession, session_id)
        if not sess:
            raise ValueError("Session not found")
        sess.runtime_data = json.dumps(runtime_data, ensure_ascii=False)
        self.db.commit()
        self.db.refresh(sess)
        return sess

    def get_running_for_user(self, user_id: int) -> ScenarioSession | None:
        return self.db.scalar(
            select(ScenarioSession)
            .where(ScenarioSession.user_id == user_id, ScenarioSession.status == "running")
            .order_by(ScenarioSession.id.desc())
        )

    def is_scenario_running_for_user(self, user_id: int, scenario_id: int) -> bool:
        s = self.db.scalar(
            select(ScenarioSession).where(
                ScenarioSession.user_id == user_id,
                ScenarioSession.scenario_id == scenario_id,
                ScenarioSession.status == "running",
            )
        )
        return s is not None

    def create_running(self, user_id: int, scenario_id: int, runtime_data: dict) -> ScenarioSession:
        sess = ScenarioSession(
            user_id=user_id,
            scenario_id=scenario_id,
            status="running",
            runtime_data=json.dumps(runtime_data),
        )
        self.db.add(sess)
        self.db.commit()
        self.db.refresh(sess)
        return sess

    def end_session(self, session_id: int, runtime_data: dict | None = None) -> ScenarioSession | None:
        sess = self.db.get(ScenarioSession, session_id)
        if not sess:
            return None
        sess.status = "ended"
        sess.ended_at = datetime.utcnow()
        if runtime_data is not None:
            sess.runtime_data = json.dumps(runtime_data)
        self.db.commit()
        self.db.refresh(sess)
        return sess

    def parse_runtime_data(self, sess: ScenarioSession) -> dict:
        try:
            return json.loads(sess.runtime_data or "{}")
        except Exception:
            return {}
