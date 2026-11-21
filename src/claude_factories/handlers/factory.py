"""Create factory and the factory state (docs/MVP.md §3.2, docs/claude-code.md §7.1, §7.3)."""

import os
import shlex
from pathlib import Path

import jinja2

from ..adapters.git import Git
from ..domain.errors import Conflict, NotFound
from ..dto.factory import FactoryOut
from ..repositories.projects import ProjectsRepo

SKILL = ".claude/skills/factory/SKILL.md"
FACTORY_FILES = (SKILL, *(f".claude/agents/{a}.md" for a in (  # 011 Q6: written and listed in this order
    "spec-writer", "builder", "review-security", "review-ux", "review-ui", "review-code", "approver")))
TEMPLATES = Path(__file__).parent.parent / "factory_templates"
# 011 Q5: markdown, not HTML; values go in verbatim and are never evaluated as template code
FACTORY_TEMPLATES = jinja2.Environment(
    loader=jinja2.FileSystemLoader(TEMPLATES),
    autoescape=False, keep_trailing_newline=True, undefined=jinja2.StrictUndefined,
)


def commit_hint(skill: str) -> str:
    """052 Q9: 011's hint for `factory`."""
    return f'git add .claude/skills/{skill} .claude/agents && git commit -m "Add factory"'


COMMIT_HINT = commit_hint("factory")


def factory_state(git: Git, path: str, default_branch: str) -> str:
    """MVP §3.2 step 4, 059: SKILL.md committed on the default branch is ready when it calls `fctl stage`
    (the app's template always does), else legacy (the file-based bootstrap loop). Not committed (or git
    fails, or it's no blob there, Q5): uncommitted when on disk, else none. One git call."""
    committed, _ = git.blob(path, f"{default_branch}:{SKILL}")  # branch can't start with `-` (connect)
    if committed is not None:
        return "ready" if b"fctl stage" in committed else "legacy"
    return "uncommitted" if os.path.isfile(os.path.join(path, SKILL)) else "none"


def skill_committed(git: Git, path: str, default_branch: str, skill: str) -> bool:
    """102 AC9: `.claude/skills/<skill>/SKILL.md` is a blob on the default branch. One git call; git failing is
    not committed."""
    return git.blob(path, f"{default_branch}:.claude/skills/{skill}/SKILL.md")[0] is not None


def factory_files(path: str) -> list[str]:
    """059 Q3: which of Create factory's paths exist on disk now, by its own skip test, in FACTORY_FILES order."""
    return [rel for rel in FACTORY_FILES if os.path.lexists(os.path.join(path, rel))]


def factory_hint(state: str, branch: str) -> str | None:
    """MVP §3.2 step 4, 014 Q6: why Run is off for this factory state, naming the next step (015 ux
    review); None when ready. run_task's 409 detail and the pages' hint."""
    if state == "legacy":
        return f"this repo runs the file-based /factory loop: Create factory with Overwrite, then commit it on {branch}"
    if state == "uncommitted":
        return f"factory isn't committed on {branch}: on {branch}, run {COMMIT_HINT}"
    if state == "none":
        return (f"factory isn't committed on {branch}: Create factory in the project's Settings,"
                f" then commit it on {branch}")
    return None


def need_test_cmd(p) -> None:
    """011: the templates render `{{ test_cmd }}`, so no test command, no files (052 Q8)."""
    if not (p["test_cmd"] or "").strip():
        raise Conflict("no test command: in the repo, run fctl connect --workspace"
                       f' {shlex.quote(p["workspace"])} --test-cmd "<your test command>"')


def write_files(root: str, files: list[tuple[str, str]], overwrite: bool) -> tuple[list[str], list[str]]:
    """011 Q7, Q8, 052 Q9: Create factory's and Write to repo's writer. Every check runs before any write;
    existing files (lexists) are skipped unless overwrite. Returns (written, skipped), in the files' order."""
    if not os.path.isdir(root):
        raise Conflict(f"{root} is not a directory")
    real_root = Path(os.path.realpath(root))
    for rel, _ in files:
        if not Path(os.path.realpath(os.path.join(root, rel))).is_relative_to(real_root):
            raise Conflict(f"{rel} resolves outside the project")
        parts = rel.split("/")  # from .claude down to the target; islink also catches a broken link
        for i in range(1, len(parts) + 1):
            if os.path.islink(os.path.join(root, *parts[:i])):
                raise Conflict(f"{'/'.join(parts[:i])} is a symlink")
    written, skipped = [], []
    for rel, content in files:
        target = Path(root, rel)
        if os.path.lexists(target) and not overwrite:
            skipped.append(rel)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode())
        written.append(rel)
    return written, skipped


def create_factory(projects: ProjectsRepo, project_id: int, overwrite: bool) -> FactoryOut:
    p = projects.for_factory(project_id)
    if p is None:
        raise NotFound()
    need_test_cmd(p)
    values = {"name": p["name"], "default_branch": p["default_branch"], "test_cmd": p["test_cmd"], "skill": "factory"}
    files = [(rel, FACTORY_TEMPLATES.get_template(rel.removeprefix(".claude/")).render(values))
             for rel in FACTORY_FILES]
    written, skipped = write_files(p["path"], files, overwrite)
    if written:  # 011 Q9
        projects.set_factory_version(project_id, 1)
    return FactoryOut(written=written, skipped=skipped, commit_hint=COMMIT_HINT)
