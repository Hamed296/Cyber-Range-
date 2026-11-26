from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from pathlib import Path
import json
import shutil
import subprocess

import psutil

from core.config import settings
from core.dependencies import get_db, require_role
from services.scenario_service import ScenarioService
from services.runtime.factory import RuntimeFactory
from services.scenario_session_service import ScenarioSessionService

from models.scenario import Scenario
from models.scenario_session import ScenarioSession
from models.user import User
from models.course import Course
from models.lab_step import LabStep
from models.student_lab_step import StudentLabStep

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _run(cmd: list[str], allow_fail: bool = False) -> subprocess.CompletedProcess:
    p = subprocess.run(cmd, capture_output=True, text=True, shell=False)
    if p.returncode != 0 and not allow_fail:
        raise RuntimeError(
            f"Command failed (code={p.returncode}):\n{' '.join(cmd)}\nSTDOUT:\n{p.stdout}\nSTDERR:\n{p.stderr}"
        )
    return p


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _get_running_vmx_paths() -> set[str]:
    try:
        p = _run([settings.vmrun_path, "list"], allow_fail=True)
        lines = [x.strip() for x in (p.stdout or "").splitlines() if x.strip()]
        return set(lines[1:]) if len(lines) > 1 else set()
    except Exception:
        return set()


def _build_session_map(db: Session):
    running_sessions = list(
        db.scalars(select(ScenarioSession).where(ScenarioSession.status == "running"))
    )

    session_map = {}
    svc = ScenarioSessionService(db)

    for sess in running_sessions:
        rd = svc.parse_runtime_data(sess) or {}
        machines = rd.get("machines") or []

        if machines:
            for m in machines:
                vmx = m.get("vmx_path")
                if vmx:
                    session_map[vmx] = {
                        "session_id": sess.id,
                        "user_id": sess.user_id,
                        "scenario_id": sess.scenario_id,
                    }
        else:
            vmx = rd.get("vmx_path")
            if vmx:
                session_map[vmx] = {
                    "session_id": sess.id,
                    "user_id": sess.user_id,
                    "scenario_id": sess.scenario_id,
                }

    return session_map


# =================================================
# Dashboard / Overview
# =================================================

@router.get("/overview")
def admin_overview(db: Session = Depends(get_db), user=Depends(require_role("admin"))):
    running_sessions = list(
        db.scalars(
            select(ScenarioSession)
            .where(ScenarioSession.status == "running")
            .order_by(ScenarioSession.id.desc())
        )
    )

    active_users = []
    for sess in running_sessions:
        student = db.get(User, sess.user_id)
        scenario = db.get(Scenario, sess.scenario_id)
        active_users.append({
            "session_id": sess.id,
            "user_id": sess.user_id,
            "username": student.username if student else None,
            "scenario_id": sess.scenario_id,
            "scenario_name": scenario.name if scenario else None,
            "started_at": sess.started_at,
            "ended_at": sess.ended_at,
            "status": sess.status,
        })

    running_vmx = sorted(list(_get_running_vmx_paths()))

    all_sessions = list(db.scalars(select(ScenarioSession).order_by(ScenarioSession.id.desc())))
    sessions_table = []

    for sess in all_sessions:
        student = db.get(User, sess.user_id)
        scenario = db.get(Scenario, sess.scenario_id)
        sessions_table.append({
            "id": sess.id,
            "user_id": sess.user_id,
            "username": student.username if student else None,
            "scenario_id": sess.scenario_id,
            "scenario_name": scenario.name if scenario else None,
            "status": sess.status,
            "started_at": sess.started_at,
            "ended_at": sess.ended_at,
        })

    return {
        "active_users_count": len(active_users),
        "active_users": active_users,
        "running_vms_count": len(running_vmx),
        "running_vms": running_vmx,
        "sessions": sessions_table,
    }


# =================================================
# Scenarios
# =================================================

@router.post("/sync-scenarios")
def sync_scenarios(db: Session = Depends(get_db), user=Depends(require_role("admin"))):
    count = ScenarioService(db).sync_from_filesystem()
    return {"synced": count}


@router.get("/scenarios")
def list_scenarios(db: Session = Depends(get_db), user=Depends(require_role("admin"))):
    scenarios = list(db.scalars(select(Scenario).order_by(Scenario.id)))
    out = []

    for s in scenarios:
        course = db.get(Course, s.course_id) if s.course_id else None
        out.append({
            "id": s.id,
            "scenario_key": s.scenario_key,
            "name": s.name,
            "type": s.type,
            "path": s.path,
            "description": s.description,
            "course_id": s.course_id,
            "course_name": course.name if course else None,
        })

    return out


