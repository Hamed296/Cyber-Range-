from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session
from core.dependencies import get_db
from schemas.auth import LoginRequest, LoginResponse
from services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    svc = AuthService(db)
    user = svc.authenticate(payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = svc.create_session_token(user.id)
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        samesite="lax",
    )
    return LoginResponse(id=user.id, username=user.username, role=user.role)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get("session_token")
    if token:
        AuthService(db).delete_session_token(token)
    response.delete_cookie("session_token")
    return {"ok": True}
