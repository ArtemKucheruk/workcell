"""docs/data-model-and-api.md §6.4: /api/auth and the SPA's page view-models. 020 Q1: the page handlers'
keys, with sqlite rows as objects; Q4: every `*_md` keeps its rendered `*_html` beside it."""

from typing import Literal

from pydantic import BaseModel, computed_field

from .rounds import RoundSummary
from .tasks import TaskItem
from .transcripts import TranscriptOut
from .workspaces import WorkspaceOut

Factory = Literal["ready", "uncommitted", "none"]


class AuthOut(BaseModel):
    auth_method: str | None
    plan: str | None
    runs_enabled: bool
    email: str | None  # 039 Q3: the claude.ai login's account


class LoginStart(BaseModel):
    account_id: int | None = None  # 056 Q3: none is a new account, in a fresh config dir


class LoginStarted(BaseModel):
    url: str  # 039 Q2: always https
    account_id: int  # 056: the account this login is for, the new row's for a new account


class LoginCode(BaseModel):
    code: str  # `<code>#<state>` from the sign-in page; handlers/pages.py checks its shape (039 AC12)
    account_id: int | None = None  # 056 Q5: a guard; another account's id than the pending login's is a 409


class AccountOut(BaseModel):
    """056: GET /api/auth/accounts' item. signed_in, auth_method, plan, and email follow AuthOut's rules."""
    id: int
    config_dir: str
    active: bool
    signed_in: bool
    auth_method: str | None
    plan: str | None
    email: str | None


# --- GET /api/docs/fctl (docs/ui.md §8 item 7) -----------------------------------------


class Heading(BaseModel):
    id: str
    text: str  # plain text: the SPA renders it as React text, never as HTML
    level: int


class FctlDoc(BaseModel):
    body_html: str
    headings: list[Heading]  # every heading, in document order


# --- GET /api/pages/sidebar (docs/ui.md §8, §8.4; 041) ---------------------------------


class SidebarProject(BaseModel):
    id: int
    name: str
    review: int  # Q1: stage human_review or escalated
    running: int  # with a running run
    escalated: int  # stage escalated


class SidebarWorkspace(BaseModel):
    id: int
    name: str
    projects: list[SidebarProject]  # by name, then id (Q4)


class SidebarCurrent(BaseModel):
    workspace_id: int
    project_id: int


class SidebarPage(BaseModel):
    workspaces: list[SidebarWorkspace]  # every workspace by name, the empty ones too
    current: SidebarCurrent | None  # ?task= or ?transcript='s project; null without one or for an unknown id


# --- GET /api/pages/dashboard (docs/ui.md §8 item 1) -----------------------------------


class TileTask(BaseModel):
    id: int
    title: str
    status: str
    stage: str | None
    project_id: int
    project: str


class TileRun(BaseModel):
    id: int
    status: str
    started_at: str
    task_id: int
    title: str
    project_id: int
    project: str


class OpenProject(BaseModel):
    id: int
    name: str
    backlog: int
    in_progress: int
    review: int


class OpenWorkspace(BaseModel):
    id: int
    name: str
    projects: list[OpenProject]


class DoneTask(BaseModel):
    id: int
    title: str
    done_at: str
    project_id: int
    project: str
    rounds: int


class NeedsYou(BaseModel):
    id: int
    title: str
    project_id: int
    project: str
    round: int | None  # the highest round n; null with no rounds
    since: str  # 045 Q1: the task's updated_at


class DashboardPage(BaseModel):
    tiles: dict[str, str]
    counts: dict[str, int]
    show: str
    listed: list[TileTask] | list[TileRun] | None  # runs only for show=runs_week
    waiting: list[NeedsYou]  # stage human_review, newest since first, then id (045 Q2); ignores show
    escalated: list[NeedsYou]  # stage escalated, likewise
    open_tasks: list[OpenWorkspace]
    done: list[DoneTask]


# --- GET /api/pages/agents (docs/ui.md §8 item 15; 053) ---------------------------------


class RunAgent(BaseModel):
    name: str  # the Agent input's name, else its subagent_type, else "agent"
    type: str | None  # subagent_type
    round: int | None  # n from `Job|Task <id>, round <n>.` in its prompt
    running: bool  # no tool_result answers it yet; the orchestrator always (Q12)
    duration_ms: int | None  # Q1: the answer's tool_use_result.totalDurationMs
    last_tool: str | None  # Q2: its latest own tool line, without the `<who> · ` prefix


class RunningRun(BaseModel):
    id: int
    kind: Literal["factory"]  # scheduled runs join later (MVP §9)
    task_id: int
    title: str
    project_id: int
    project: str
    stage: str | None
    round: int | None  # Q4: the task's highest rounds.n
    started_at: str
    agents: list[RunAgent]  # the orchestrator first, then one per Agent tool_use in log order


class RecentRun(BaseModel):
    id: int
    task_id: int
    title: str
    project_id: int
    project: str
    status: Literal["succeeded", "failed", "stopped"]
    error: str | None
    started_at: str
    ended_at: str | None  # Q5: null for 031's imported runs, listed last
    transcripts: int  # Q6: this run's transcripts rows


