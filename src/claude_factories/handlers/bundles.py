"""032: a task as a zip bundle. Export writes 031's job-folder layout (docs/data-model-and-api.md §6.2) and a
task.json with what the folders can't hold. Import checks every entry, unpacks the zip into a temp folder, and
runs it through 031's reader and writer, keyed on `tasks.import_key` (docs/data-model-and-api.md §6.1, §6.2;
docs/MVP.md §4.5). Every check comes before the first write, so a refusal writes nothing (Q7)."""

import io
import json
import os
import re
import shutil
import stat
import tempfile
import zipfile
import zlib
from datetime import UTC, datetime
from pathlib import Path

from .. import config
from ..domain.enums import STAGE_STATUS, Reviewer, Status
from ..domain.errors import Conflict, Invalid, NotFound, TooLarge
from ..dto.bundles import BundleOut
from ..repositories.projects import ProjectsRepo
from ..repositories.reviews import ReviewsRepo
from ..repositories.rounds import RoundsRepo
from ..repositories.runs import RunsRepo
from ..repositories.tasks import TasksRepo
from ..repositories.transcripts import TranscriptsRepo
from .factory_import import STAGES, STATUSES, TIME, copy_transcripts, job_files, read, save, short
from .transcripts import SESSION, copy, load

N = r"[1-9][0-9]{0,8}"  # 031 Q7
FILES = re.compile(rf"task\.json|spec\.md|decision\.md|feedback-{N}\.md"
                   rf"|round-{N}/(?:build\.md|diff\.patch|review-(?:{'|'.join(Reviewer)})\.md)")
ROUND_DIR = re.compile(rf"round-{N}/")
SEGMENT = re.compile(r"[A-Za-z0-9._-]+")
KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9:._@-]{0,199}")  # Q7
ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)  # the earliest time a ZIP entry can hold


# --- Export (Q1–Q4, Q8) --------------------------------------------------------------------


