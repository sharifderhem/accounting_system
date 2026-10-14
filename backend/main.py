"""Application entry point: lifespan, middleware, routers and the static frontend."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from api import approvals, auth, books, production, settings as settings_api, transactions
from config import settings
from database import Database
from migrations.migrations import migrate
from services import auth_service, settings_service
from utils.errors import DomainError

logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = Database.connect()
    try:
        version = migrate(conn)
        logger.info("Database ready at schema version %s", version)
        settings_service.seed(conn, settings.owner_name)
        auth_service.ensure_owner(conn, settings.owner_username, settings.owner_password, settings.owner_name)
    finally:
        conn.close()
    yield


app = FastAPI(title="دفتر مصنع جوان", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def guard(request: Request, call_next):
    # Cross-site requests cannot add custom headers without CORS (which is not enabled),
    # so requiring one on every write blocks cross-site form posts.
    if request.url.path.startswith("/api/") and request.method in UNSAFE_METHODS \
            and request.headers.get("x-requested-with") != "fetch":
        return JSONResponse({"detail": "طلب غير مسموح"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
        "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(DomainError)
async def domain_error(_: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse({"detail": exc.message, "field": exc.field}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
@app.exception_handler(ValidationError)
async def validation_error(_: Request, exc: ValidationError | RequestValidationError) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
    return JSONResponse({"detail": "بيانات غير صحيحة في النموذج", "field": field or None}, status_code=422)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


for module in (auth, settings_api, transactions, approvals, production, books):
    app.include_router(module.router)

frontend = Path(settings.frontend_dir)
if frontend.is_dir():
    app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
else:
    logger.warning("Frontend folder %s not found; serving the API only.", frontend)