class AgentsPage(BaseModel):
    running: list[RunningRun]  # newest started_at first, then id
    recent: list[RecentRun]  # at most 20, ended_at newest first, nulls last, then id


# --- GET /api/pages/workspaces/{id} (§8 item 2) ----------------------------------------


class WorkspaceRef(BaseModel):
    id: int
    name: str


class WorkspaceProject(BaseModel):
    id: int
    name: str
    path: str
    backlog: int
    in_progress: int
    review: int
    done: int
    last_activity: str
    factory: Factory


class WorkspacePage(BaseModel):
    workspace: WorkspaceRef
    projects: list[WorkspaceProject]


# --- GET /api/pages/projects/{id} (§8 item 3, §8.1) ------------------------------------


class BoardProject(BaseModel):
    id: int
    name: str
    path: str
    default_branch: str
    workspace_id: int
    workspace: str
    remote_url: str | None
    test_cmd: str | None


class Card(TaskItem):
    position: float
    started_at: str | None
    branch: str | None  # 042 Q1: for the Reviews rows
    description_md: str  # 048 Q5: prefills the board's Edit form

    @computed_field
    def waiting(self) -> bool:
        return self.stage == "human_review"

    @computed_field
    def escalated(self) -> bool:
        return self.stage == "escalated"

    @computed_field
    def stalled(self) -> bool:
        """014 Q5: an in_progress card whose latest run has ended."""
        return self.status == "in_progress" and self.run is not None and self.run.status != "running"


class BoardPage(BaseModel):
    project: BoardProject
    factory: Factory
    hint: str | None
    can_run: bool
    workspaces: list[WorkspaceOut]
    columns: dict[str, list[Card]]  # backlog, in_progress, review, done


# --- GET /api/pages/tasks/{id} (§8 item 4) ---------------------------------------------


class PageTask(BaseModel):
    id: int
    project_id: int
    project: str
    workspace_id: int  # 047: the project's workspace now, for the breadcrumb
    workspace: str
    title: str
    status: str
    stage: str | None
    branch: str | None
    worktree_path: str | None
    description_md: str
    description_html: str
    spec_md: str | None
    spec_html: str


class Posted(BaseModel):
    verdict: str
    body_md: str
    body_html: str


class ReviewRound(RoundSummary):
    posted: dict[str, Posted]  # only the reviewers that posted


class TaskRound(ReviewRound):
    build_md: str | None
    build_html: str


class Approver(BaseModel):
    decision: str
    n: int
    body_md: str
    body_html: str


class HistoryEntry(BaseModel):
    created_at: str
    label: str


class RunDetail(BaseModel):
    id: int
    status: str
    error: str | None
    session_id: str
    started_at: str


class TaskPage(BaseModel):
    task: PageTask
    can_run: bool
    hint: str | None
    run: RunDetail | None  # Q9: the latest run, whatever its status
    takeover: str | None
    rounds: list[TaskRound]
    approver: Approver | None
    history: list[HistoryEntry]
    transcripts: list[TranscriptOut]  # 030: the Agents per round, and Other agents for round null


# --- GET /api/pages/tasks/{id}/review (§8 item 5, §8.2, §8.3) --------------------------


class ReviewTask(PageTask):
    commit_hint: str | None


class Comment(BaseModel):
    id: int
    author: str
    path: str
    line: int | None
    side: str | None
    body_md: str
    body_html: str


class DiffRow(BaseModel):
    kind: Literal["hunk", "ctx", "add", "del", "note"]
    old: int | None
    new: int | None
    side: Literal["old", "new"] | None  # Q5
    anchor: str | None  # path:side:line
    text: str
    comments: list[Comment]


class FileOut(BaseModel):
    path: str
    old_path: str | None
    change: str
    binary: bool
    additions: int
    deletions: int
    lang: str | None
    rows: list[DiffRow]
    orphans: list[Comment]  # comments on lines that aren't in the diff


class TimelineEntry(BaseModel):
    created_at: str
    kind: Literal["event", "round", "verdict", "decision", "comment"]  # Q8
    id: int  # unique within its kind
    label: str
    body_md: str | None
    body_html: str


class ReviewPage(BaseModel):
    task: ReviewTask
    rounds: list[ReviewRound]
    selected: RoundSummary | None
    approver: Approver | None
    files: list[FileOut]
    timeline: list[TimelineEntry]


# --- GET /api/pages/projects/{id}/code (§8 item 6) -------------------------------------


class CodeProject(BaseModel):
    id: int
    name: str
    path: str
    workspace_id: int  # 047: for the breadcrumb
    workspace: str


class TextView(BaseModel):
    text: str
    lines: int


class NoteView(BaseModel):
    note: str


class CodePage(BaseModel):
    """With `error` (git ls-files failed) only `project` is filled in."""
    project: CodeProject
    error: str | None = None
    branch: str | None = None  # the checked-out branch, whichever one is browsed
    branches: list[str] = []  # 054 Q4: local names, then origin/<name> without a local twin
    tree: dict = {}  # Q12: lib.diff.file_tree's nesting, directory keys ending in "/"
    shown: str = ""
    view: TextView | NoteView | None = None
    lang: str | None = None
    readme_html: str | None = None
