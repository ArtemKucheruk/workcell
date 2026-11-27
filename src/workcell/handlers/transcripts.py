"""030: a run's Claude Code transcripts, copied into FCTL_HOME/transcripts/<run-id>/ and indexed when the run
ends (docs/MVP.md §4.4), then listed per task and shown one at a time (docs/data-model-and-api.md §6.2).

Claude Code prunes old transcripts and the worktree gets removed, so the copies are the record."""

import json
import re
import threading
from pathlib import Path

from .. import config
from ..domain.errors import NotFound
from ..dto.transcripts import TranscriptDetail, TranscriptOut
from ..lib.transcript import agent_types, events, folder_name, messages, summary
from ..repositories.claude_accounts import ClaudeAccountsRepo
from ..repositories.tasks import TasksRepo
from ..repositories.transcripts import TranscriptsRepo

SESSION = re.compile(r"[A-Za-z0-9-]+")  # a session id that can't step out of the folder
# ponytail: one lock for every collect, so Stop's and the exit thread's copies of a run never interleave;
# collects are short and rare
COLLECTING = threading.Lock()


def store() -> Path:
    return config.data_dir() / "transcripts"


def jsonl(path: Path) -> bool:
    """A regular .jsonl file. AC14: a symlink is never followed."""
    return path.suffix == ".jsonl" and not path.is_symlink() and path.is_file()


def load(path: Path) -> dict | None:
    """The file's bytes, its events, and its summary, read once so the copy and its row agree; None if
    it can't be read (Q7)."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    evts = events(data)
    return {"source": path, "data": data, "events": evts} | summary(evts)


def agent_type(meta: Path) -> str | None:
    """AC5: a subagent's `agentType` from its meta.json; None when that is missing, a symlink, or unparsable."""
    try:
        found = None if meta.is_symlink() else json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return None
    kind = found.get("agentType") if isinstance(found, dict) else None
    return kind if isinstance(kind, str) else None


def subagents(folder: Path, session: str) -> list[dict]:
    """A session's `<session>/subagents/agent-*.jsonl`, skipped whole if either directory is a symlink."""
    sub = folder / session / "subagents"
    if (folder / session).is_symlink() or sub.is_symlink() or not sub.is_dir():
        return []
    found = []
    for path in sorted(sub.glob("agent-*.jsonl")):
        if jsonl(path) and (got := load(path)):
            found.append(got | {"agent_type": agent_type(path.with_suffix(".meta.json")), "name": None})
    return found


def sources(folder: Path, session: str) -> list[dict]:
    """The run's main session, its teammates (Q2: top-level sessions whose first teamName is
    `session-<session[:8]>`), and each one's subagents."""
    if folder.is_symlink() or not folder.is_dir():
        return []
    main = folder / f"{session}.jsonl"
    lead = load(main) if jsonl(main) else None
    found = [lead | {"agent_type": "orchestrator", "name": None}] if lead else []
    types = agent_types(lead["events"]) if lead else {}
    team, sessions = f"session-{session[:8]}", [session]
    # ponytail: reads every top-level session in the worktree's folder to find teammates; read only up to
    # each file's first teamName line if folders get big
    for path in sorted(folder.glob("*.jsonl")):
        if path != main and jsonl(path) and (mate := load(path)) and mate["team_name"] == team:
            found.append(mate | {"agent_type": types.get(mate["agent_name"]), "name": mate["agent_name"]})
            sessions.append(path.stem)
    return found + [s for name in sessions for s in subagents(folder, name)]


def collect(tx, run_id: int) -> None:
    """Q7: copy the run's transcripts from the worktree's Claude Code folder (Q1), in the run's own account's
    config dir (096 AC22), else the active account's (056; a pre-096 run, AC23), to `<run-id>/` under the
    store, mirroring the folder's layout (Q8), and upsert one row per copy. Called after the run's own row is
    written; an OSError leaves that file out (or all of them) and never fails the caller. No account copies
    nothing (056 Q8)."""
    with COLLECTING:
        with tx() as conn:
            run = TranscriptsRepo(conn).source(run_id)
            active = ClaudeAccountsRepo(conn).active()
        config_dir = run and run["config_dir"] or active and active["config_dir"]
        if run is None or not config_dir or not run["worktree_path"] or not SESSION.fullmatch(run["session_id"]):
            return
        folder = Path(config_dir) / "projects" / folder_name(run["worktree_path"])
        try:
            found = sources(folder, run["session_id"])
        except OSError:
            return
        rows = []
        for f in found:
            path = Path(str(run_id), f["source"].relative_to(folder))
            dest = store() / path
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(f["data"])
            except OSError:
                continue
            rows.append(f | {"run_id": run_id, "task_id": run["task_id"], "path": path.as_posix()})
        with tx() as conn:
            repo = TranscriptsRepo(conn)
            for row in rows:
                repo.upsert(row)


def for_task(tasks: TasksRepo, transcripts: TranscriptsRepo, task_id: int) -> list[TranscriptOut]:
    """The task page's Agents (Q11): ordered by run, then start, then id."""
    if not tasks.exists(task_id):
        raise NotFound(f"Task #{task_id} not found")
    return [TranscriptOut(**r) for r in transcripts.for_task(task_id)]


def copy(transcripts: TranscriptsRepo, transcript_id: int) -> tuple:
    """The row and its copy's path. docs/MVP.md §4.5: a path that resolves outside the store is never read."""
    row = transcripts.get(transcript_id)
    if row is None:
        raise NotFound(f"Transcript #{transcript_id} not found")
    root = store().resolve()
    path = (root / row["path"]).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise NotFound(f"Transcript #{transcript_id} file missing")
    return row, path


def detail(transcripts: TranscriptsRepo, transcript_id: int, full: bool) -> TranscriptDetail:
    row, path = copy(transcripts, transcript_id)
    try:
        data = path.read_bytes()
    except OSError:
        raise NotFound(f"Transcript #{transcript_id} file missing")
    # ponytail: the whole transcript in one response; page it if transcripts get big enough to hurt
    return TranscriptDetail(**row, messages=messages(events(data), full))


def raw(transcripts: TranscriptsRepo, transcript_id: int) -> Path:
    return copy(transcripts, transcript_id)[1]
