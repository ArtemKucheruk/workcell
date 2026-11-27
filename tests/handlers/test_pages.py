import sqlite3
from contextlib import closing

import pytest
from conftest import commit

from workcell import db
from workcell.adapters.claude import SubprocessClaude
from workcell.adapters.git import SubprocessGit
from workcell.domain.errors import NotFound
from workcell.handlers import code, pages
from workcell.repositories.claude_accounts import ClaudeAccountsRepo
from workcell.repositories.projects import ProjectsRepo
from workcell.repositories.reviews import ReviewsRepo
from workcell.repositories.rounds import RoundsRepo
from workcell.repositories.runs import RunsRepo
from workcell.repositories.settings import SettingsRepo
from workcell.repositories.tasks import TasksRepo
from workcell.repositories.transcripts import TranscriptsRepo
from workcell.repositories.usage import UsageRepo
from workcell.repositories.workspaces import WorkspacesRepo


@pytest.fixture
def conn():
    """A connection to the test's database, no app."""
    db.init()
    with closing(db.connect()) as c:
        c.row_factory = sqlite3.Row
        yield c


def detail(call) -> str:
    with pytest.raises(NotFound) as e:
        call()
    return e.value.detail


def test_page_handlers_raise_not_found(conn, repo):  # 036 AC11
    git, claude = SubprocessGit(), SubprocessClaude()
    projects, tasks, rounds, reviews = ProjectsRepo(conn), TasksRepo(conn), RoundsRepo(conn), ReviewsRepo(conn)
    runs, workspaces, accounts = RunsRepo(conn), WorkspacesRepo(conn), ClaudeAccountsRepo(conn)
    assert detail(lambda: pages.workspace(workspaces, projects, git, 999)) == "Not Found"
    assert detail(lambda: pages.board(projects, tasks, rounds, reviews, runs, TranscriptsRepo(conn), workspaces, git,
                                      claude, accounts, SettingsRepo(conn), UsageRepo(conn), 999)) == "Not Found"
    assert detail(lambda: pages.task(tasks, rounds, reviews, runs, TranscriptsRepo(conn), git, claude, accounts,
                                     UsageRepo(conn), 999)) == "Task #999 not found"
    assert detail(lambda: pages.review(tasks, rounds, reviews, git, 999, "latest", "")) == "Task #999 not found"
    assert detail(lambda: code.code(projects, git, 999, "")) == "Project #999 not found"
    commit(repo, {"README.md": "# hi\n"})
    project = projects.add(workspaces.get_or_create("personal"), "api", str(repo), None, "main", None)
    assert detail(lambda: code.code(projects, git, project, "nope.txt")) == "nope.txt is not a tracked file in api"