def zip_time(at: str | None) -> tuple:
    """Q4: a row's created_at as a ZIP date_time. ZIP keeps 2-second steps, so an odd second rounds down."""
    try:
        t = datetime.strptime((at or "")[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return ZIP_EPOCH
    if not 1980 <= t.year <= 2107:
        return ZIP_EPOCH
    return (t.year, t.month, t.day, t.hour, t.minute, t.second - t.second % 2)


def zipped(entries: list[tuple]) -> bytes:
    """(name, created_at, content) per entry, in order; a None content is a folder."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, at, content in entries:
            info = zipfile.ZipInfo(name, zip_time(at))
            if content is None:
                info.external_attr = (0o40755 << 16) | 0x10  # a folder, as `zip` marks one
                info.CRC = info.compress_size = 0  # mkdir sets these only for a name
                zf.mkdir(info)
            else:
                info.external_attr = 0o644 << 16
                zf.writestr(info, content, zipfile.ZIP_DEFLATED)
    return buf.getvalue()


def export(tasks: TasksRepo, rounds: RoundsRepo, reviews: ReviewsRepo, transcripts: TranscriptsRepo, task_id: int,
           with_transcripts: bool) -> bytes:
    """The task's bundle: task.json, then 031's files, then (on request) its transcripts' copies."""
    task = tasks.for_export(task_id)
    if task is None:
        raise NotFound(f"Task #{task_id} not found")
    made = task["created_at"]
    entries = [] if task["spec_md"] is None else [("spec.md", made, task["spec_md"])]
    found = rounds.all(task_id)
    for r in found:
        folder = f"round-{r['n']}/"
        entries.append((folder, r["created_at"], None))
        if r["build_md"] is not None:
            entries.append((f"{folder}build.md", r["created_at"], r["build_md"]))
        entries.append((f"{folder}diff.patch", r["created_at"], "".join(rounds.patches(r["id"]))))
    for v in reviews.export_verdicts(task_id):
        entries.append((f"round-{v['n']}/review-{v['reviewer']}.md", v["created_at"],
                        f"VERDICT: {v['verdict']}\n\n{v['body_md']}\n"))
    # Q3: my latest change request per round, as feedback on the next; the approver's latest decision, only
    # when it's on the highest round, where 031 reads decision.md
    decisions = reviews.task_decisions(task_id)
    feedback = {d["round"] + 1: d for d in decisions if (d["actor"], d["decision"]) == ("me", "CHANGES_REQUESTED")}
    entries += [(f"feedback-{n}.md", d["created_at"], d["body_md"]) for n, d in sorted(feedback.items())]
    approver = [d for d in decisions if d["actor"] == "approver"]
    if approver and approver[-1]["round"] == found[-1]["n"]:
        d = approver[-1]
        entries.append(("decision.md", d["created_at"], f"{d['decision']}\n\n{d['body_md']}\n"))
    data = {
        "import_key": task["import_key"] or f"task:{task['id']}@{made}",  # Q2: not stored
        "title": task["title"], "description_md": task["description_md"], "status": task["status"],
        "stage": task["stage"], "events": [dict(e) for e in tasks.events(task_id)],
        "comments": [dict(c) for c in reviews.task_comments(task_id)],
    }
    if with_transcripts:
        data["transcripts"] = []
        for t in transcripts.for_export(task_id):
            try:  # Q8: read through 030's containment; a missing copy is left out
                content = copy(transcripts, t["id"])[1].read_bytes()
            except (NotFound, OSError):
                continue
            entries.append((f"transcripts/{t['path']}", t["started_at"] or made, content))
            data["transcripts"].append({k: t[k] for k in ("path", "session_id", "agent_type", "name", "round")})
    return zipped([("task.json", made, json.dumps(data, ensure_ascii=False, indent=1) + "\n"), *entries])


# --- Checking and unpacking the zip (Q1, Q7) --------------------------------------------------


def check_size(size: int) -> None:
    """Q7: the raw body's cap, on its Content-Length and again as the stream comes in."""
    if size > config.MAX_BUNDLE:
        raise TooLarge("bundle over 50 MB")


def bad_entry(name: str, problem: str) -> Invalid:
    return Invalid(f"bundle entry {short(name)} {problem}")


def safe_segments(path: str) -> bool:
    return all(SEGMENT.fullmatch(p) and p not in (".", "..") for p in path.split("/"))


def transcript_path(path: str) -> bool:
    """Q7: `<segment>/…/<name>.jsonl`."""
    return "/" in path and path.endswith(".jsonl") and safe_segments(path)


def known(name: str) -> bool:
    """Q1: a name the layout has. Folders are `round-<N>/` or lie under transcripts/."""
    if name.startswith("transcripts/"):
        rest = name.removeprefix("transcripts/")
        return rest == "" or (safe_segments(rest[:-1]) if rest.endswith("/") else transcript_path(rest))
    return bool(ROUND_DIR.fullmatch(name) or FILES.fullmatch(name))


def checked(zf: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    """Every entry's name, kind, and encoding, then the declared sizes' sum. Whether task.json lists a
    transcripts/ file is checked once it's read."""
    infos, seen = zf.infolist(), set()
    for info in infos:
        name = info.filename
        if name.startswith("/") or ".." in name.split("/"):
            raise bad_entry(name, "is unsafe")
        if stat.S_ISLNK(info.external_attr >> 16):
            raise bad_entry(name, "is a symlink")
        if not known(name):
            raise Invalid(f"unknown bundle entry {short(name)}")
        if name in seen:
            raise bad_entry(name, "appears twice")
        seen.add(name)
        if info.flag_bits & 0x1:
            raise bad_entry(name, "can't be read: it is encrypted")
        if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise bad_entry(name, "can't be read: its compression isn't stored or deflated")
    # zipfile stops reading an entry at its declared size, so this sum bounds the disk the unpack uses
    if sum(i.file_size for i in infos) > config.MAX_UNPACKED:
        raise TooLarge("bundle unpacks to over 500 MB")
    return infos


def unpack(zf: zipfile.ZipFile, infos: list[zipfile.ZipInfo], root: Path) -> None:
    """Every entry under `root`, then Q4: each one's mtime from its entry, folders after their files."""
    for info in infos:
        dest = root / info.filename
        try:
            if info.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
        except (zipfile.BadZipFile, zlib.error, EOFError, OSError) as e:  # a bad CRC, a cut-off entry, a clash
            raise bad_entry(info.filename, f"can't be read: {e}")
    for info in sorted(infos, key=lambda i: i.is_dir()):
        try:
            at = datetime(*info.date_time, tzinfo=UTC).timestamp()
        except ValueError:
            raise bad_entry(info.filename, "has a bad date")
        os.utime(root / info.filename, (at, at))


# --- task.json (AC39) -------------------------------------------------------------------------


def is_time(v) -> bool:
    """db.now()'s format exactly, so stored times keep sorting as text."""
    try:
        return isinstance(v, str) and datetime.strptime(v, TIME).strftime(TIME) == v
    except ValueError:
        return False


def one_of(values):
    return lambda v: isinstance(v, str) and v in values


def maybe(ok):
    return lambda v: v is None or ok(v)


def text(v) -> bool:
    return isinstance(v, str)


def filled(v) -> bool:
    return isinstance(v, str) and v.strip() != ""


def count(v) -> bool:
    """A round or line number SQLite can store."""
    return type(v) is int and 0 < v < 2**31


EVENT = {"actor": filled, "from_status": maybe(one_of(STATUSES)), "to_status": one_of(STATUSES),
         "stage": maybe(one_of(STAGES)), "created_at": is_time}
COMMENT = {"round": count, "author": filled, "path": maybe(filled), "line": maybe(count),
           "side": maybe(one_of(("old", "new"))), "body_md": text, "created_at": is_time}
TRANSCRIPT = {"path": lambda v: isinstance(v, str) and transcript_path(v),
              "session_id": lambda v: isinstance(v, str) and bool(SESSION.fullmatch(v)),
              "agent_type": maybe(text), "name": maybe(text), "round": maybe(count)}


def want(obj: dict, key: str, ok, where: str = ""):
    """obj[key] when `ok` takes it, else a 422 naming the field and showing its value."""
    value = obj.get(key)
    if not ok(value):
        raise Invalid(f"task.json: bad {where}{key} {short(value)}")
    return value


def rows(data: dict, key: str, fields: dict) -> list[dict]:
    """A list of objects (missing = none), each cut to `fields` and checked by them."""
    found = data.get(key, [])
    if not isinstance(found, list):
        raise Invalid(f"task.json: {key} must be a list")
    for i, item in enumerate(found):
        if not isinstance(item, dict):
            raise Invalid(f"task.json: {key}[{i}] must be an object")
    return [{k: want(item, k, ok, f"{key}[{i}].") for k, ok in fields.items()} for i, item in enumerate(found)]


def task_json(root: Path, files: set[str], rounds: set[int]) -> dict:
    """The checked task.json. `files` are the bundle's file entries, `rounds` the n of its round folders."""
    found = read(root, root / "task.json", "task.json")  # 031's reader: 413 over 5 MB
    if found is None:
        raise Invalid("bundle has no task.json")
    try:
        data = json.loads(found)
    except (ValueError, RecursionError):
        raise Invalid("task.json isn't valid JSON")
    if not isinstance(data, dict):
        raise Invalid("task.json must be an object")
    out = {"import_key": want(data, "import_key", lambda v: isinstance(v, str) and bool(KEY.fullmatch(v))),
           "title": want(data, "title", filled), "description_md": want(data, "description_md", text),
           "status": want(data, "status", one_of(STATUSES)), "stage": want(data, "stage", maybe(one_of(STAGES))),
           "events": rows(data, "events", EVENT), "comments": rows(data, "comments", COMMENT),
           "transcripts": rows(data, "transcripts", TRANSCRIPT)}
    if out["stage"] is not None and STAGE_STATUS[out["stage"]] != out["status"]:  # §5.2
        raise Invalid(f"task.json: stage {short(out['stage'])} doesn't go with status {short(out['status'])}")
    for i, c in enumerate(out["comments"]):
        if c["round"] not in rounds:
            raise Invalid(f"task.json: comments[{i}].round {c['round']} has no round-{c['round']}/ folder")
        if len({c[k] is None for k in ("path", "line", "side")}) > 1:
            raise Invalid(f"task.json: comments[{i}] sets only some of path, line, and side")
    listed = {t["path"] for t in out["transcripts"]}
    for i, t in enumerate(out["transcripts"]):
        if f"transcripts/{t['path']}" not in files:
            raise Invalid(f"task.json: transcripts[{i}].path {short(t['path'])} has no entry in the bundle")
    for name in sorted(files):
        if name.startswith("transcripts/") and name.removeprefix("transcripts/") not in listed:
            raise Invalid(f"unknown bundle entry {short(name)}: task.json doesn't list it")
    return out


# --- Import (Q2, Q5, Q6, Q8) ------------------------------------------------------------------


def sessions(root: Path, listed: list[dict]) -> dict:
    """Q8: copy_transcripts' input, one run per session_id, timed from its earliest and latest transcript.
    Each copy goes to `<new run id>/<its path after the first segment>`."""
    found: dict[str, list] = {}
    for t in listed:
        source = root / "transcripts" / t["path"]
        got = load(source) or {}
        found.setdefault(t["session_id"], []).append(
            {"source": source, "rel": t["path"].split("/", 1)[1], "agent_type": t["agent_type"], "name": t["name"],
             "round": t["round"], "started_at": got.get("started_at"), "ended_at": got.get("ended_at")})
    return {s: {"started_at": min((t["started_at"] for t in ts if t["started_at"]), default=None),
                "ended_at": max((t["ended_at"] for t in ts if t["ended_at"]), default=None), "transcripts": ts}
            for s, ts in found.items()}


def land(status: str, stage: str | None, events: list[dict], now: str) -> tuple[str, str | None, list[dict]]:
    """§5.2, Q5: done and review keep their status and stage. Anything else lands in backlog with no stage,
    plus an app event when that changes the status."""
    if status in (Status.DONE, Status.REVIEW, Status.BACKLOG):
        return status, stage, events
    return Status.BACKLOG.value, None, [*events, {"actor": "app", "from_status": status, "to_status": "backlog",
                                                  "stage": None, "created_at": now}]


def import_bundle(projects: ProjectsRepo, tasks: TasksRepo, rounds: RoundsRepo, reviews: ReviewsRepo, runs: RunsRepo,
                  transcripts: TranscriptsRepo, project_id: int, body: bytes) -> BundleOut:
    if projects.for_code(project_id) is None:
        raise NotFound(f"Project #{project_id} not found")
    try:
        zf = zipfile.ZipFile(io.BytesIO(body))
    except (zipfile.BadZipFile, OSError, ValueError, EOFError):
        raise Invalid("not a zip file")
    with zf, tempfile.TemporaryDirectory(prefix="fctl-bundle-") as tmp:  # removed however this ends
        root = Path(os.path.realpath(tmp))
        infos = checked(zf)
        unpack(zf, infos, root)
        f = job_files(root, root) | {"base_sha": "unknown"}  # Q3
        data = task_json(root, {i.filename for i in infos if not i.is_dir()}, {r["n"] for r in f["rounds"]})
        by_session = sessions(root, data["transcripts"])
        key = data["import_key"]
        now = tasks.lock()
        task = tasks.by_import_key(key)
        if task and task["project_id"] != project_id:  # 031 Q11
            raise Conflict(f"{key} is imported in project #{task['project_id']}")
        if task and (run := runs.running(task["id"])):  # Q6: overwriting it would lose the run's work
            raise Conflict(f"run #{run['id']} active")
        status, stage, events = land(data["status"], data["stage"], data["events"], now)
        done = [e["created_at"] for e in events if e["to_status"] == Status.DONE]
        task_id = save(tasks, rounds, reviews, task, {  # Q4: the task's times come from its events
            "project_id": project_id, "import_key": key, "title": data["title"],
            "description_md": data["description_md"], "spec_md": f["spec_md"], "status": status, "stage": stage,
            "branch": None, "created_at": events[0]["created_at"] if events else now,
            "updated_at": events[-1]["created_at"] if events else now,
            "done_at": (done[-1] if done else now) if status == Status.DONE else None,
        }, events, f)
        ids = {r["n"]: r["id"] for r in rounds.all(task_id)}
        reviews.replace_comments(task_id, [c | {"round_id": ids[c["round"]]} for c in data["comments"]])  # Q6
        copied = copy_transcripts(runs, transcripts, task_id, by_session, now)
    return BundleOut(task_id=task_id, title=data["title"], import_key=key, created=task is None, status=status,
                     rounds=len(f["rounds"]), transcripts=copied)
