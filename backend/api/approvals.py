"""Payment requests (§6) and advance requests (§6.1)."""

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends

from api.deps import current_user, get_conn
from schemas.requests import AdvanceDecision, AdvanceForm
from schemas.responses import Ok
from services import requests_service

router = APIRouter(prefix="/api", tags=["approvals"])


@router.get("/requests")
def list_requests(user: dict[str, Any] = Depends(current_user), conn: sqlite3.Connection = Depends(get_conn)) -> list[dict[str, Any]]:
    return requests_service.list_for(conn, user)


@router.post("/requests/{req_id}/approve")
def approve(req_id: int, user: dict[str, Any] = Depends(current_user), conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return requests_service.approve(conn, req_id, user)


@router.post("/requests/{req_id}/reject", response_model=Ok)
def reject(req_id: int, user: dict[str, Any] = Depends(current_user), conn: sqlite3.Connection = Depends(get_conn)) -> Ok:
    requests_service.reject(conn, req_id, user)
    return Ok()


@router.post("/requests/{req_id}/withdraw", response_model=Ok)
def withdraw(req_id: int, user: dict[str, Any] = Depends(current_user), conn: sqlite3.Connection = Depends(get_conn)) -> Ok:
    requests_service.withdraw(conn, req_id, user)
    return Ok()


@router.get("/advances")
def list_advances(user: dict[str, Any] = Depends(current_user), conn: sqlite3.Connection = Depends(get_conn)) -> list[dict[str, Any]]:
    return requests_service.list_advances(conn, user)


@router.post("/advances")
def create_advance(body: AdvanceForm, user: dict[str, Any] = Depends(current_user),
                   conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return requests_service.create_advance(conn, body.model_dump(), user)


@router.post("/advances/{adv_id}/approve")
def approve_advance(adv_id: int, body: AdvanceDecision, user: dict[str, Any] = Depends(current_user),
                    conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return requests_service.approve_advance(conn, adv_id, body.source, body.custodian, user)


@router.post("/advances/{adv_id}/reject", response_model=Ok)
def reject_advance(adv_id: int, user: dict[str, Any] = Depends(current_user), conn: sqlite3.Connection = Depends(get_conn)) -> Ok:
    requests_service.reject_advance(conn, adv_id, user)
    return Ok()
