from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import select

from core.dependencies import get_db, require_role
from services.dashboard_service import DashboardService
from services.scenario_service import ScenarioService
from services.scenario_session_service import ScenarioSessionService
from services.runtime.factory import RuntimeFactory
from models.scenario_session import ScenarioSession
from models.scenario import Scenario
from models.course import Course
from models.lab_step import LabStep
from models.student_lab_step import StudentLabStep
from schemas.dashboard import StudentDashboardResponse
from core.database import SessionLocal

import traceback

router = APIRouter(prefix="/api/student", tags=["student"])


def _calc_duration_seconds(started_at, ended_at=None) -> int:
    if not started_at:
        return 0
    end_time = ended_at or datetime.utcnow()
    return max(0, int((end_time - started_at).total_seconds()))


def _serialize_running_session(db: Session, running: ScenarioSession | None):
    if not running:
        return None

    rd = ScenarioSessionService(db).parse_runtime_data(running) or {}

    if rd.get("type") == "vm_rdp":
        rd = dict(rd)
        rd["rdp_download_url"] = f"/api/student/rdp/{running.id}"

    return {
        "id": running.id,
        "user_id": running.user_id,
        "scenario_id": running.scenario_id,
        "status": running.status,
        "started_at": running.started_at,
        "ended_at": running.ended_at,
        "runtime_data": rd,
    }


def _serialize_scenario_with_course(db: Session, scenario: Scenario):
    course = db.get(Course, scenario.course_id) if scenario.course_id else None
    return {
        "id": scenario.id,
        "scenario_key": scenario.scenario_key,
        "name": scenario.name,
        "type": scenario.type,
        "path": scenario.path,
        "description": scenario.description or "",
        "course_id": scenario.course_id,
        "course_name": course.name if course else None,
        "course": {
            "id": course.id,
            "code": course.code,
            "name": course.name,
            "description": course.description,
        } if course else None,
    }


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), user=Depends(require_role("student"))):
    dash = DashboardService(db)
    scenarios, running = dash.student_dashboard(user)

    general_scenarios = []
    course_map = {}

    for item in scenarios:
        scenario_id = item.id if hasattr(item, "id") else item.get("id")
        scenario = db.get(Scenario, scenario_id)
        if not scenario:
            continue

        serialized = _serialize_scenario_with_course(db, scenario)

        if scenario.course_id:
            course = db.get(Course, scenario.course_id)
            if course:
                if course.id not in course_map:
                    course_map[course.id] = {
                        "id": course.id,
                        "code": course.code,
                        "name": course.name,
                        "description": course.description,
                        "scenarios_count": 0,
                    }
                course_map[course.id]["scenarios_count"] += 1
        else:
            general_scenarios.append(serialized)

    return {
        "user": {"id": user.id, "username": user.username, "role": user.role},
        "general_scenarios": general_scenarios,
        "courses": list(course_map.values()),
        "running_session": _serialize_running_session(db, running),
    }


@router.get("/courses")
def list_courses_for_student(db: Session = Depends(get_db), user=Depends(require_role("student"))):
    courses = list(db.scalars(select(Course).order_by(Course.name, Course.id)))
    out = []

    for c in courses:
        linked_scenarios = list(
            db.scalars(
                select(Scenario)
                .where(Scenario.course_id == c.id)
                .order_by(Scenario.id)
            )
        )
        if not linked_scenarios:
            continue

        out.append({
            "id": c.id,
            "code": c.code,
            "name": c.name,
            "description": c.description,
            "scenarios_count": len(linked_scenarios),
        })

    return out


@router.get("/course-scenarios/{course_id}")
def course_scenarios(
    course_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_role("student")),
):
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    scenarios = list(
        db.scalars(
            select(Scenario)
            .where(Scenario.course_id == course.id)
            .order_by(Scenario.id)
        )
    )

    return {
        "course": {
            "id": course.id,
            "code": course.code,
            "name": course.name,
            "description": course.description,
        },
        "scenarios": [_serialize_scenario_with_course(db, s) for s in scenarios]
    }


@router.get("/scenario-details/{scenario_id}")
def scenario_details(
    scenario_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_role("student")),
):
    scenario = db.get(Scenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    course = db.get(Course, scenario.course_id) if scenario.course_id else None

    steps = list(
        db.scalars(
            select(LabStep)
            .where(LabStep.scenario_id == scenario.id)
            .order_by(LabStep.step_order, LabStep.id)
        )
    )

    total_possible_score = sum(int(s.points or 0) for s in steps)

    running = db.scalar(
        select(ScenarioSession).where(
            ScenarioSession.user_id == user.id,
            ScenarioSession.scenario_id == scenario.id,
            ScenarioSession.status == "running",
        )
    )

    return {
        "id": scenario.id,
        "scenario_key": scenario.scenario_key,
        "name": scenario.name,
        "type": scenario.type,
        "path": scenario.path,
        "description": scenario.description or "",
        "course": {
            "id": course.id,
            "code": course.code,
            "name": course.name,
            "description": course.description,
        } if course else None,
        "steps_count": len(steps),
        "total_possible_score": total_possible_score,
        "running_session": _serialize_running_session(db, running),
    }


@router.get("/scenario-steps/{scenario_id}")
def scenario_steps(
    scenario_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_role("student")),
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
            "placeholder": s.placeholder,
            "hint": s.hint,
            "is_required": s.is_required,
        }
        for s in steps
    ]


