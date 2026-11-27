"""032: a task bundle, out (docs/data-model-and-api.md §6.2) and in (§6.1)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from ..dto.bundles import BundleOut
from ..handlers import bundles as handler
from ..server.deps import Projects, Reviews, Rounds, Runs, Tasks, Transcripts

router = APIRouter()


async def bundle_body(request: Request) -> bytes:
    """The raw body, with no python-multipart: refused on an honest Content-Length, else as soon as the
    stream passes the cap."""
    length = request.headers.get("content-length", "")
    if length.isdigit():
        handler.check_size(int(length))
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        handler.check_size(len(body))
    return bytes(body)


@router.get("/api/tasks/{task_id}/export")
def export_task(task_id: int, tasks: Tasks, rounds: Rounds, reviews: Reviews, transcripts: Transcripts,
                with_transcripts: Annotated[bool, Query(alias="transcripts")] = False) -> Response:
    return Response(handler.export(tasks, rounds, reviews, transcripts, task_id, with_transcripts),
                    media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="task-{task_id}.zip"',
                             "X-Content-Type-Options": "nosniff"})


@router.post("/api/projects/{project_id}/import")
def import_bundle(project_id: int, body: Annotated[bytes, Depends(bundle_body)], projects: Projects, tasks: Tasks,
                  rounds: Rounds, reviews: Reviews, runs: Runs, transcripts: Transcripts) -> BundleOut:
    return handler.import_bundle(projects, tasks, rounds, reviews, runs, transcripts, project_id, body)
