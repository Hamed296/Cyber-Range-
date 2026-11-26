from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from pathlib import Path

from models.user import User
from models.scenario import Scenario
from models.scenario_session import ScenarioSession
from models.course import Course
from models.lab_step import LabStep
from models.student_lab_step import StudentLabStep




from core.database import Base, engine, SessionLocal
from services.auth_service import AuthService
from services.scenario_service import ScenarioService

from routers import auth as auth_router
from routers import student as student_router
from routers import admin as admin_router
from core.config import settings




app = FastAPI(title=settings.app_name)

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
def root():
    return FileResponse(str(static_dir / "index.html"))


# Redirect helper: so student gets a stable URL via backend
def _redirect_to_same_host(request: Request, port: int):
    host = request.url.hostname or "localhost"
    scheme = request.url.scheme or "http"
    return RedirectResponse(url=f"{scheme}://{host}:{port}")


@app.get("/runtime/ttyd/{port}")
def runtime_ttyd(request: Request, port: int):
    return _redirect_to_same_host(request, port)


@app.get("/runtime/novnc/{port}")
def runtime_novnc(request: Request, port: int):
    return _redirect_to_same_host(request, port)


app.include_router(auth_router.router)
app.include_router(student_router.router)
app.include_router(admin_router.router)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        AuthService(db).ensure_default_users()
        ScenarioService(db).sync_from_filesystem()
    finally:
        db.close()
