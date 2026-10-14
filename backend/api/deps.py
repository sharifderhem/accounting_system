"""Request-scoped dependencies: a database connection and the signed-in user."""

import sqlite3
from typing import Any, Iterator

from fastapi import Depends, HTTPException, Request, status

from database import Database
from services import access, auth_service

SESSION_COOKIE = "jl_session"


def get_conn() -> Iterator[sqlite3.Connection]:
    conn = Database.connect()
    try:
        yield conn
    finally:
        conn.close()


def current_user(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    user = auth_service.user_for_token(conn, request.cookies.get(SESSION_COOKIE))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="سجّل الدخول أولاً")
    if user["role"] == "none":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="لم يحدد المالك صلاحياتك بعد")
    return user


def owner(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    access.require_owner(user)
    return user


def finance_viewer(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    """Owner and reviewer: balances, reports, journal, analytics (§14)."""
    access.require_finance(user)
    return user
