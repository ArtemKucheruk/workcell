"""031: fctl import-factory. The bootstrap factory's records, `<project>/factory/board.json` and
`factory/jobs/<id>/` (FACTORY.md "Target file system"), become tasks with their events, rounds, round_files,
verdicts, and decisions, and each job's Claude Code transcripts are copied the 030 way. A rerun rewrites the
same rows, keyed on `tasks.import_key` `factory:<job id>` (Q3). Everything is read and checked before the
first write, so a refusal writes nothing (Q7).
058: `{}` also reads `factory/backlog.md`, whose lines board.json doesn't list become backlog-only tasks under the
same key, and the board's view-model runs it when either file changes (`sync`)."""

import json
import os
import re
import stat
from datetime import UTC, datetime
from pathlib import Path

from .. import config
from ..adapters.git import Git
from ..domain.enums import Reviewer, Stage, Status
from ..domain.errors import Conflict, DomainError, Invalid, NotFound, TooLarge
from ..dto.factory import ImportedJob, ImportOut
from ..lib.backlog import ID, parse
from ..lib.patch import split_patch
from ..lib.transcript import agent_types, first_prompt, folder_name
from ..repositories.projects import ProjectsRepo
from ..repositories.reviews import ReviewsRepo
from ..repositories.rounds import RoundsRepo
from ..repositories.runs import RunsRepo
from ..repositories.tasks import TasksRepo
from ..repositories.transcripts import TranscriptsRepo
from .transcripts import SESSION, agent_type, jsonl, load, store

ROUND_DIR = re.compile(r"round-([1-9][0-9]{0,8})")
FEEDBACK = re.compile(r"feedback-([1-9][0-9]{0,8})\.md")
PULL = re.compile(r"/pull/([0-9]{1,9})\b")  # Q6
TIME = "%Y-%m-%dT%H:%M:%SZ"  # db.now()'s format (Q4)
STATUSES, STAGES = {s.value for s in Status}, {s.value for s in Stage}
FILES = ("board.json", "backlog.md")  # 058


# --- Reading factory/ (Q7) ---------------------------------------------------------------


def inside(root: Path, path: Path) -> bool:
    """`path` resolves inside `root`, itself a realpath."""
    return Path(os.path.realpath(path)).is_relative_to(root)


def read(root: Path, path: Path, label: str) -> str | None:
    """A regular file that resolves inside `root`, as text; None for anything else. 413 over 5 MB."""
    if not inside(root, path) or not path.is_file():
        return None
    try:
        with open(path, "rb") as f:
            data = f.read(config.MAX_PATCH + 1)
    except OSError:
        return None
    if len(data) > config.MAX_PATCH:
        raise TooLarge(f"{label} over 5 MB")
    return data.decode(errors="replace")


def mtime(path: Path) -> str:
    """Q4: when the file was last written, in UTC."""
    return datetime.fromtimestamp(path.stat().st_mtime, UTC).strftime(TIME)


def head(text: str) -> tuple[str, str]:
    """Q5: the first line and the rest, each stripped."""
    first, _, rest = text.partition("\n")
    return first.strip(), rest.strip()


def short(value) -> str:
    return json.dumps(value)[:100]


def bad_id(value, where: str = "") -> Invalid:
    return Invalid(f"{where}bad job id {short(value)}: use letters, digits, and dashes (up to 100),"
                   " starting with a letter or digit")


def factory_root(project_path: str) -> Path | None:
    """The realpath of factory/, or None when it resolves outside the project (Q7)."""
    root = Path(os.path.realpath(Path(project_path, "factory")))
    return root if root.is_relative_to(os.path.realpath(project_path)) else None


def mark(project_path: str) -> str | None:
    """058 Q10: board.json's and backlog.md's st_mtime_ns and st_size, `-` for a missing one; None with neither.
    It uses the import's containment, so a file outside factory/ counts as missing."""
    root, parts = factory_root(project_path), []
    for name in FILES:
        path = Path(project_path, "factory", name)
        try:
            st = path.stat()
        except OSError:
            st = None
        found = root and st and stat.S_ISREG(st.st_mode) and inside(root, path)
        parts.append(f"{name}:{st.st_mtime_ns}:{st.st_size}" if found else f"{name}:-")
    return None if all(p.endswith(":-") for p in parts) else " ".join(parts)


