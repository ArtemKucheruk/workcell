"""docs/data-model-and-api.md §6.4: /api/auth and the SPA's page view-models. 020 Q1: the page handlers'
keys, with sqlite rows as objects; Q4: every `*_md` keeps its rendered `*_html` beside it."""

from typing import Literal

from pydantic import BaseModel, Field, computed_field

from .factories import Graph
from .modules import ModuleRef
from .rounds import RoundSummary
from .tasks import Dep, TaskItem
from .transcripts import TranscriptOut
from .usage import UsageAccount, UsageWindow
from .workspaces import WorkspaceOut

Factory = Literal["ready", "legacy", "uncommitted", "none"]


class AuthOut(BaseModel):
    auth_method: str | None
    plan: str | None
    runs_enabled: bool
    email: str | None  # 039 Q3: the claude.ai login's account


class SettingsBody(BaseModel):
    """096 Q2: GET and PUT /api/settings. Outside 1–10, or not an integer, is FastAPI's 422."""
    max_concurrent_runs: int = Field(ge=1, le=10, strict=True)  # strict: "3", 2.0, and true aren't integers


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
    usage: list[UsageAccount]  # 095 AC19: GET /api/usage's accounts, for the usage block under the badge


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
    kind: Literal["factory", "automation"]  # 102: a task run, or an automation's (MVP §9)
    task_id: int | None  # 102: null for an automation run
    factory_id: int | None  # 102: the automation; null for a task run or a deleted automation
    title: str  # the task's title, the automation's name, or `deleted automation` (Q9)
    project_id: int | None  # 102 Q9: null once the automation is deleted
    project: str | None
    stage: str | None  # null for an automation run
    round: int | None  # Q4: the task's highest rounds.n
    started_at: str
    agents: list[RunAgent]  # the orchestrator first, then one per Agent tool_use in log order


class RecentRun(BaseModel):
    id: int
    kind: Literal["factory", "automation"]  # 102: as RunningRun
    task_id: int | None
    factory_id: int | None
    title: str
    project_id: int | None
    project: str | None
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
    github_label: str | None  # 108 AC5: the Settings page's GitHub issues section
    github_repo: str | None  # owner/repo of a github.com remote_url, else null
    github_hint: str | None  # why Sync now is off; null when github_repo is set


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
    can_run: bool  # 096: false at the run cap too
    runs_active: int  # 096 AC29: running runs across all projects
    max_concurrent_runs: int
    workspaces: list[WorkspaceOut]
    columns: dict[str, list[Card]]  # backlog, in_progress, review, done
    factory_error: str | None  # 058 Q10: the last automatic factory/ sync's refusal
    factory_files: list[str]  # 059 Q3: Create factory's paths on disk now, the order it writes them
    runs_enabled: bool  # 102 AC19: the active account is logged in to claude.ai (claude_login)
    accounts: list["RunAccount"]  # 102 Q12: the Workflows page's Run menu, as the task page's
    auto: "AutoPick | None"


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
    module: ModuleRef | None  # 112 AC14: the review page's task carries it too, as a PageTask


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
    account: str | None  # 097 AC24: the label of the account it ran in; null for none or a deleted one


class RunAccount(BaseModel):
    """097 AC26: a Run menu entry, the windows as GET /api/usage reads them (DB only)."""
    id: int
    label: str
    active: bool  # the preferred account (Settings, Q8)
    five_hour: UsageWindow | None
    seven_day: UsageWindow | None


class AutoPick(BaseModel):
    account_id: int
    label: str


class PagePr(BaseModel):
    """093 AC36: from the task row and local git only, never gh."""
    url: str | None
    number: int | None  # parsed from url
    can_create: bool
    hint: str | None  # why Create PR is off; null when it's on or a PR exists


class TaskPageTask(PageTask):
    issue_url: str | None  # 108 AC22: the issue a `github:` import_key names, else null


