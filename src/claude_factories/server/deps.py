"""What controllers hand to handlers through `Depends` (docs/MVP.md §4.7). Tests swap any of these
with `app.dependency_overrides`."""

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from typing import Annotated

from fastapi import Depends

from .. import db
from ..adapters.claude import Claude, SubprocessClaude
from ..adapters.git import Git, SubprocessGit
from ..repositories.claude_accounts import ClaudeAccountsRepo
from ..repositories.context_items import ContextItemsRepo
from ..repositories.factories import FactoriesRepo
from ..repositories.projects import ProjectsRepo
from ..repositories.reviews import ReviewsRepo
from ..repositories.rounds import RoundsRepo
from ..repositories.runs import RunsRepo
from ..repositories.settings import SettingsRepo
from ..repositories.tasks import TasksRepo
from ..repositories.transcripts import TranscriptsRepo
from ..repositories.usage import UsageRepo
from ..repositories.workspaces import WorkspacesRepo


def get_conn() -> Iterator[sqlite3.Connection]:
    """One connection per request, so one handler call is one transaction: committed when the handler
    returns, rolled back if it raises. scope="function" ends it before the response goes out, so a
    client's next request sees the commit."""
    with closing(db.connect()) as conn, conn:
        conn.row_factory = sqlite3.Row
        yield conn


Conn = Annotated[sqlite3.Connection, Depends(get_conn, scope="function")]
# 036 Q1: the same connection and transaction outside Depends, for the run handlers' steps
transaction = contextmanager(get_conn)


def get_workspaces(conn: Conn) -> WorkspacesRepo:
    return WorkspacesRepo(conn)


def get_projects(conn: Conn) -> ProjectsRepo:
    return ProjectsRepo(conn)


def get_tasks(conn: Conn) -> TasksRepo:
    return TasksRepo(conn)


def get_rounds(conn: Conn) -> RoundsRepo:
    return RoundsRepo(conn)


def get_reviews(conn: Conn) -> ReviewsRepo:
    return ReviewsRepo(conn)


def get_runs(conn: Conn) -> RunsRepo:
    return RunsRepo(conn)


def get_transcripts(conn: Conn) -> TranscriptsRepo:
    return TranscriptsRepo(conn)


def get_settings(conn: Conn) -> SettingsRepo:
    return SettingsRepo(conn)


def get_factories(conn: Conn) -> FactoriesRepo:
    return FactoriesRepo(conn)


def get_claude_accounts(conn: Conn) -> ClaudeAccountsRepo:
    return ClaudeAccountsRepo(conn)


def get_context_items(conn: Conn) -> ContextItemsRepo:
    return ContextItemsRepo(conn)


def get_usage(conn: Conn) -> UsageRepo:
    return UsageRepo(conn)


def get_git() -> Git:
    return SubprocessGit()


def get_claude() -> Claude:
    return SubprocessClaude()


Workspaces = Annotated[WorkspacesRepo, Depends(get_workspaces)]
Projects = Annotated[ProjectsRepo, Depends(get_projects)]
Tasks = Annotated[TasksRepo, Depends(get_tasks)]
Rounds = Annotated[RoundsRepo, Depends(get_rounds)]
Reviews = Annotated[ReviewsRepo, Depends(get_reviews)]
Runs = Annotated[RunsRepo, Depends(get_runs)]
Transcripts = Annotated[TranscriptsRepo, Depends(get_transcripts)]
Settings = Annotated[SettingsRepo, Depends(get_settings)]
Factories = Annotated[FactoriesRepo, Depends(get_factories)]
ClaudeAccounts = Annotated[ClaudeAccountsRepo, Depends(get_claude_accounts)]
ContextItems = Annotated[ContextItemsRepo, Depends(get_context_items)]
Usage = Annotated[UsageRepo, Depends(get_usage)]
GitAdapter = Annotated[Git, Depends(get_git)]
ClaudeAdapter = Annotated[Claude, Depends(get_claude)]