def board_jobs(text: str) -> list:
    """board.json's jobs; 422 when it isn't a JSON object with a jobs list."""
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):
        raise Invalid("factory/board.json isn't valid JSON")
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        raise Invalid('factory/board.json has no "jobs" list')
    return jobs


def checked(job) -> dict:
    """AC28: one board entry, else 422 naming the job and what's wrong. Status and stage are FACTORY.md's set,
    stored as given (§5.2)."""
    if not isinstance(job, dict):
        raise Invalid("factory/board.json: every job must be an object")
    jid = job.get("id")
    if not isinstance(jid, str) or not ID.fullmatch(jid):
        raise bad_id(jid, "factory/board.json: ")
    title = job.get("title")
    if not isinstance(title, str) or not title.strip():
        raise Invalid(f"job {jid} has no title")
    for key in ("description", "branch", "pr"):
        if not isinstance(job.get(key), str | None):
            raise Invalid(f"job {jid}: {key} must be a string or null")
    history = job.get("history") or []
    if not isinstance(history, list) or not all(isinstance(h, dict) and isinstance(h.get("at"), str) for h in history):
        raise Invalid(f"job {jid}: history must be a list of entries, each with an at")
    for entry in (job, *history):
        status, stage = entry.get("status"), entry.get("stage")
        if not (isinstance(status, str) and status in STATUSES):
            raise Invalid(f"job {jid} has unknown status {short(status)}")
        if stage is not None and not (isinstance(stage, str) and stage in STAGES):
            raise Invalid(f"job {jid} has unknown stage {short(stage)}")
    return job | {"history": history}


def job_files(root: Path, folder: Path, jid: str | None = None) -> dict:
    """The job's folder: spec, rounds (Q7: `round-<N>` folders, whatever they hold), and decisions (Q5).
    032: a task bundle's unpacked folder has no `jid`, so its 413s and 422s name the file or round alone."""
    at, where = (f"{jid}/", f"job {jid} ") if jid else ("", "")
    names = sorted(os.listdir(folder)) if inside(root, folder) and folder.is_dir() else []
    dirs, feedback = {}, {}
    for name in names:
        if (m := ROUND_DIR.fullmatch(name)) and inside(root, folder / name) and (folder / name).is_dir():
            dirs[int(m[1])] = folder / name
        elif (m := FEEDBACK.fullmatch(name)) and (text := read(root, folder / name, f"{at}{name}")) is not None:
            feedback[int(m[1])] = {"body_md": text, "created_at": mtime(folder / name)}
    rounds = []
    for n, d in sorted(dirs.items()):
        label = f"{at}round-{n}"
        build = read(root, d / "build.md", f"{label}/build.md")
        patch = read(root, d / "diff.patch", f"{label}/diff.patch") or ""
        try:
            files = split_patch(patch) if patch.strip() else []
        except Invalid as e:
            raise Invalid(f"{where}round {n}: {e.detail}")
        verdicts = []
        for r in Reviewer:
            path = d / f"review-{r}.md"
            if (text := read(root, path, f"{label}/review-{r}.md")) is not None:
                first, body = head(text)
                verdicts.append({"reviewer": r.value, "verdict": "PASS" if first == "VERDICT: PASS" else "CHANGES",
                                 "body_md": body, "created_at": mtime(path)})
        rounds.append({"n": n, "trigger": "initial" if n == 1 else "human" if n in feedback else "agent",
                       "build_md": build, "files": files, "verdicts": verdicts,
                       "created_at": mtime(d / "build.md" if build is not None else d)})
    decisions = [f | {"n": n - 1, "actor": "me", "decision": "CHANGES_REQUESTED"}
                 for n, f in sorted(feedback.items()) if n - 1 in dirs]
    decision = folder / "decision.md"
    if dirs and (text := read(root, decision, f"{at}decision.md")) is not None:
        first, body = head(text)
        decisions.append({"n": max(dirs), "actor": "approver", "decision": "APPROVE" if first == "APPROVE" else "ESCALATE",
                          "body_md": body, "created_at": mtime(decision)})
    return {"spec_md": read(root, folder / "spec.md", f"{at}spec.md"), "rounds": rounds, "decisions": decisions}


