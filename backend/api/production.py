"""Shifts (§7) and fixed assets (§8)."""

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends

from api.deps import current_user, get_conn, owner
from schemas.requests import AssetCreate, AssetLife, AssetPrice, DepreciationRun, ShiftForm
from schemas.responses import Ok, PostedRef
from services import assets_service, shifts_service

router = APIRouter(prefix="/api", tags=["production"])


@router.get("/shifts")
def list_shifts(user: dict[str, Any] = Depends(current_user), conn: sqlite3.Connection = Depends(get_conn)) -> list[dict[str, Any]]:
    return shifts_service.list_for(conn, user)


@router.post("/shifts")
def submit_shift(body: ShiftForm, user: dict[str, Any] = Depends(current_user),
                 conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return shifts_service.submit(conn, body.model_dump(), user)


@router.post("/shifts/{shift_id}/approve", response_model=PostedRef)
def approve_shift(shift_id: int, user: dict[str, Any] = Depends(owner), conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return shifts_service.approve(conn, shift_id, user)


@router.post("/shifts/{shift_id}/reject", response_model=Ok)
def reject_shift(shift_id: int, user: dict[str, Any] = Depends(owner), conn: sqlite3.Connection = Depends(get_conn)) -> Ok:
    shifts_service.reject(conn, shift_id, user)
    return Ok()


@router.get("/assets")
def assets(_: dict[str, Any] = Depends(owner), conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return assets_service.overview(conn)


@router.post("/assets")
def add_asset(body: AssetCreate, user: dict[str, Any] = Depends(owner), conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return assets_service.add(conn, body.model_dump(), user)


@router.post("/assets/{asset_id}/price")
def price_asset(asset_id: str, body: AssetPrice, user: dict[str, Any] = Depends(owner),
                conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return assets_service.set_price(conn, asset_id, body.model_dump(), user)


@router.post("/assets/{asset_id}/life")
def asset_life(asset_id: str, body: AssetLife, user: dict[str, Any] = Depends(owner),
               conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return assets_service.set_life(conn, asset_id, body.life, user)


@router.post("/depreciation", response_model=PostedRef)
def depreciation(body: DepreciationRun, user: dict[str, Any] = Depends(owner),
                 conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return assets_service.post_depreciation(conn, body.to, user)
