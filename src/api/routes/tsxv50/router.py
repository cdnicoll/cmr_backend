"""TSXV50 snapshot API router."""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from src.api.dependencies import get_tsxv50_token
from src.api.schemas.tsxv50 import SnapshotRequest
from src.services.supabase.tsxv50_dao import get_latest_snapshot, insert_snapshot_entries

router = APIRouter(prefix="/tsxv50", tags=["tsxv50"])


def _serialize(row: dict) -> dict:
    return {
        k: v.isoformat() if isinstance(v, datetime) else str(v) if isinstance(v, UUID) else v
        for k, v in row.items()
    }


@router.get("/snapshot")
async def get_snapshot(_: None = Depends(get_tsxv50_token)) -> JSONResponse:
    row = await get_latest_snapshot()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No snapshot found")
    return JSONResponse(content=_serialize(row))


@router.post("/snapshot", status_code=201)
async def post_snapshot(body: SnapshotRequest, _: None = Depends(get_tsxv50_token)) -> JSONResponse:
    entries = [entry.model_dump() for entry in body.entries]
    row = await insert_snapshot_entries(entries)
    return JSONResponse(content=_serialize(row), status_code=status.HTTP_201_CREATED)
