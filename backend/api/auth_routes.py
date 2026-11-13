from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend import auth
from backend.database import get_db
from backend.models import User
from backend.schemas import LoginIn, RegisterIn
from utils.validators import validate_email, validate_password, validate_username

router = APIRouter(prefix="/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)


def user_out(u: User) -> dict:
    return {"id": u.id, "username": u.username, "email": u.email, "role": u.role, "is_active": u.is_active, "created_at": u.created_at.isoformat()}


@router.post("/register", status_code=201)
def register(payload: RegisterIn, request: Request, db: Session = Depends(get_db)):
    auth.ip_limit(request, limit=10)
    try:
        username, email, pw = validate_username(payload.username), validate_email(payload.email), validate_password(payload.password)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    first = db.query(User).count() == 0
    user = User(username=username, email=email, password_hash=auth.hash_password(pw), role="admin" if first else "user")
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Username or email already registered")
    return {"access_token": auth.create_token(user), "token_type": "bearer", "user": user_out(user)}


@router.post("/login")
def login(payload: LoginIn, request: Request, db: Session = Depends(get_db)):
    auth.ip_limit(request, limit=10)
    user = db.query(User).filter(User.username == payload.username.strip()).first()
    if not user or not user.is_active or not auth.verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "Invalid username or password")
    return {"access_token": auth.create_token(user), "token_type": "bearer", "user": user_out(user)}


@router.post("/logout")
def logout(creds: HTTPAuthorizationCredentials | None = Depends(_bearer), _: User = Depends(auth.get_current_user)):
    if creds:
        auth.revoke_token(creds.credentials)
    return {"detail": "Logged out"}


@router.get("/me")
def me(user: User = Depends(auth.get_current_user)):
    return user_out(user)
