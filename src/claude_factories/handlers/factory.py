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
COMMIT_HINT = 'git add .claude/skills/factory .claude/agents && git commit -m "Add factory"'


def factory_state(git: Git, path: str, default_branch: str) -> str:
    """002 Q6: ready = SKILL.md committed on the default branch (MVP §3.2), uncommitted = only on disk."""
    if git.committed(path, default_branch, SKILL):
        return "ready"
    return "uncommitted" if os.path.isfile(os.path.join(path, SKILL)) else "none"


def factory_hint(state: str, branch: str) -> str | None:
    """MVP §3.2 step 4, 014 Q6: why Run is off for this factory state, naming the next step (015 ux
    review); None when ready. run_task's 409 detail and the pages' hint."""
    if state == "uncommitted":
        return f"factory isn't committed on {branch}: on {branch}, run {COMMIT_HINT}"
    if state == "none":
        return (f"factory isn't committed on {branch}: Create factory in the project's Settings,"
                f" then commit it on {branch}")
    return None


def create_factory(projects: ProjectsRepo, project_id: int, overwrite: bool) -> FactoryOut:
    """011 Q7, Q8: every check before any write; existing files (lexists) are skipped unless overwrite."""
    p = projects.for_factory(project_id)
    if p is None:
        raise NotFound()
    if not (p["test_cmd"] or "").strip():
        raise Conflict("no test command: in the repo, run fctl connect --workspace"
                       f' {shlex.quote(p["workspace"])} --test-cmd "<your test command>"')
    root = p["path"]
    if not os.path.isdir(root):
        raise Conflict(f"{root} is not a directory")
    real_root = Path(os.path.realpath(root))
    for rel in FACTORY_FILES:
        if not Path(os.path.realpath(os.path.join(root, rel))).is_relative_to(real_root):
            raise Conflict(f"{rel} resolves outside the project")
    values = {"name": p["name"], "default_branch": p["default_branch"], "test_cmd": p["test_cmd"]}
    written, skipped = [], []
    for rel in FACTORY_FILES:
        target = Path(root, rel)
        if os.path.lexists(target) and not overwrite:
            skipped.append(rel)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(FACTORY_TEMPLATES.get_template(rel.removeprefix(".claude/")).render(values),
                          encoding="utf-8")
        written.append(rel)
    if written:  # 011 Q9
        projects.set_factory_version(project_id, 1)
    return FactoryOut(written=written, skipped=skipped, commit_hint=COMMIT_HINT)
