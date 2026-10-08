from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import func, select

from app.api.dependencies import DB, Auth, MutationAuth
from app.api.schemas import (
    MonitorCreate,
    MonitorOut,
    MonitorPatch,
    Page,
    ProjectCreate,
    ProjectOut,
    ProjectPatch,
)
from app.db.models import Monitor, Project
from app.services import resources as service

router = APIRouter(tags=["resources"])


@router.get("/projects", response_model=Page[ProjectOut])
async def list_projects(
    db: DB,
    auth: Auth,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=2**63 - 1),
):
    filters = (Project.owner_id == auth.user.id, Project.archived_at.is_(None))
    total = await db.scalar(select(func.count()).select_from(Project).where(*filters))
    items = (
        await db.scalars(
            select(Project)
            .where(*filters)
            .order_by(Project.created_at, Project.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return Page[ProjectOut](items=[ProjectOut.model_validate(p) for p in items], total=total)


@router.post("/projects", status_code=201, response_model=ProjectOut)
async def create_project(data: ProjectCreate, db: DB, auth: MutationAuth):
    return ProjectOut.model_validate(await service.create_project(db, auth.user.id, data))


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(project_id: UUID, db: DB, auth: Auth):
    return ProjectOut.model_validate(await service.owned_project(db, auth.user.id, project_id))


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def patch_project(project_id: UUID, data: ProjectPatch, db: DB, auth: MutationAuth):
    project = await service.owned_project(db, auth.user.id, project_id, lock=True)
    changes = data.model_dump(exclude_unset=True)
    if any(getattr(project, field) != value for field, value in changes.items()):
        for field, value in changes.items():
            setattr(project, field, value)
        project.revision += 1
        await db.flush()
        await db.refresh(project)
        service.queue_invalidation(db, project)
    return ProjectOut.model_validate(project)


@router.delete("/projects/{project_id}", status_code=204)
async def archive_project(project_id: UUID, db: DB, auth: MutationAuth):
    project = await service.owned_project(
        db, auth.user.id, project_id, lock=True, include_archived=True
    )
    await service.archive_project(db, project)
    return Response(status_code=204)


@router.get("/projects/{project_id}/monitors", response_model=Page[MonitorOut])
async def list_monitors(
    project_id: UUID,
    db: DB,
    auth: Auth,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=2**63 - 1),
):
    await service.owned_project(db, auth.user.id, project_id)
    filters = (Monitor.project_id == project_id, Monitor.archived_at.is_(None))
    total = await db.scalar(select(func.count()).select_from(Monitor).where(*filters))
    items = (
        await db.scalars(
            select(Monitor)
            .where(*filters)
            .order_by(Monitor.created_at, Monitor.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return Page[MonitorOut](items=[service.monitor_output(m) for m in items], total=total)


@router.post("/projects/{project_id}/monitors", status_code=201, response_model=MonitorOut)
async def create_monitor(
    project_id: UUID, data: MonitorCreate, request: Request, db: DB, auth: MutationAuth
):
    monitor = await service.create_monitor(
        db,
        auth.user.id,
        project_id,
        data,
        minimum_interval_seconds=request.app.state.settings.minimum_interval_seconds,
    )
    return service.monitor_output(monitor)


@router.get("/monitors/{monitor_id}", response_model=MonitorOut)
async def get_monitor(monitor_id: UUID, db: DB, auth: Auth):
    _, monitor = await service.owned_monitor(db, auth.user.id, monitor_id)
    return service.monitor_output(monitor)


@router.patch("/monitors/{monitor_id}", response_model=MonitorOut)
async def patch_monitor(
    monitor_id: UUID, data: MonitorPatch, request: Request, db: DB, auth: MutationAuth
):
    project, monitor = await service.owned_monitor(db, auth.user.id, monitor_id, lock=True)
    return service.monitor_output(
        await service.patch_monitor(
            db,
            project,
            monitor,
            data,
            minimum_interval_seconds=request.app.state.settings.minimum_interval_seconds,
        )
    )


@router.delete("/monitors/{monitor_id}", status_code=204)
async def archive_monitor(monitor_id: UUID, db: DB, auth: MutationAuth):
    project, monitor = await service.owned_monitor(
        db, auth.user.id, monitor_id, lock=True, include_archived=True
    )
    await service.archive_monitor(db, project, monitor)
    return Response(status_code=204)


@router.post("/monitors/{monitor_id}/pause", response_model=MonitorOut)
async def pause_monitor(monitor_id: UUID, db: DB, auth: MutationAuth):
    project, monitor = await service.owned_monitor(db, auth.user.id, monitor_id, lock=True)
    return service.monitor_output(await service.set_paused(db, project, monitor, True))


@router.post("/monitors/{monitor_id}/resume", response_model=MonitorOut)
async def resume_monitor(monitor_id: UUID, db: DB, auth: MutationAuth):
    project, monitor = await service.owned_monitor(db, auth.user.id, monitor_id, lock=True)
    return service.monitor_output(await service.set_paused(db, project, monitor, False))