@router.get("/session-progress/{session_id}")
def session_progress(
    session_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_role("student")),
):
    sess: ScenarioSession | None = db.get(ScenarioSession, session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    if sess.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your session")

    scenario = db.get(Scenario, sess.scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    steps = list(
        db.scalars(
            select(LabStep)
            .where(LabStep.scenario_id == scenario.id)
            .order_by(LabStep.step_order, LabStep.id)
        )
    )

    progress_rows = list(
        db.scalars(
            select(StudentLabStep).where(
                StudentLabStep.session_id == sess.id,
                StudentLabStep.user_id == user.id,
            )
        )
    )

    progress_by_step = {}
    for row in progress_rows:
        existing = progress_by_step.get(row.step_id)
        if existing is None or row.id > existing.id:
            progress_by_step[row.step_id] = row

    total_score = 0
    total_possible_score = 0
    completed_steps = 0

    steps_out = []
    for step in steps:
        total_possible_score += int(step.points or 0)
        row = progress_by_step.get(step.id)

        is_completed = bool(row and row.is_correct)
        awarded_points = int(row.awarded_points or 0) if row else 0

        if is_completed:
            completed_steps += 1
            total_score += awarded_points

        steps_out.append({
            "step_id": step.id,
            "id": step.id,
            "step_order": step.step_order,
            "title": step.title,
            "description": step.description,
            "points": step.points,
            "answer_type": step.answer_type,
            "placeholder": step.placeholder,
            "hint": step.hint,
            "is_required": step.is_required,
            "submitted_answer": row.submitted_answer if row else "",
            "is_correct": bool(row.is_correct) if row else False,
            "awarded_points": awarded_points,
            "submitted_at": row.submitted_at if row else None,
        })

    return {
        "session_id": sess.id,
        "scenario_id": sess.scenario_id,
        "status": sess.status,
        "started_at": sess.started_at,
        "ended_at": sess.ended_at,
        "duration_seconds": _calc_duration_seconds(sess.started_at, sess.ended_at),
        "completed_steps": completed_steps,
        "total_steps": len(steps),
        "total_score": total_score,
        "total_possible_score": total_possible_score,
        "steps": steps_out,
    }


@router.post("/submit-step")
def submit_step(
    payload: dict,
    db: Session = Depends(get_db),
    user=Depends(require_role("student")),
):
    session_id = payload.get("session_id")
    step_id = payload.get("step_id")
    submitted_answer = (payload.get("answer") or "").strip()

    if not session_id or not step_id:
        raise HTTPException(status_code=400, detail="session_id and step_id are required")

    sess: ScenarioSession | None = db.get(ScenarioSession, int(session_id))
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    if sess.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your session")

    if sess.status != "running":
        raise HTTPException(status_code=400, detail="Session is not running")

    step: LabStep | None = db.get(LabStep, int(step_id))
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")

    if step.scenario_id != sess.scenario_id:
        raise HTTPException(status_code=400, detail="This step does not belong to the session scenario")

    existing_correct = db.scalar(
        select(StudentLabStep).where(
            StudentLabStep.session_id == sess.id,
            StudentLabStep.user_id == user.id,
            StudentLabStep.step_id == step.id,
            StudentLabStep.is_correct == True,
        )
    )
    if existing_correct:
        return {
            "ok": True,
            "already_completed": True,
            "is_correct": True,
            "awarded_points": int(existing_correct.awarded_points or 0),
            "message": "Step already completed",
        }

    answer_type = (step.answer_type or "text").lower()

    if answer_type == "info":
        is_correct = True
        awarded_points = int(step.points or 0)
    else:
        correct_answer = (step.correct_answer or "").strip()
        is_correct = submitted_answer == correct_answer
        awarded_points = int(step.points or 0) if is_correct else 0

    row = StudentLabStep(
        user_id=user.id,
        session_id=sess.id,
        step_id=step.id,
        submitted_answer=submitted_answer,
        is_correct=is_correct,
        awarded_points=awarded_points,
        submitted_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return {
        "ok": True,
        "already_completed": False,
        "is_correct": is_correct,
        "awarded_points": awarded_points,
        "message": "Correct answer" if is_correct else "Incorrect answer",
    }


@router.post("/start/{scenario_id}")
def start_scenario(
    scenario_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user=Depends(require_role("student")),
):
    scenario_svc = ScenarioService(db)
    session_svc = ScenarioSessionService(db)

    scenario = scenario_svc.get_by_id(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    if session_svc.is_scenario_running_for_user(user.id, scenario.id):
        raise HTTPException(status_code=400, detail="Scenario already running for this user")

    if scenario.type == "vm" and session_svc.get_running_for_user(user.id):
        raise HTTPException(status_code=400, detail="You already have a running VM session. End it first.")

    if scenario.type == "docker":
        runtime = RuntimeFactory.get_runtime(scenario.type)
        result = runtime.start(user, scenario)

        rd = dict(result.runtime_data or {})
        if result.access_url:
            rd["access_url"] = result.access_url

        sess = session_svc.create_running(user.id, scenario.id, rd)
        return {
            "session_id": sess.id,
            "access_url": result.access_url,
            "runtime_data": rd,
        }

    sess = session_svc.create_running(user.id, scenario.id, runtime_data={"phase": "starting"})

    def _vm_job(session_id: int, user_id: int, scenario_id2: int):
        db2 = SessionLocal()
        try:
            scenario2 = ScenarioService(db2).get_by_id(scenario_id2)
            user2 = user

            runtime = RuntimeFactory.get_runtime("vm")
            result = runtime.start(user2, scenario2)

            rd = dict(result.runtime_data or {})
            if rd.get("type") == "vm_rdp":
                rd["rdp_download_url"] = f"/api/student/rdp/{session_id}"

            ScenarioSessionService(db2).update_runtime_data(session_id, rd)

        except Exception as e:
            print("VM start failed:", str(e))
            traceback.print_exc()

            try:
                ScenarioSessionService(db2).end_session(session_id, runtime_data={"error": str(e)})
            except Exception:
                pass
        finally:
            db2.close()

    background_tasks.add_task(_vm_job, sess.id, user.id, scenario.id)

    return {"session_id": sess.id, "status": "starting"}


@router.get("/rdp/{session_id}")
def download_rdp(session_id: int, db: Session = Depends(get_db), user=Depends(require_role("student"))):
    session_svc = ScenarioSessionService(db)

    sess: ScenarioSession | None = db.get(ScenarioSession, session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    if sess.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your session")

    if sess.status != "running":
        raise HTTPException(status_code=400, detail="Session not running")

    rd = session_svc.parse_runtime_data(sess) or {}
    if rd.get("type") != "vm_rdp":
        raise HTTPException(status_code=400, detail="Not an RDP VM session")

    entry_machine = rd.get("entry_machine") or {}
    guest_ip = entry_machine.get("guest_ip") or rd.get("guest_ip")
    username = entry_machine.get("username") or rd.get("rdp_user") or ""
    port = entry_machine.get("port") or rd.get("rdp_port") or 3389

    if not guest_ip:
        raise HTTPException(status_code=400, detail="Missing guest_ip in runtime_data")

    lines = [
        f"full address:s:{guest_ip}:{port}",
        "prompt for credentials:i:1",
        "redirectclipboard:i:1",
        "screen mode id:i:2",
        "desktopwidth:i:1366",
        "desktopheight:i:768",
    ]
    if username:
        lines.append(f"username:s:{username}")

    rdp_text = "\r\n".join(lines) + "\r\n"

    return Response(
        content=rdp_text,
        media_type="application/x-rdp",
        headers={"Content-Disposition": 'attachment; filename="cyberrange.rdp"'},
    )


@router.post("/end/{session_id}")
def end_scenario(session_id: int, db: Session = Depends(get_db), user=Depends(require_role("student"))):
    session_svc = ScenarioSessionService(db)

    sess: ScenarioSession | None = db.get(ScenarioSession, session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    if sess.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your session")

    if sess.status != "running":
        raise HTTPException(status_code=400, detail="Session already ended")

    runtime_data = session_svc.parse_runtime_data(sess) or {}

    scenario = ScenarioService(db).get_by_id(sess.scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    runtime = RuntimeFactory.get_runtime(scenario.type)
    runtime.stop(runtime_data)

    ended = session_svc.end_session(sess.id, runtime_data=runtime_data)

    progress_rows = list(
        db.scalars(
            select(StudentLabStep).where(
                StudentLabStep.session_id == ended.id,
                StudentLabStep.user_id == user.id,
                StudentLabStep.is_correct == True,
            )
        )
    )
    total_score = sum(int(r.awarded_points or 0) for r in progress_rows)

    return {
        "ok": True,
        "session_id": ended.id,
        "ended_at": ended.ended_at,
        "duration_seconds": _calc_duration_seconds(ended.started_at, ended.ended_at),
        "total_score": total_score,
    }