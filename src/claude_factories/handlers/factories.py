"""051: a project's named factory designs, their graph rules, and the default graph
(docs/data-model-and-api.md §6.1)."""

import json

from .. import config
from ..domain.errors import Conflict, Invalid, NotFound
from ..dto.factories import FactoryDesign, FactoryItem, FactoryPatch, Graph
from ..lib.factory_graph import check, frontmatter
from ..repositories.factories import FactoriesRepo
from ..repositories.projects import ProjectsRepo
from ..repositories.tasks import TasksRepo
from .factory import TEMPLATES

# Q8: the 011 loop, left to right. (id, type, extra data or None for an agent-less node, x, y)
DEFAULT_NODES = (
    ("start", "start", None, 0, 225),
    ("spec-writer", "spec_writer", {}, 300, 225),
    ("builder", "builder", {"side": "both"}, 600, 225),
    ("review-security", "reviewer", {"focus": "security"}, 900, 0),
    ("review-ux", "reviewer", {"focus": "ux"}, 900, 150),
    ("review-ui", "reviewer", {"focus": "ui"}, 900, 300),
    ("review-code", "reviewer", {"focus": "code"}, 900, 450),
    ("all-pass", "all_pass", None, 1200, 225),
    ("rounds", "rounds_below", None, 1500, 450),
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


def agent(name: str) -> dict:
    """BE4: an agent's data from its raw 011 template, unrendered, so `{{ test_cmd }}` stays (Q8)."""
    meta, prompt = frontmatter((TEMPLATES / "agents" / f"{name}.md").read_text(encoding="utf-8"))
    return {"name": meta["name"], "description": meta["description"], "model": meta["model"],
            "tools": [tool.strip() for tool in meta["tools"].split(",")], "prompt": prompt}


def default_graph() -> Graph:
    nodes = [{"id": id_, "type": type_, "position": {"x": x, "y": y},
              "data": {"n": 2} if type_ == "rounds_below" else {} if extra is None else agent(id_) | extra}
             for id_, type_, extra, x, y in DEFAULT_NODES]
    edges = [{"id": f"e{i}", "source": source, "sourceHandle": handle, "target": target}
             for i, (source, handle, target) in enumerate(DEFAULT_EDGES, 1)]
    return Graph(nodes=nodes, edges=edges)


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
                   name: str) -> FactoryDesign:
    """+ New factory: the default graph under a name new to this project (exact match after trim)."""
    name = trimmed(name)
    graph = stored(default_graph())
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