def base_sha(git: Git, project_path: str, pr: str | None) -> str:
    """Q6: the parent on main of the PR's merge commit, for every round of the job; else unknown."""
    found = PULL.search(pr) if pr else None
    return (git.merge_parent(project_path, int(found[1])) if found else None) or "unknown"


# --- Transcripts (Q8, Q9) -----------------------------------------------------------------


def facts(folder: Path, path: Path) -> dict | None:
    """What matching needs from one transcript, without its bytes or events; it's read again when copied."""
    got = load(path)
    if got is None:
        return None
    return {k: got[k] for k in ("started_at", "ended_at", "team_name", "agent_name")} | {
        "source": path, "rel": path.relative_to(folder).as_posix(), "prompt": first_prompt(got["events"]),
        "types": agent_types(got["events"])}


def sessions(project_path: str, ids: list[str]) -> dict[str, dict[str, dict]]:
    """Q9: job id → {session id → {started_at, ended_at, transcripts}}, the sessions that ran the job: each one's
    own transcript, its subagents whose first prompt names the job, and the builder-<id> teammates it leads."""
    folder = config.claude_config_dir() / "projects" / folder_name(project_path)
    if folder.is_symlink() or not folder.is_dir():
        return {}
    prompts = {jid: re.compile(rf"Job {re.escape(jid)}(?:, round (\d{{1,9}}))?[.,]") for jid in ids}
    found: dict[str, dict[str, list]] = {jid: {} for jid in ids}
    # ponytail: reads every transcript in the project's folder once; read only up to each first prompt and
    # teamName line if folders get big
    tops = {p.stem: f for p in sorted(folder.glob("*.jsonl")) if jsonl(p) and (f := facts(folder, p))}
    for session in sorted(folder.iterdir()):
        sub = session / "subagents"
        if not SESSION.fullmatch(session.name) or session.is_symlink() or sub.is_symlink() or not sub.is_dir():
            continue
        for path in sorted(sub.glob("agent-*.jsonl")):
            f = facts(folder, path) if jsonl(path) else None
            for jid, pattern in prompts.items():
                if f and (m := pattern.search(f["prompt"])):
                    found[jid].setdefault(session.name, []).append(f | {
                        "agent_type": agent_type(path.with_suffix(".meta.json")), "name": None,
                        "round": int(m[1]) if m[1] else None})
    for stem, f in tops.items():
        team = f["team_name"] or ""
        prefix = team.removeprefix("session-")[:8] if team.startswith("session-") else ""
        lead = next((s for s in tops if len(prefix) == 8 and s.startswith(prefix) and s != stem), None)
        for jid, pattern in prompts.items():
            if lead and f["agent_name"] == f"builder-{jid}":
                m = pattern.search(f["prompt"])
                found[jid].setdefault(lead, []).append(f | {
                    "agent_type": tops[lead]["types"].get(f["agent_name"]), "name": f["agent_name"],
                    "round": int(m[1]) if m and m[1] else None})
    runs = {}
    for jid, by_session in found.items():
        runs[jid] = {}
        for s, mates in by_session.items():
            own = tops.get(s)
            ts = [own] if own and own["started_at"] else [t for t in mates if t["started_at"]]
            runs[jid][s] = {
                "started_at": min((t["started_at"] for t in ts), default=None),
                "ended_at": max((t["ended_at"] for t in ts), default=None),
                "transcripts": ([own | {"agent_type": "orchestrator", "name": None, "round": None}] if own else []) + mates,
            }
    return runs


def copy_transcripts(runs: RunsRepo, transcripts: TranscriptsRepo, task_id: int, by_session: dict, now: str) -> int:
    """One run per session (Q8), each transcript copied to `<run-id>/<path in the folder>` under the store and
    upserted on (run_id, path), as 030's collect does. A file that can't be read or copied is left out."""
    count = 0
    for session, run in sorted(by_session.items()):
        run_id = runs.imported(task_id, session, run["started_at"] or now, run["ended_at"] or now)
        for t in run["transcripts"]:
            path = f"{run_id}/{t['rel']}"
            if (got := load(t["source"])) is None:
                continue
            try:
                dest = store() / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(got["data"])
            except OSError:
                continue
            transcripts.upsert(got | {"agent_type": t["agent_type"], "name": t["name"], "round": t["round"],
                                      "run_id": run_id, "task_id": task_id, "path": path})
            count += 1
    return count


