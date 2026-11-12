"""051: a project's named factory designs, their graph rules, and the default graph. 052: their compiled files,
as a list, a zip, or written into the repo. 088: the templates + New factory starts from (docs/data-model-and-api.md
§6.1)."""

import json

from .. import config
from ..domain.errors import Conflict, Invalid, NotFound
from ..dto.factories import FactoryDesign, FactoryFile, FactoryItem, FactoryPatch, FactoryTemplate, Graph
from ..dto.factory import FactoryOut
from ..lib.factory_compile import compile_files, slug
from ..lib.factory_graph import AGENTS, check, frontmatter
from ..repositories.factories import FactoriesRepo
from ..repositories.projects import ProjectsRepo
from ..repositories.tasks import TasksRepo
from .bundles import zipped
from .factory import TEMPLATES, commit_hint, need_test_cmd, write_files

# Q8: the 011 loop, left to right. (id, type, data: an agent's extra keys over its template, or the whole data, x, y)
DEFAULT_NODES = (
    ("start", "start", {}, 0, 225),
    ("spec-writer", "spec_writer", {}, 300, 225),
    ("builder", "builder", {"side": "both"}, 600, 225),
    ("review-security", "reviewer", {"focus": "security"}, 900, 0),
    ("review-ux", "reviewer", {"focus": "ux"}, 900, 150),
    ("review-ui", "reviewer", {"focus": "ui"}, 900, 300),
    ("review-code", "reviewer", {"focus": "code"}, 900, 450),
    ("all-pass", "all_pass", {}, 1200, 225),
    ("rounds", "rounds_below", {"n": 2}, 1500, 450),
    ("approver", "approver", {}, 1800, 225),
)
REVIEWERS = ("review-security", "review-ux", "review-ui", "review-code")
DEFAULT_EDGES = (  # (source, sourceHandle, target)
    ("start", None, "spec-writer"),
    ("spec-writer", None, "builder"),
    *(("builder", None, r) for r in REVIEWERS),
    *((r, None, "all-pass") for r in REVIEWERS),
    ("all-pass", "yes", "approver"),
    ("all-pass", "no", "rounds"),
    ("rounds", "yes", "builder"),
    ("rounds", "no", "approver"),
)


def changes_loop(writer: str, reviewers: tuple[tuple[str, str], ...], n: int) -> tuple[tuple, tuple]:
    """088 Q3: Standard's loop for fewer than 4 reviewers ((name, focus) each), so it branches on any_changes, which
    the unused, pending slots can't trip. (nodes, edges) as DEFAULT_NODES and DEFAULT_EDGES hold them."""
    top = 225 - 75 * (len(reviewers) - 1)  # centred on 225, 150 apart, as Standard's 4 are
    nodes = (("start", "start", {}, 0, 225), (writer, "spec_writer", {}, 300, 225),
             ("builder", "builder", {"side": "both"}, 600, 225),
             *((name, "reviewer", {"focus": focus}, 900, top + 150 * i) for i, (name, focus) in enumerate(reviewers)),
             ("any-changes", "any_changes", {}, 1200, 225), ("rounds", "rounds_below", {"n": n}, 1500, 450),
             ("approver", "approver", {}, 1800, 225))
    edges = (("start", None, writer), (writer, None, "builder"), *(("builder", None, r) for r, _ in reviewers),
             *((r, None, "any-changes") for r, _ in reviewers), ("any-changes", "yes", "rounds"),
             ("any-changes", "no", "approver"), ("rounds", "yes", "builder"), ("rounds", "no", "approver"))
    return nodes, edges


# 088: + New factory's templates, in list order: key → (name, description, nodes, edges). docs/data-model-and-api.md
# §6.1. A new agent name gets its own file in factory_templates/agents/; a reused one is the 011 file (Q5).
PRESETS = {
    "standard": ("Standard", "Spec, build, then security, UX, UI, and code reviews; up to 2 rounds; the approver"
                 " decides.", DEFAULT_NODES, DEFAULT_EDGES),
    "bug-fix": ("Bug fix", "Reproduce the bug as a failing test, fix its root cause, then code and security reviews.",
                *changes_loop("bug-spec-writer", (("review-code", "code"), ("review-security", "security")), 2)),
    "security-audit": ("Security audit", "Audit dependencies, secrets, and code; write SECURITY-AUDIT.md and fix what"
                       " is safe; security review. Built for scheduled runs.",
                       *changes_loop("security-auditor", (("review-security", "security"),), 2)),
    "ml-experiment": ("ML experiment", "Check the data and baseline, run the experiment, and gate it on eval metrics"
                      " against the baseline.", *changes_loop("data-check", (("review-eval", "custom"),), 3)),
    "test-coverage": ("Test coverage", "Find risky untested code and pin its behavior with tests, leaving production"
                      " code unchanged.", *changes_loop("coverage-planner", (("review-tests", "custom"),), 2)),
}


def agent(name: str) -> dict:
    """BE4: an agent's data from its raw 011 template, unrendered, so `{{ test_cmd }}` stays (Q8)."""
    meta, prompt = frontmatter((TEMPLATES / "agents" / f"{name}.md").read_text(encoding="utf-8"))
    return {"name": meta["name"], "description": meta["description"], "model": meta["model"],
            "tools": [tool.strip() for tool in meta["tools"].split(",")], "prompt": prompt}