@router.post("/create-scenario-vm")
async def create_scenario_vm(
    scenario_key: str = Form(...),
    name: str = Form(...),
    description: str = Form(""),
    clone_type: str = Form("linked"),
    entry_machine: str = Form(...),
    machines_json: str = Form(...),
    db: Session = Depends(get_db),
    user=Depends(require_role("admin")),
):
    scenario_key = scenario_key.strip()
    name = name.strip()
    description = description.strip()
    clone_type = clone_type.strip().lower()

    if not scenario_key or not name:
        raise HTTPException(status_code=400, detail="scenario_key and name are required")

    if clone_type not in ("linked", "full"):
        raise HTTPException(status_code=400, detail="clone_type must be linked or full")

    existing = db.scalar(select(Scenario).where(Scenario.scenario_key == scenario_key))
    if existing:
        raise HTTPException(status_code=400, detail="scenario_key already exists")

    scenario_dir = Path(settings.scenarios_dir) / "vm" / scenario_key
    if scenario_dir.exists():
        raise HTTPException(status_code=400, detail="Scenario directory already exists")

    try:
        machines = json.loads(machines_json)
    except Exception:
        raise HTTPException(status_code=400, detail="machines_json is invalid JSON")

    if not isinstance(machines, list) or not machines:
        raise HTTPException(status_code=400, detail="At least one machine is required")

    normalized_machines = []
    machine_names = set()

    for idx, m in enumerate(machines, start=1):
        machine_name = str(m.get("name") or "").strip()
        template_vmx = str(m.get("template_vmx") or "").strip()
        access = str(m.get("access") or "internal").strip().lower()
        username = str(m.get("username") or "").strip()
        password = str(m.get("password") or "").strip()
        nic_index = _safe_int(m.get("nic_index"), 0)

        if not machine_name:
            raise HTTPException(status_code=400, detail=f"Machine #{idx}: name is required")
        if machine_name in machine_names:
            raise HTTPException(status_code=400, detail=f"Duplicate machine name: {machine_name}")
        machine_names.add(machine_name)

        if not template_vmx:
            raise HTTPException(status_code=400, detail=f"Machine '{machine_name}': template_vmx is required")
        if access not in ("rdp", "ssh", "internal"):
            raise HTTPException(status_code=400, detail=f"Machine '{machine_name}': invalid access type")

        machine_data = {
            "name": machine_name,
            "template_vmx": template_vmx,
            "access": access,
            "nic_index": nic_index,
        }

        if username:
            machine_data["username"] = username
        if password:
            machine_data["password"] = password

        normalized_machines.append(machine_data)

    if entry_machine not in machine_names:
        raise HTTPException(status_code=400, detail="entry_machine must match one of the machine names")

    scenario_dir.mkdir(parents=True, exist_ok=False)

    data = {
        "scenario_key": scenario_key,
        "name": name,
        "description": description,
        "type": "vm",
        "vmware": {
            "clone_type": clone_type,
            "entry_machine": entry_machine,
            "machines": normalized_machines,
        }
    }

    try:
        scenario_json = scenario_dir / "scenario.json"
        scenario_json.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        count = ScenarioService(db).sync_from_filesystem()
        return {
            "ok": True,
            "synced": count,
            "path": f"vm/{scenario_key}"
        }
    except Exception as e:
        shutil.rmtree(scenario_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create-scenario-docker")
async def create_scenario_docker(
    scenario_key: str = Form(...),
    name: str = Form(...),
    description: str = Form(""),
    docker_compose_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(require_role("admin")),
):
    scenario_key = scenario_key.strip()
    name = name.strip()
    description = description.strip()

    if not scenario_key or not name:
        raise HTTPException(status_code=400, detail="scenario_key and name are required")

    existing = db.scalar(select(Scenario).where(Scenario.scenario_key == scenario_key))
    if existing:
        raise HTTPException(status_code=400, detail="scenario_key already exists")

    if docker_compose_file.filename.lower() not in ("docker-compose.yml", "docker-compose.yaml"):
        raise HTTPException(status_code=400, detail="Please upload docker-compose.yml or docker-compose.yaml")

    scenario_dir = Path(settings.scenarios_dir) / "docker" / scenario_key
    if scenario_dir.exists():
        raise HTTPException(status_code=400, detail="Scenario directory already exists")

    scenario_dir.mkdir(parents=True, exist_ok=False)

    data = {
        "scenario_key": scenario_key,
        "name": name,
        "description": description,
        "type": "docker",
    }

    try:
        scenario_json = scenario_dir / "scenario.json"
        scenario_json.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        content = await docker_compose_file.read()
        compose_file = scenario_dir / "docker-compose.yml"
        compose_file.write_bytes(content)

        count = ScenarioService(db).sync_from_filesystem()
        return {
            "ok": True,
            "synced": count,
            "path": f"docker/{scenario_key}"
        }
    except Exception as e:
        shutil.rmtree(scenario_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/update-scenario/{scenario_id}")
def update_scenario(
    scenario_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    user=Depends(require_role("admin")),
):
    scenario = db.get(Scenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    name = payload.get("name")
    description = payload.get("description")

    if name is not None:
        name = str(name).strip()
        if not name:
            raise HTTPException(status_code=400, detail="name cannot be empty")
        scenario.name = name

    if description is not None:
        scenario.description = str(description).strip()

    db.commit()
    db.refresh(scenario)

    return {
        "ok": True,
        "id": scenario.id,
        "name": scenario.name,
        "description": scenario.description,
    }


@router.delete("/delete-scenario/{scenario_id}")
def delete_scenario(
    scenario_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_role("admin")),
):
    scenario = db.get(Scenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    running = db.scalar(
        select(ScenarioSession).where(
            ScenarioSession.scenario_id == scenario.id,
            ScenarioSession.status == "running",
        )
    )
    if running:
        raise HTTPException(status_code=400, detail="Cannot delete scenario with a running session")

    steps = list(db.scalars(select(LabStep).where(LabStep.scenario_id == scenario.id)))
    for step in steps:
        progresses = list(db.scalars(select(StudentLabStep).where(StudentLabStep.step_id == step.id)))
        for prog in progresses:
            db.delete(prog)
        db.delete(step)

    scenario_dir = Path(settings.scenarios_dir) / scenario.path
    if scenario_dir.exists():
        shutil.rmtree(scenario_dir, ignore_errors=True)

    db.delete(scenario)
    db.commit()
    return {"ok": True, "deleted_id": scenario_id}


# =================================================
# Courses
# =================================================

@router.get("/courses")
def list_courses(db: Session = Depends(get_db), user=Depends(require_role("admin"))):
    courses = list(db.scalars(select(Course).order_by(Course.id)))
    return [
        {
            "id": c.id,
            "code": c.code,
            "name": c.name,
            "description": c.description,
        }
        for c in courses
    ]


@router.post("/create-course")
def create_course(
    payload: dict,
    db: Session = Depends(get_db),
    user=Depends(require_role("admin")),
):
    code = (payload.get("code") or "").strip()
    name = (payload.get("name") or "").strip()
    description = (payload.get("description") or "").strip()

    if not code or not name:
        raise HTTPException(status_code=400, detail="code and name are required")

    existing = db.scalar(select(Course).where(Course.code == code))
    if existing:
        raise HTTPException(status_code=400, detail="Course code already exists")

    course = Course(code=code, name=name, description=description)
    db.add(course)
    db.commit()
    db.refresh(course)

    return {
        "ok": True,
        "id": course.id,
        "code": course.code,
        "name": course.name,
        "description": course.description,
    }


@router.put("/update-course/{course_id}")
def update_course(
    course_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    user=Depends(require_role("admin")),
):
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    code = payload.get("code")
    name = payload.get("name")
    description = payload.get("description")

    if code is not None:
        code = str(code).strip()
        if not code:
            raise HTTPException(status_code=400, detail="code cannot be empty")
        existing = db.scalar(select(Course).where(Course.code == code, Course.id != course_id))
        if existing:
            raise HTTPException(status_code=400, detail="Course code already exists")
        course.code = code

    if name is not None:
        name = str(name).strip()
        if not name:
            raise HTTPException(status_code=400, detail="name cannot be empty")
        course.name = name

    if description is not None:
        course.description = str(description).strip()

    db.commit()
    db.refresh(course)

    return {
        "ok": True,
        "id": course.id,
        "code": course.code,
        "name": course.name,
        "description": course.description,
    }


@router.delete("/delete-course/{course_id}")
def delete_course(
    course_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_role("admin")),
):
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    linked_scenarios = list(db.scalars(select(Scenario).where(Scenario.course_id == course.id)))
    if linked_scenarios:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete course while scenarios are still linked to it"
        )

    db.delete(course)
    db.commit()
    return {"ok": True, "deleted_id": course_id}


@router.post("/assign-scenario-course")
def assign_scenario_to_course(
    payload: dict,
    db: Session = Depends(get_db),
    user=Depends(require_role("admin")),
):
    scenario_id = payload.get("scenario_id")
    course_id = payload.get("course_id")

    if not scenario_id:
        raise HTTPException(status_code=400, detail="scenario_id is required")

    scenario = db.get(Scenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    if course_id is None:
        scenario.course_id = None
        db.commit()
        return {"ok": True, "scenario_id": scenario.id, "course_id": None}

    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    scenario.course_id = course.id
    db.commit()

    return {
        "ok": True,
        "scenario_id": scenario.id,
        "course_id": course.id,
        "course_name": course.name,
    }


# =================================================
# Lab Steps
# =================================================

@router.get("/scenario-steps/{scenario_id}")
def list_scenario_steps(
    scenario_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_role("admin")),
):
    scenario = db.get(Scenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    steps = list(
        db.scalars(
            select(LabStep)
            .where(LabStep.scenario_id == scenario.id)
            .order_by(LabStep.step_order, LabStep.id)
        )
    )

    return [
        {
            "id": s.id,
            "scenario_id": s.scenario_id,
            "step_order": s.step_order,
            "title": s.title,
            "description": s.description,
            "points": s.points,
            "answer_type": s.answer_type,
            "correct_answer": s.correct_answer,
            "placeholder": s.placeholder,
            "hint": s.hint,
            "is_required": s.is_required,
        }
        for s in steps
    ]


@router.post("/create-step")
def create_step(
    payload: dict,
    db: Session = Depends(get_db),
    user=Depends(require_role("admin")),
):
    scenario_id = payload.get("scenario_id")
    step_order = payload.get("step_order")
    title = (payload.get("title") or "").strip()
    description = (payload.get("description") or "").strip()
    points = int(payload.get("points") or 0)
    answer_type = (payload.get("answer_type") or "text").strip().lower()
    correct_answer = (payload.get("correct_answer") or "").strip()
    placeholder = (payload.get("placeholder") or "").strip()
    hint = (payload.get("hint") or "").strip()
    is_required = bool(payload.get("is_required", True))

    if not scenario_id or not title:
        raise HTTPException(status_code=400, detail="scenario_id and title are required")

    if answer_type not in ("info", "text", "flag"):
        raise HTTPException(status_code=400, detail="answer_type must be one of: info, text, flag")

    scenario = db.get(Scenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    if step_order is None:
        last_step = db.scalar(
            select(LabStep)
            .where(LabStep.scenario_id == scenario.id)
            .order_by(LabStep.step_order.desc())
        )
        step_order = (last_step.step_order + 1) if last_step else 1

    step = LabStep(
        scenario_id=scenario.id,
        step_order=int(step_order),
        title=title,
        description=description,
        points=points,
        answer_type=answer_type,
        correct_answer=correct_answer,
        placeholder=placeholder,
        hint=hint,
        is_required=is_required,
    )

    db.add(step)
    db.commit()
    db.refresh(step)

    return {
        "ok": True,
        "id": step.id,
        "scenario_id": step.scenario_id,
        "step_order": step.step_order,
        "title": step.title,
    }


@router.put("/update-step/{step_id}")
def update_step(
    step_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    user=Depends(require_role("admin")),
):
    step = db.get(LabStep, step_id)
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")

    title = payload.get("title")
    if title is not None:
        title = str(title).strip()
        if not title:
            raise HTTPException(status_code=400, detail="title cannot be empty")
        step.title = title

    if "description" in payload:
        step.description = str(payload.get("description") or "").strip()

    if "points" in payload:
        step.points = _safe_int(payload.get("points"), 0)

    if "answer_type" in payload:
        answer_type = str(payload.get("answer_type") or "").strip().lower()
        if answer_type not in ("info", "text", "flag"):
            raise HTTPException(status_code=400, detail="answer_type must be one of: info, text, flag")
        step.answer_type = answer_type

    if "correct_answer" in payload:
        step.correct_answer = str(payload.get("correct_answer") or "").strip()

    if "placeholder" in payload:
        step.placeholder = str(payload.get("placeholder") or "").strip()

    if "hint" in payload:
        step.hint = str(payload.get("hint") or "").strip()

    if "step_order" in payload and payload.get("step_order") is not None:
        step.step_order = _safe_int(payload.get("step_order"), step.step_order)

    if "is_required" in payload:
        step.is_required = bool(payload.get("is_required"))

    db.commit()
    db.refresh(step)

    return {
        "ok": True,
        "id": step.id,
        "scenario_id": step.scenario_id,
        "title": step.title,
    }


@router.delete("/delete-step/{step_id}")
def delete_step(
    step_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_role("admin")),
):
    step = db.get(LabStep, step_id)
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")

    progresses = list(db.scalars(select(StudentLabStep).where(StudentLabStep.step_id == step.id)))
    for prog in progresses:
        db.delete(prog)

    db.delete(step)
    db.commit()
    return {"ok": True, "deleted_id": step_id}


# =================================================
# Students
# =================================================

@router.get("/students")
def list_students(db: Session = Depends(get_db), user=Depends(require_role("admin"))):
    students = list(
        db.scalars(
            select(User).where(User.role == "student").order_by(User.id)
        )
    )
    return [
        {
            "id": u.id,
            "username": u.username,
            "role": u.role,
        }
        for u in students
    ]


@router.get("/students-search")
def search_students(
    q: str = Query(default=""),
    db: Session = Depends(get_db),
    user=Depends(require_role("admin"))
):
    q = (q or "").strip()

    stmt = select(User).where(User.role == "student")
    if q:
        stmt = stmt.where(User.username.ilike(f"%{q}%"))

    students = list(db.scalars(stmt.order_by(User.id)))
    return [
        {
            "id": u.id,
            "username": u.username,
            "role": u.role,
        }
        for u in students
    ]


@router.post("/create-student")
def create_student(
    payload: dict,
    db: Session = Depends(get_db),
    user=Depends(require_role("admin")),
):
    username = (payload.get("username") or "").strip()
    password = (payload.get("password") or "").strip()

    if not username or not password:
        raise HTTPException(status_code=400, detail="username and password are required")

    existing = db.scalar(select(User).where(User.username == username))
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    student = User(username=username, password=password, role="student")
    db.add(student)
    db.commit()
    db.refresh(student)

    return {"ok": True, "id": student.id, "username": student.username, "role": student.role}


@router.put("/update-student/{student_id}")
def update_student(
    student_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    user=Depends(require_role("admin")),
):
    student = db.get(User, student_id)
    if not student or student.role != "student":
        raise HTTPException(status_code=404, detail="Student not found")

    username = payload.get("username")
    password = payload.get("password")

    if username is not None:
        username = str(username).strip()
        if not username:
            raise HTTPException(status_code=400, detail="username cannot be empty")

        existing = db.scalar(select(User).where(User.username == username, User.id != student_id))
        if existing:
            raise HTTPException(status_code=400, detail="Username already exists")

        student.username = username

    if password is not None:
        password = str(password).strip()
        if password:
            student.password = password

    db.commit()
    db.refresh(student)

    return {"ok": True, "id": student.id, "username": student.username, "role": student.role}


@router.get("/student-stats/{student_id}")
def student_stats(
    student_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_role("admin"))
):
    student = db.get(User, student_id)
    if not student or student.role != "student":
        raise HTTPException(status_code=404, detail="Student not found")

    sessions = list(
        db.scalars(
            select(ScenarioSession)
            .where(ScenarioSession.user_id == student_id)
            .order_by(ScenarioSession.id.desc())
        )
    )

    total_sessions = len(sessions)
    running_sessions = len([s for s in sessions if s.status == "running"])
    ended_sessions = len([s for s in sessions if s.status == "ended"])
    scenario_ids = list({s.scenario_id for s in sessions if s.scenario_id})

    completed_steps = db.scalar(
        select(func.count(StudentLabStep.id)).where(StudentLabStep.user_id == student_id)
    ) or 0

    scenario_names = []
    for sid in scenario_ids:
        scenario = db.get(Scenario, sid)
        if scenario:
            scenario_names.append({
                "id": scenario.id,
                "name": scenario.name,
            })

    latest_sessions = []
    for sess in sessions[:10]:
        scenario = db.get(Scenario, sess.scenario_id)
        latest_sessions.append({
            "id": sess.id,
            "scenario_id": sess.scenario_id,
            "scenario_name": scenario.name if scenario else None,
            "status": sess.status,
            "started_at": sess.started_at,
            "ended_at": sess.ended_at,
        })

    return {
        "student_id": student.id,
        "username": student.username,
        "total_sessions": total_sessions,
        "running_sessions": running_sessions,
        "ended_sessions": ended_sessions,
        "completed_steps": completed_steps,
        "joined_scenarios_count": len(scenario_ids),
        "joined_scenarios": scenario_names,
        "latest_sessions": latest_sessions,
    }


@router.delete("/delete-student/{student_id}")
def delete_student(
    student_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_role("admin")),
):
    student = db.get(User, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    if student.role != "student":
        raise HTTPException(status_code=400, detail="Only students can be deleted here")

    running = db.scalar(
        select(ScenarioSession).where(
            ScenarioSession.user_id == student.id,
            ScenarioSession.status == "running",
        )
    )
    if running:
        raise HTTPException(status_code=400, detail="Cannot delete student with a running session")

    db.delete(student)
    db.commit()
    return {"ok": True, "deleted_id": student_id}


# =================================================
# Sessions
# =================================================

@router.get("/sessions")
def list_sessions(db: Session = Depends(get_db), user=Depends(require_role("admin"))):
    sessions = list(db.scalars(select(ScenarioSession).order_by(ScenarioSession.id.desc())))

    out = []
    for sess in sessions:
        scenario = db.get(Scenario, sess.scenario_id)
        student = db.get(User, sess.user_id)

        out.append({
            "id": sess.id,
            "user_id": sess.user_id,
            "username": student.username if student else None,
            "scenario_id": sess.scenario_id,
            "scenario_name": scenario.name if scenario else None,
            "status": sess.status,
            "started_at": sess.started_at,
            "ended_at": sess.ended_at,
        })

    return out


@router.post("/end-session/{session_id}")
def end_session_as_admin(
    session_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_role("admin")),
):
    session_svc = ScenarioSessionService(db)

    sess: ScenarioSession | None = db.get(ScenarioSession, session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    if sess.status != "running":
        raise HTTPException(status_code=400, detail="Session is not running")

    runtime_data = session_svc.parse_runtime_data(sess) or {}

    scenario = db.get(Scenario, sess.scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    runtime = RuntimeFactory.get_runtime(scenario.type)
    runtime.stop(runtime_data)

    ended = session_svc.end_session(sess.id, runtime_data=runtime_data)
    return {"ok": True, "session_id": ended.id}


# =================================================
# Server Resources
# =================================================

@router.get("/server-resources")
def server_resources(db: Session = Depends(get_db), user=Depends(require_role("admin"))):
    vm_count = 0
    docker_count = 0

    try:
        p = _run([settings.vmrun_path, "list"], allow_fail=True)
        lines = [x.strip() for x in (p.stdout or "").splitlines() if x.strip()]
        vm_count = max(0, len(lines) - 1) if lines else 0
    except Exception:
        vm_count = 0

    try:
        p = _run([settings.docker_bin, "ps", "-q"], allow_fail=True)
        docker_count = len([x for x in (p.stdout or "").splitlines() if x.strip()])
    except Exception:
        docker_count = 0

    mem = psutil.virtual_memory()
    disk = psutil.disk_usage(str(Path.cwd().anchor or Path.cwd()))

    return {
        "cpu_percent": psutil.cpu_percent(interval=0.3),
        "ram_total_gb": round(mem.total / (1024 ** 3), 2),
        "ram_used_gb": round(mem.used / (1024 ** 3), 2),
        "ram_percent": mem.percent,
        "disk_total_gb": round(disk.total / (1024 ** 3), 2),
        "disk_used_gb": round(disk.used / (1024 ** 3), 2),
        "disk_percent": disk.percent,
        "running_vms": vm_count,
        "running_docker_containers": docker_count,
    }


# =================================================
# Running VMs
# =================================================

@router.get("/vms")
def list_running_vms(db: Session = Depends(get_db), user=Depends(require_role("admin"))):
    try:
        p = _run([settings.vmrun_path, "list"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    lines = [x.strip() for x in (p.stdout or "").splitlines() if x.strip()]
    vmx_paths = lines[1:] if len(lines) > 1 else []

    session_map = _build_session_map(db)

    out = []
    for vmx in vmx_paths:
        linked = session_map.get(vmx)
        out.append({
            "vmx_path": vmx,
            "name": Path(vmx).stem,
            "linked_session": linked,
        })

    return out


@router.post("/stop-vm")
def stop_vm(
    payload: dict,
    db: Session = Depends(get_db),
    user=Depends(require_role("admin")),
):
    vmx_path = (payload.get("vmx_path") or "").strip()
    if not vmx_path:
        raise HTTPException(status_code=400, detail="vmx_path is required")

    try:
        _run([settings.vmrun_path, "stop", vmx_path, "hard"])
        return {"ok": True, "vmx_path": vmx_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/delete-vm")
def delete_vm(
    payload: dict,
    db: Session = Depends(get_db),
    user=Depends(require_role("admin")),
):
    vmx_path = (payload.get("vmx_path") or "").strip()
    if not vmx_path:
        raise HTTPException(status_code=400, detail="vmx_path is required")

    vmx_file = Path(vmx_path)
    if not vmx_file.exists():
        raise HTTPException(status_code=404, detail="VMX file not found")

    running_vmx = _get_running_vmx_paths()
    if vmx_path in running_vmx:
        raise HTTPException(status_code=400, detail="Cannot delete a running VM")

    vm_dir = vmx_file.parent

    try:
        shutil.rmtree(vm_dir, ignore_errors=True)
        return {"ok": True, "deleted_vm_dir": str(vm_dir)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =================================================
# Runtime clones browser
# =================================================

@router.get("/runtime-clones")
def list_runtime_clones(
    db: Session = Depends(get_db),
    user=Depends(require_role("admin")),
):
    clones_root = Path(settings.vm_clones_dir)
    clones_root.mkdir(parents=True, exist_ok=True)

    running_vmx = _get_running_vmx_paths()

    session_map = {}
    sessions = list(db.scalars(select(ScenarioSession).order_by(ScenarioSession.id.desc())))
    for sess in sessions:
        rd = ScenarioSessionService(db).parse_runtime_data(sess) or {}

        clone_dir = rd.get("clone_dir")
        if clone_dir:
            session_map[str(Path(clone_dir).resolve())] = {
                "session_id": sess.id,
                "status": sess.status,
                "user_id": sess.user_id,
                "scenario_id": sess.scenario_id,
            }

    items = []

    for child in sorted(clones_root.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir():
            continue

        if child.name == "_vmnet_locks":
            continue

        vmx_files = [str(p) for p in child.rglob("*.vmx")]
        is_running = any(vmx in running_vmx for vmx in vmx_files)

        total_size = 0
        try:
            for f in child.rglob("*"):
                if f.is_file():
                    total_size += f.stat().st_size
        except Exception:
            pass

        linked_info = session_map.get(str(child.resolve()))

        orphan_state = "orphan"
        if linked_info:
            if linked_info["status"] == "running":
                orphan_state = "linked_running"
            else:
                orphan_state = "linked_ended"

        items.append({
            "name": child.name,
            "path": str(child),
            "vmx_files": vmx_files,
            "vmx_count": len(vmx_files),
            "is_running": is_running,
            "size_mb": round(total_size / (1024 * 1024), 2),
            "linked_info": linked_info,
            "state": orphan_state,
        })

    return items


@router.delete("/runtime-clones")
def delete_runtime_clone(
    payload: dict,
    db: Session = Depends(get_db),
    user=Depends(require_role("admin")),
):
    clone_path = (payload.get("path") or "").strip()
    if not clone_path:
        raise HTTPException(status_code=400, detail="path is required")

    clones_root = Path(settings.vm_clones_dir).resolve()
    target = Path(clone_path).resolve()

    try:
        target.relative_to(clones_root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid clone path")

    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="Clone folder not found")

    running_vmx = _get_running_vmx_paths()

    vmx_files = [str(p) for p in target.rglob("*.vmx")]
    still_running = [vmx for vmx in vmx_files if vmx in running_vmx]

    if still_running:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete clone while VM is still running: {still_running[0]}"
        )

    shutil.rmtree(target, ignore_errors=True)
    return {"ok": True, "deleted_path": str(target)}