"""Login, logout, current user and own password."""

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, Request, Response

from api.deps import SESSION_COOKIE, current_user, get_conn
from config import settings
from schemas.requests import LoginRequest, PasswordChange
from schemas.responses import Ok, UserOut
from services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=UserOut)
def login(body: LoginRequest, response: Response, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    token, user = auth_service.login(conn, body.username, body.password)
    response.set_cookie(
        SESSION_COOKIE, token, max_age=settings.session_days * 86400, httponly=True, secure=settings.secure_cookies,
        samesite="lax", path="/",
    )
    return user


@router.post("/logout", response_model=Ok)
def logout(request: Request, response: Response, conn: sqlite3.Connection = Depends(get_conn)) -> Ok:
    auth_service.logout(conn, request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/")
    return Ok()


@router.get("/me", response_model=UserOut)
def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return user


@router.post("/password", response_model=Ok)
def change_password(body: PasswordChange, user: dict[str, Any] = Depends(current_user),
                    conn: sqlite3.Connection = Depends(get_conn)) -> Ok:
    auth_service.change_own_password(conn, user["id"], body.current, body.new)
    return Ok()
