"""051: factory designs (docs/data-model-and-api.md §6.1). The graph is React Flow's shape, cut to the documented
keys: pydantic's default `extra="ignore"` drops the rest (Q5), so `Graph.model_dump()` is the stored graph."""

from typing import Annotated, Literal

from pydantic import AllowInfNan, BaseModel, Field, Strict, field_validator

Id = Annotated[str, Field(min_length=1)]
Coordinate = Annotated[float, Strict(), AllowInfNan(False)]  # strict: "5" is a 422, not 5.0


class Position(BaseModel):
    x: Coordinate
    y: Coordinate


class Empty(BaseModel):
    """start and the conditions without a parameter."""


class Agent(BaseModel):
    name: str
    description: str
    model: Literal["inherit", "opus", "sonnet", "haiku"]
    tools: list[str]
    prompt: str


class BuilderData(Agent):
    side: Literal["backend", "frontend", "both"]


class ReviewerData(Agent):
    focus: Literal["security", "ux", "ui", "code", "custom"]


class RoundsData(BaseModel):
    n: Annotated[int, Strict(), Field(ge=1)]


class NodeBase(BaseModel):
    id: Id
    position: Position


class BareNode(NodeBase):
    type: Literal["start", "all_pass", "any_changes", "approved"]
    data: Empty


class AgentNode(NodeBase):
    type: Literal["spec_writer", "approver", "custom_agent"]
    data: Agent


class BuilderNode(NodeBase):
    type: Literal["builder"]
    data: BuilderData


class ReviewerNode(NodeBase):
    type: Literal["reviewer"]
    data: ReviewerData


class RoundsNode(NodeBase):
    type: Literal["rounds_below"]
    data: RoundsData


Node = Annotated[BareNode | AgentNode | BuilderNode | ReviewerNode | RoundsNode, Field(discriminator="type")]


class Edge(BaseModel):
    id: Id
    source: Id
    sourceHandle: str | None = None  # React Flow's key; which values fit which node: lib/factory_graph.py
    target: Id


class Graph(BaseModel):
    nodes: list[Node]
    edges: list[Edge]


Kind = Literal["workflow", "automation"]  # 101: workflow runs on board tasks, automation on the repo


class NewFactory(BaseModel):
    name: str
    template: str | None = None  # 088 Q7: a FactoryTemplate key; null or left out → standard
    kind: Kind = "workflow"  # 101 AC5: anything else, null included, is a 422


class FactoryTemplate(BaseModel):
    """088: one of + New factory's templates. 101 Q1: kind picks the Workflows page section that offers it."""
    key: str
    name: str
    description: str
    kind: Kind


class FactoryPatch(BaseModel):
    """Q6: name, graph, or both, applied together."""
    name: str | None = None
    graph: Graph | None = None

    @field_validator("name", "graph")
    @classmethod
    def not_null(cls, value):
        """049's ProjectPatch.not_null: a sent null gets FastAPI's list detail; an omitted key stays None."""
        if value is None:
            raise ValueError("must not be null")
        return value


class FactoryItem(BaseModel):
    """A Factories list row: `nodes` counts every node, start and conditions included (Q7)."""
    id: int
    name: str
    kind: Kind
    nodes: int
    created_at: str
    updated_at: str


class FactoryDesign(BaseModel):
    """<Factory>: with the project's and workspace's names as they are now, for the breadcrumb."""
    id: int
    project_id: int
    project: str
    workspace_id: int
    workspace: str
    name: str
    kind: Kind
    graph: Graph
    created_at: str
    updated_at: str


class FactoryFile(BaseModel):
    """052: one compiled file; path is relative to the repo root, with "/"."""
    path: str
    content: str