class TaskPage(BaseModel):
    task: TaskPageTask
    pr: PagePr | None  # 093: null for a standalone task
    can_run: bool
    hint: str | None
    run: RunDetail | None  # Q9: the latest run, whatever its status
    takeover: str | None
    accounts: list[RunAccount]  # 097 AC26: every account by id
    auto: AutoPick | None  # Auto's first candidate from the DB alone; null when all are low or there are none
    rounds: list[TaskRound]
    approver: Approver | None
    history: list[HistoryEntry]
    transcripts: list[TranscriptOut]  # 030: the Agents per round, and Other agents for round null
    blocked_by: list[Dep]  # 094: every link, done blockers too, by id
    blocks: list[Dep]  # 094: the tasks waiting on this one, by id
    project_tasks: list[Dep]  # 094 Q8: the project's other tasks by id, Add's candidates


# --- GET /api/pages/factories/{id}/runs (§8 item 17; 103) ----------------------------------


class AutomationRef(BaseModel):
    id: int
    name: str
    project_id: int
    project: str  # the project's and workspace's names now, for the breadcrumb
    workspace_id: int
    workspace: str


class AutomationRun(BaseModel):
    id: int
    status: Literal["running", "succeeded", "failed", "stopped"]
    trigger: Literal["manual", "schedule"]
    started_at: str
    ended_at: str | None
    error: str | None  # AC2: only a failed run's
    account: str | None  # the label of the account it ran in; null for none or a deleted one
    transcripts: list[TranscriptOut]  # AC3: by started_at, then id


class AutomationRunsPage(BaseModel):
    automation: AutomationRef
    runs: list[AutomationRun]  # started_at newest first, then id
    runs_enabled: bool  # AC5: as BoardPage's
    runs_active: int
    max_concurrent_runs: int
    accounts: list[RunAccount]
    auto: AutoPick | None


# --- GET /api/pages/tasks/{id}/flow?round= (§8 item 4's Factory section; 089) -----------


class FlowVerdict(BaseModel):
    verdict: str
    body_md: str
    body_html: str


class FlowComment(BaseModel):
    path: str | None  # all null for a conversation comment
    line: int | None
    side: str | None
    body_md: str
    body_html: str


class FlowDecision(BaseModel):
    actor: Literal["approver", "me"]
    decision: str
    body_md: str
    body_html: str


class FlowResult(BaseModel):
    """What clicking the node shows; only its type's keys are filled, the rest stay null or []."""
    spec_md: str | None = None  # spec_writer
    spec_html: str | None = None
    build_md: str | None = None  # builder: round n's row; all null before it submits
    build_html: str | None = None
    files: int | None = None
    additions: int | None = None
    deletions: int | None = None
    diff_url: str | None = None  # /tasks/{id}/review?round={n}&tab=files
    verdict: FlowVerdict | None = None  # a security/ux/ui/code reviewer
    comments: list[FlowComment] = []  # that reviewer's comments on round n, by id
    decisions: list[FlowDecision] = []  # approver: every decision on round n, by id
    answer: Literal["yes", "no"] | None = None  # a condition; null until reached
    why: str | None = None
    transcripts: list[TranscriptOut] = []  # an agent: round n's (a spec-writer: all of its)


class FlowNode(BaseModel):
    state: Literal["idle", "running", "done", "changes", "failed", "escalated"]
    label: str  # PASS, CHANGES, APPROVE, ESCALATE, yes, no, running, failed, done, escalated, not reached
    current: bool  # where the run is now
    result: FlowResult


class FlowSource(BaseModel):
    factory_id: int
    name: str


class TaskFlow(BaseModel):
    graph: Graph | None  # Q3: null for a standalone task
    source: FlowSource | None  # the design slugged `factory`; null for default_graph()
    rounds: list[int]  # 1..max(L, C)
    round: int  # the one the states and results are for
    nodes: dict[str, FlowNode]  # by node id; {} with no graph


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
    pr: PagePr | None  # 093
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
    web_url: str | None = None  # 090: lib.remote.web_url of remote_url, always http(s); remote_url itself isn't sent


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
    file_url: str | None = None  # 090 Q5: ?path= on the default branch, github.com only; null with `error`
