"""Login and role management (SRS 5.1, all roles / admin)."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ROLES, Magistrate, User
from ..security import create_token, current_user, hash_password, require, verify_password

router = APIRouter(tags=["auth"])


def user_out(u: User) -> dict:
    return {"id": u.id, "username": u.username, "full_name": u.full_name, "role": u.role,
            "court_station": u.court_station, "magistrate_id": u.magistrate_id, "active": u.active}


@router.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalars(select(User).where(User.username == form.username)).first()
    if not user or not user.active or not verify_password(form.password, user.password_hash):
        raise HTTPException(401, "Incorrect username or password")
    return {"access_token": create_token(user), "token_type": "bearer", "user": user_out(user)}


@router.get("/auth/me")
def me(user: User = Depends(current_user)):
    return user_out(user)


class UserIn(BaseModel):
    username: str
    full_name: str
    role: str
    password: str
    court_station: str | None = None
    magistrate_id: str | None = None


class UserPatch(BaseModel):
    full_name: str | None = None
    role: str | None = None
    password: str | None = None
    court_station: str | None = None
    magistrate_id: str | None = None
    active: bool | None = None


def _check_role(db, role, magistrate_id):
    if role not in ROLES:
        raise HTTPException(400, f"role must be one of {ROLES}")
    if role == "magistrate" and (not magistrate_id or not db.get(Magistrate, magistrate_id)):
        raise HTTPException(400, "A magistrate account must be linked to a magistrate on the roster")


@router.get("/users")
def list_users(db: Session = Depends(get_db), _=Depends(require("admin"))):
    return [user_out(u) for u in db.scalars(select(User).order_by(User.role, User.username))]


@router.post("/users", status_code=201)
def create_user(body: UserIn, db: Session = Depends(get_db), _=Depends(require("admin"))):
    _check_role(db, body.role, body.magistrate_id)
    if len(body.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    if db.scalars(select(User).where(User.username == body.username)).first():
        raise HTTPException(409, "Username already taken")
    u = User(username=body.username, full_name=body.full_name, role=body.role,
             password_hash=hash_password(body.password), court_station=body.court_station,
             magistrate_id=body.magistrate_id if body.role == "magistrate" else None)
    db.add(u)
    db.commit()
    return user_out(u)


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserPatch, db: Session = Depends(get_db), admin=Depends(require("admin"))):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    changes = body.model_dump(exclude_unset=True)
    if u.id == admin.id and (changes.get("active") is False or changes.get("role", "admin") != "admin"):
        raise HTTPException(400, "You cannot deactivate or demote your own admin account")
    role = changes.get("role", u.role)
    _check_role(db, role, changes.get("magistrate_id", u.magistrate_id))
    if "password" in changes:
        if len(changes["password"]) < 8:
            raise HTTPException(400, "Password must be at least 8 characters")
        u.password_hash = hash_password(changes.pop("password"))
    for k, v in changes.items():
        setattr(u, k, v)
    db.commit()
    return user_out(u)
