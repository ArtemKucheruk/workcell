"""docs/data-model-and-api.md §6.2: a task's transcripts, one transcript's messages, and its raw copy (030)."""

from fastapi import APIRouter
from fastapi.responses import FileResponse

from ..dto.transcripts import TranscriptDetail, TranscriptOut
from ..handlers import transcripts as handler
from ..server.deps import Tasks, Transcripts

router = APIRouter()


@router.get("/api/tasks/{task_id}/transcripts")
def task_transcripts(task_id: int, tasks: Tasks, transcripts: Transcripts) -> list[TranscriptOut]:
    return handler.for_task(tasks, transcripts, task_id)


@router.get("/api/transcripts/{transcript_id}")
def transcript(transcript_id: int, transcripts: Transcripts, full: bool = False) -> TranscriptDetail:
    return handler.detail(transcripts, transcript_id, full)


@router.get("/api/transcripts/{transcript_id}/raw")
def raw(transcript_id: int, transcripts: Transcripts) -> FileResponse:
    """The copy as a download, never sniffed as HTML."""
    return FileResponse(handler.raw(transcripts, transcript_id), media_type="application/x-ndjson",
                        filename=f"transcript-{transcript_id}.jsonl", headers={"X-Content-Type-Options": "nosniff"})
