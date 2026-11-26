from sqlalchemy.orm import Session
from sqlalchemy import select
from models.scenario import Scenario
from core.config import settings
from pathlib import Path
import json


class ScenarioService:
    def __init__(self, db: Session):
        self.db = db

    def list_scenarios(self) -> list[Scenario]:
        return list(self.db.scalars(select(Scenario).order_by(Scenario.id)))

    def get_by_id(self, scenario_id: int) -> Scenario | None:
        return self.db.get(Scenario, scenario_id)

    def sync_from_filesystem(self) -> int:
        """
        scans scenarios/**/scenario.json and UPSERT into DB

        المطلوب داخل كل scenario.json على الأقل:
        {
          "scenario_key": "...",
          "name": "...",
          "type": "docker" | "vm"
        }

        الحقول الاختيارية:
        {
          "description": "..."
        }

        ملاحظة:
        - لا نعدل course_id هنا، لأنه سيُدار من لوحة الأدمن
        """
        base: Path = settings.scenarios_dir
        if not base.exists():
            return 0

        count = 0

        for scenario_json in base.rglob("scenario.json"):
            try:
                data = json.loads(scenario_json.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"Skipping invalid JSON: {scenario_json} -> {e}")
                continue

            scenario_key = data.get("scenario_key")
            name = data.get("name")
            s_type = data.get("type")
            description = data.get("description") or ""

            if not scenario_key or not name or not s_type:
                print(f"Skipping scenario with missing required fields: {scenario_json}")
                continue

            if s_type not in ("docker", "vm"):
                print(f"Skipping scenario with invalid type '{s_type}': {scenario_json}")
                continue

            rel_path = str(scenario_json.parent.relative_to(base)).replace("\\", "/")

            existing = self.db.scalar(
                select(Scenario).where(Scenario.scenario_key == scenario_key)
            )

            if existing:
                existing.name = name
                existing.type = s_type
                existing.path = rel_path
                existing.description = description
            else:
                self.db.add(
                    Scenario(
                        scenario_key=scenario_key,
                        name=name,
                        type=s_type,
                        path=rel_path,
                        description=description,
                        course_id=None,
                    )
                )

            count += 1

        self.db.commit()
        return count