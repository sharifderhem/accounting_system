"""One-time prototype import. Protected by the IMPORT_TOKEN environment variable, not by a login."""

import hmac
import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from api.deps import get_conn
from config import settings
from services import import_service

router = APIRouter(prefix="/api/admin", tags=["admin"])

IMPORT_PATH = "/api/admin/import"


@router.post("/import")
async def import_export(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    if not settings.import_token:
        raise HTTPException(status_code=404, detail="Not Found")
    token = request.headers.get("x-import-token") or ""
    if not hmac.compare_digest(token.encode(), settings.import_token.encode()):
        raise HTTPException(status_code=403, detail="رمز الاستيراد غير صحيح")
    raw = await request.body()
    return await run_in_threadpool(import_service.import_export, conn, raw)