# --- The import ---------------------------------------------------------------------------


def import_factory(projects: ProjectsRepo, tasks: TasksRepo, rounds: RoundsRepo, reviews: ReviewsRepo,
                   runs: RunsRepo, transcripts: TranscriptsRepo, git: Git, project_id: int,
                   job_id: str | None) -> ImportOut:
    """Every job on board.json in board order, then backlog.md's backlog-only lines in file order (058); or only
    board.json's `job_id`."""
    if job_id is not None and not ID.fullmatch(job_id):
        raise bad_id(job_id)
    project = projects.for_code(project_id)
    if project is None:
        raise NotFound(f"Project #{project_id} not found")
    path = project["path"]
    signature = mark(path) if job_id is None else None  # Q10: taken before the files are read
    root = factory_root(path)
    board = read(root, Path(path, "factory", "board.json"), "board.json") if root else None
    backlog = read(root, Path(path, "factory", "backlog.md"), "backlog.md") if root and job_id is None else None  # Q8
    if job_id is None and board is None and backlog is None:  # Q9
        raise NotFound(f"no factory/board.json or factory/backlog.md in {path}")
    if board is None and job_id is not None:
        raise NotFound(f"no factory/board.json in {path}")
    jobs = [] if board is None else board_jobs(board)
    picked = [j for j in jobs if job_id is None or (isinstance(j, dict) and j.get("id") == job_id)]
    if job_id is not None and not picked:
        raise NotFound(f"no job {job_id} in factory/board.json")
    picked = [checked(j) for j in picked]  # Q7: only the jobs being imported
    ids = [j["id"] for j in picked]
    if dup := next((i for n, i in enumerate(ids) if i in ids[:n]), None):
        raise Invalid(f"factory/board.json lists job {dup} twice")
    lines, skipped = ([], 0) if backlog is None else parse(backlog)
    lines = [line for line in lines if line["id"] not in ids]  # BE9: board.json's entry wins
    jobs_dir = Path(path, "factory", "jobs")
    files = {j["id"]: job_files(root, jobs_dir / j["id"], j["id"]) | {"base_sha": base_sha(git, path, j.get("pr"))}
             for j in picked}
    found = sessions(path, ids)
    # ponytail: the copies happen inside the write lock, so a first import of every job holds it for seconds
    now = tasks.lock()
    for jid in ids + [line["id"] for line in lines]:
        task = tasks.by_import_key(f"factory:{jid}")
        if task and task["project_id"] != project_id:  # Q11
            raise Conflict(f"factory:{jid} is imported in project #{task['project_id']}")
    imported = []
    for job in picked:
        jid, f = job["id"], files[job["id"]]
        task = tasks.by_import_key(f"factory:{jid}")
        task_id = save(tasks, rounds, reviews, task, *board_task(project_id, job, f, now), f)
        count = copy_transcripts(runs, transcripts, task_id, found.get(jid, {}), now)
        imported.append(ImportedJob(job=jid, task_id=task_id, created=task is None, rounds=len(f["rounds"]),
                                    transcripts=count))
    for line in lines:
        task = tasks.by_import_key(f"factory:{line['id']}")
        task_id = put_line(tasks, project_id, task, line, now)
        imported.append(ImportedJob(job=line["id"], task_id=task_id, created=task is None, rounds=0, transcripts=0))
    if job_id is None:
        projects.set_factory_sync(project_id, signature, None)  # Q10: a {} that worked clears the error
    return ImportOut(imported=imported, skipped=skipped)


