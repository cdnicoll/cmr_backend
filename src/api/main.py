"""FastAPI application entry point."""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from src.middleware.metrics import MetricsMiddleware
from src.middleware.request_id import RequestIDMiddleware
from src.models.common import ErrorResponse


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan."""
    yield


app = FastAPI(
    title="CMR Backend",
    description="CMR API with resources and Modal pipeline workers",
    version="0.1.0",
    lifespan=lifespan,
)

# Middleware order (last added = outermost): RequestID → Metrics → CORS
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.add_middleware(MetricsMiddleware)
app.add_middleware(RequestIDMiddleware)

from src.api.routes import health
from src.api.routes.resources import router as resources_router

app.include_router(health.router)
app.include_router(resources_router, prefix="/api/v1")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global error handler; MUST pass request_id into ErrorResponse."""
    from fastapi.responses import JSONResponse

    request_id = getattr(request.state, "request_id", None)
    err = ErrorResponse(
        error="internal_error",
        message="An internal error occurred. Please try again later.",
        request_id=request_id,
    )
    return JSONResponse(status_code=500, content=err.model_dump())
