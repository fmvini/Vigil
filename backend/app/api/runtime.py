"""Public deployment timing, without credentials or operational gates."""

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["runtime"])


class RuntimeConfig(BaseModel):
    minimum_interval_seconds: int = Field(strict=True, ge=60, le=3600)
    scheduled_checks_interval_seconds: int | None = Field(strict=True, ge=1)


@router.get("/runtime-config", response_model=RuntimeConfig)
async def runtime_config(request: Request):
    settings = request.app.state.settings
    return RuntimeConfig(
        minimum_interval_seconds=settings.minimum_interval_seconds,
        scheduled_checks_interval_seconds=settings.scheduled_checks_interval_seconds,
    )