def preset_graph(key: str) -> Graph:
    """088: a template's graph; an agent node's data is its template file's, under its extra keys."""
    _, _, preset_nodes, preset_edges = PRESETS[key]
    nodes = [{"id": id_, "type": type_, "position": {"x": x, "y": y},
              "data": agent(id_) | data if type_ in AGENTS else data}
             for id_, type_, data, x, y in preset_nodes]
    edges = [{"id": f"e{i}", "source": source, "sourceHandle": handle, "target": target}
             for i, (source, handle, target) in enumerate(preset_edges, 1)]
    return Graph(nodes=nodes, edges=edges)


def default_graph() -> Graph:
    return preset_graph("standard")


def list_templates() -> list[FactoryTemplate]:
    return [FactoryTemplate(key=key, name=name, description=text) for key, (name, text, _, _) in PRESETS.items()]


def template_graph(key: str | None) -> Graph:
    """088 Q7: no key → Standard; an unknown one → 422 naming the keys."""
    if key is None:
        key = "standard"
    if key not in PRESETS:
        *rest, last = PRESETS
        raise Invalid(f"unknown template {key}: use {', '.join(rest)}, or {last}")
    return preset_graph(key)


def stored(graph: Graph) -> str:
    """Rules 1–6 (Q3, Q4); the compact JSON to store."""
    return check(graph.model_dump(), config.MAX_GRAPH)


def design(row) -> FactoryDesign:
    return FactoryDesign(**dict(row) | {"graph": json.loads(row["graph"])})


def trimmed(name: str) -> str:
    name = name.strip()
    if not name:
        raise Invalid("name must not be blank")
    return name


def list_factories(projects: ProjectsRepo, factories: FactoriesRepo, project_id: int) -> list[FactoryItem]:
    if not projects.exists(project_id):
        raise NotFound(f"Project #{project_id} not found")
    return [FactoryItem(**row) for row in factories.for_project(project_id)]


def create_factory(projects: ProjectsRepo, factories: FactoriesRepo, tasks: TasksRepo, project_id: int,
                   name: str, template: str | None = None) -> FactoryDesign:
    """+ New factory: a template's graph (088; default Standard) under a name new to this project (exact match after
    trim). 088 AC12: the blank name's 422, then the template's, then 404 and 409."""
    name = trimmed(name)
    graph = stored(template_graph(template))
    tasks.lock()  # the clash check and the insert commit together
    if not projects.exists(project_id):
        raise NotFound(f"Project #{project_id} not found")
    if factories.by_name(project_id, name) is not None:
        raise Conflict(f"factory {name} already exists")
    return design(factories.get(factories.add(project_id, name, graph)))


def get_factory(factories: FactoriesRepo, factory_id: int) -> FactoryDesign:
    row = factories.get(factory_id)
    if row is None:
        raise NotFound(f"Factory #{factory_id} not found")
    return design(row)


def put_factory(factories: FactoriesRepo, tasks: TasksRepo, factory_id: int, body: FactoryPatch) -> FactoryDesign:
    """Designer Save and list Rename: the sent fields together, every check before the write (Q6)."""
    fields = {key: getattr(body, key) for key in body.model_fields_set}
    if not fields:
        raise Invalid("send at least one of: name, graph")
    if "name" in fields:
        fields["name"] = trimmed(fields["name"])
    if "graph" in fields:
        fields["graph"] = stored(fields["graph"])
    tasks.lock()  # the clash check and the update commit together
    row = factories.get(factory_id)
    if row is None:
        raise NotFound(f"Factory #{factory_id} not found")
    if "name" in fields and factories.by_name(row["project_id"], fields["name"]) not in (None, factory_id):
        raise Conflict(f"factory {fields['name']} already exists")
    factories.update(factory_id, fields)
    return design(factories.get(factory_id))


def delete_factory(factories: FactoriesRepo, factory_id: int) -> None:
    if not factories.delete(factory_id):
        raise NotFound(f"Factory #{factory_id} not found")


# --- 052: export -------------------------------------------------------------------------


def compiled(factories: FactoriesRepo, projects: ProjectsRepo, factory_id: int):
    """Q8: 404, then 409 no test command, then the compile's 422. (factory row, project row, [(path, content)])."""
    row = factories.get(factory_id)
    if row is None:
        raise NotFound(f"Factory #{factory_id} not found")
    p = projects.for_factory(row["project_id"])
    need_test_cmd(p)
    values = {"name": p["name"], "default_branch": p["default_branch"], "test_cmd": p["test_cmd"]}
    template = (TEMPLATES / "skills" / "factory" / "SKILL.md").read_text(encoding="utf-8")
    return row, p, compile_files(json.loads(row["graph"]), template, values, slug(row["name"]))


def factory_files(factories: FactoriesRepo, projects: ProjectsRepo, factory_id: int) -> list[FactoryFile]:
    _, _, files = compiled(factories, projects, factory_id)
    return [FactoryFile(path=path, content=content) for path, content in files]


def download(factories: FactoriesRepo, projects: ProjectsRepo, factory_id: int) -> tuple[str, bytes]:
    """Q10: (`{project slug}-{factory slug}.zip`, the zip): the files deflated, in order, dated the last save."""
    row, _, files = compiled(factories, projects, factory_id)
    body = zipped([(path, row["updated_at"], content) for path, content in files])
    return f"{slug(row['project'], 'project')}-{slug(row['name'])}.zip", body


def write_factory(factories: FactoriesRepo, projects: ProjectsRepo, factory_id: int, overwrite: bool) -> FactoryOut:
    """Write to repo: Create factory's writer and response (Q9). factory_version stays Create factory's."""
    row, p, files = compiled(factories, projects, factory_id)
    written, skipped = write_files(p["path"], files, overwrite)
    return FactoryOut(written=written, skipped=skipped, commit_hint=commit_hint(slug(row["name"])))
