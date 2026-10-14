"""Transaction forms (§5): preview and save. Role checks happen in the service."""

import sqlite3
from typing import Any

from fastapi import APIRouter, Body, Depends

from api.deps import current_user, get_conn
from schemas.requests import FORMS
from schemas.responses import SaveResult
from services import transactions_service
from utils.errors import NotFound

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


def _form(kind: str, body: dict[str, Any]) -> dict[str, Any]:
    model = FORMS.get(kind)
    if model is None:
        raise NotFound("نوع الحركة غير معروف")
    return model.model_validate(body).model_dump()


@router.post("/{kind}/preview")
def preview(kind: str, body: dict[str, Any] = Body(...), user: dict[str, Any] = Depends(current_user),
            conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return transactions_service.preview(conn, kind, _form(kind, body), user)


@router.post("/{kind}", response_model=SaveResult)
def save(kind: str, body: dict[str, Any] = Body(...), user: dict[str, Any] = Depends(current_user),
         conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return transactions_service.save(conn, kind, _form(kind, body), user)
