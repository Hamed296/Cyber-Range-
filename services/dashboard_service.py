from sqlalchemy.orm import Session
from services.scenario_service import ScenarioService
from services.scenario_session_service import ScenarioSessionService


class DashboardService:
    def __init__(self, db: Session):
        self.db = db
        self.scenarios = ScenarioService(db)
        self.sessions = ScenarioSessionService(db)

    def student_dashboard(self, user):
        scenarios = self.scenarios.list_scenarios()
        running = self.sessions.get_running_for_user(user.id)
        return scenarios, running
