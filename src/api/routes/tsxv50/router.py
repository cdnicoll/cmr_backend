"""TSXV50 snapshot API router."""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from src.api.dependencies import get_tsxv50_token
from src.services.supabase.tsxv50_dao import get_latest_snapshot, insert_snapshot

router = APIRouter(prefix="/tsxv50", tags=["tsxv50"])


class SnapshotRequest(BaseModel):
    symbols: list[str]

    @field_validator("symbols")
    @classmethod
    def symbols_non_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("symbols must not be empty")
        return v


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
    row = await insert_snapshot(body.symbols)
    return JSONResponse(content=_serialize(row), status_code=status.HTTP_201_CREATED)
