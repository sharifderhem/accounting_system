"""Form context for every role; settings, parties, cost centers and users for the owner (§15)."""

import sqlite3
from typing import Any

from fastapi import APIRouter, Body, Depends

from api.deps import current_user, get_conn, owner
from schemas.requests import CostCenterCreate, PartyCreate, UserCreate, UserUpdate
from schemas.responses import UserOut
from services import auth_service, meta_service, settings_service

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/meta")
def meta(user: dict[str, Any] = Depends(current_user), conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return meta_service.context(conn, user)


@router.get("/settings")
def get_settings(_: dict[str, Any] = Depends(owner), conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return settings_service.get(conn)


@router.put("/settings")
def update_settings(values: dict[str, Any] = Body(...), _: dict[str, Any] = Depends(owner),
                    conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return settings_service.update(conn, values)


@router.post("/parties")
def add_party(body: PartyCreate, _: dict[str, Any] = Depends(owner), conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return settings_service.add_party(conn, body.name, body.type)


@router.post("/cost-centers")
def add_cost_center(body: CostCenterCreate, _: dict[str, Any] = Depends(owner),
                    conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return settings_service.add_cost_center(conn, body.name)


@router.get("/users", response_model=list[UserOut])
def list_users(_: dict[str, Any] = Depends(owner), conn: sqlite3.Connection = Depends(get_conn)) -> list[dict[str, Any]]:
    return auth_service.list_users(conn)


@router.post("/users", response_model=UserOut)
def create_user(body: UserCreate, _: dict[str, Any] = Depends(owner), conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return auth_service.create_user(conn, body.username, body.label, body.password, body.role, body.approver)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, _: dict[str, Any] = Depends(owner),
                conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return auth_service.update_user(conn, user_id, body.model_dump(exclude_unset=True))
