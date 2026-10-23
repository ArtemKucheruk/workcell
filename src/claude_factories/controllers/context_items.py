"""docs/data-model-and-api.md §6.1: a project's context cards and groups (057). The pinned card is
`GET`/`PUT /api/projects/{id}/context`, in controllers/projects.py."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from ..dto.context_items import ContextItemOut, ContextItemPatch, FromPathBody, NewContextItem, ParentId
from ..handlers import context_items as handler
from ..server.deps import ContextItems, Projects, Tasks

router = APIRouter()


async def card_body(request: Request) -> bytes:
    """bundles.bundle_body with the 16 KB card cap: refused on an honest Content-Length, else as soon as the
    stream passes it."""
    length = request.headers.get("content-length", "")
    if length.isdigit():
        handler.check_size(int(length))
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        handler.check_size(len(body))
    return bytes(body)


@router.get("/api/projects/{project_id}/context/items")
def list_items(project_id: int, projects: Projects, items: ContextItems) -> list[ContextItemOut]:
    return handler.list_items(projects, items, project_id)


@router.post("/api/projects/{project_id}/context/items", status_code=201)
def create_item(project_id: int, body: NewContextItem, projects: Projects, items: ContextItems,
                tasks: Tasks) -> ContextItemOut:
    return handler.create(projects, items, tasks, project_id, body)


@router.post("/api/projects/{project_id}/context/items/upload", status_code=201)
def upload_item(project_id: int, name: str, body: Annotated[bytes, Depends(card_body)], projects: Projects,
                items: ContextItems, tasks: Tasks, parent_id: Annotated[ParentId, Query()] = None) -> ContextItemOut:
    return handler.upload(projects, items, tasks, project_id, name, parent_id, body)


@router.post("/api/projects/{project_id}/context/items/from-path", status_code=201)
def items_from_path(project_id: int, body: FromPathBody, projects: Projects, items: ContextItems,
                    tasks: Tasks) -> list[ContextItemOut]:
    return handler.from_path(projects, items, tasks, project_id, body.path, body.parent_id)


@router.patch("/api/context/items/{item_id}")
def patch_item(item_id: int, body: ContextItemPatch, items: ContextItems, tasks: Tasks) -> ContextItemOut:
    return handler.patch(items, tasks, item_id, body)


@router.delete("/api/context/items/{item_id}", status_code=204)
def delete_item(item_id: int, items: ContextItems) -> None:
    handler.delete(items, item_id)


@router.post("/api/context/items/{item_id}/reload")
def reload_item(item_id: int, items: ContextItems, tasks: Tasks) -> ContextItemOut:
    return handler.reload(items, tasks, item_id)
