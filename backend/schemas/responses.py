"""Response models for the small, stable endpoints.

Reports, home and analytics return nested data whose shape is documented in their
services; those endpoints declare ``dict[str, Any]``.
"""

from pydantic import BaseModel


class UserOut(BaseModel):
    id: int
    username: str
    label: str
    role: str
    roleLabel: str
    approver: bool
    active: bool


class PostedRef(BaseModel):
    id: int
    no: int


class SaveResult(BaseModel):
    posted: list[PostedRef]
    request: dict | None = None


class Ok(BaseModel):
    ok: bool = True