def put_line(tasks: TasksRepo, project_id: int, task, line: dict, now: str) -> int:
    """058 Q4–Q6: a backlog-only line's task, new at the bottom of its column with one `app` event. A rerun on one
    the app hasn't started changes only description_md and status, and only when they differ; a new status sends
    it to the bottom of that column with an event. A started task is left alone. done_at stays NULL (Q4)."""
    status = Status.DONE if line["done"] else Status.BACKLOG
    if task is None:
        task_id = tasks.put_imported(None, {
            "project_id": project_id, "import_key": f"factory:{line['id']}", "title": line["title"],
            "description_md": line["description_md"], "spec_md": None, "status": status, "stage": None,
            "position": tasks.bottom_position(project_id, status), "branch": None, "created_at": now,
            "updated_at": now, "done_at": None})
        tasks.add_event(task_id, "app", None, status, None, now)
        return task_id
    if task["started"]:
        return task["id"]
    if task["description_md"] != line["description_md"]:
        tasks.edit(task["id"], None, line["description_md"], now)
    if task["status"] != status:
        tasks.move(task["id"], status, None, None, now, tasks.bottom_position(project_id, status))
        tasks.add_event(task["id"], "app", task["status"], status, None, now)
    return task["id"]


def sync(projects: ProjectsRepo, tasks: TasksRepo, rounds: RoundsRepo, reviews: ReviewsRepo, runs: RunsRepo,
         transcripts: TranscriptsRepo, git: Git, project_id: int) -> str | None:
    """058 Q10, Q11: the board's `{}`, run only when the files' mark differs from the stored one; the refusal to
    show, or None. A refusal (DomainError) is stored with the mark, so a 3 s poll doesn't retry it until a file
    changes; anything else still fails the request. With neither file, nothing is imported or written."""
    # ponytail (Q15): a changed mark runs 031's whole import (a git log per job with a PR, a transcript scan, and
    # copies inside the write lock), once per file change; skip the transcripts here if that ever shows
    found = projects.factory_sync(project_id)
    signature = mark(found["path"])
    if signature == found["factory_mark"]:
        return found["factory_error"]
    error = None
    if signature is not None:
        try:
            import_factory(projects, tasks, rounds, reviews, runs, transcripts, git, project_id, None)
            return None
        except DomainError as e:
            error = e.detail
    projects.set_factory_sync(project_id, signature, error)
    return error


def board_task(project_id: int, job: dict, f: dict, now: str) -> tuple[dict, list[dict]]:
    """Q2: a board entry's task row for `save`, and its history as events."""
    history, pr = job["history"], job.get("pr")
    done = [h["at"] for h in history if h["status"] == "done"]
    row = {
        "project_id": project_id, "import_key": f"factory:{job['id']}", "title": job["title"],
        "description_md": (job.get("description") or "") + (f"\n\nPR: {pr}" if pr else ""),
        "spec_md": f["spec_md"], "status": job["status"], "stage": job.get("stage"), "branch": job.get("branch"),
        "created_at": history[0]["at"] if history else now, "updated_at": history[-1]["at"] if history else now,
        "done_at": done[-1] if done and job["status"] == "done" else None,
    }
    events = [{"actor": "orchestrator", "from_status": prev["status"] if prev else None, "to_status": h["status"],
               "stage": h.get("stage"), "created_at": h["at"]} for prev, h in zip([None, *history], history)]
    return row, events


def save(tasks: TasksRepo, rounds: RoundsRepo, reviews: ReviewsRepo, task, row: dict, events: list[dict],
         f: dict) -> int:
    """Q2, Q3: the task (`row`: put_imported's fields but position), its events, its rounds with their files and
    verdicts, and its decisions; its id. 032 shares it with task bundles."""
    moved = task is None or task["status"] != row["status"]  # Q2: to the bottom of the new column, else kept
    task_id = tasks.put_imported(task["id"] if task else None, row | {
        "position": tasks.bottom_position(row["project_id"], row["status"]) if moved else None})
    tasks.replace_events(task_id, events)
    round_ids = {}
    for r in f["rounds"]:
        round_id = round_ids[r["n"]] = rounds.upsert(task_id, r["n"], r["trigger"], f["base_sha"], r["build_md"],
                                                     r["created_at"])
        rounds.replace_files(round_id, r["files"])
        reviews.replace_verdicts(round_id, r["verdicts"])
    reviews.replace_decisions(task_id, [d | {"round_id": round_ids[d["n"]]} for d in f["decisions"]])
    return task_id
