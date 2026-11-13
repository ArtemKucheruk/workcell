import sqlite3
from contextlib import closing

import pytest
from conftest import commit

from claude_factories import db
from claude_factories.adapters.claude import SubprocessClaude
from claude_factories.adapters.git import SubprocessGit
from claude_factories.domain.errors import NotFound
from claude_factories.handlers import code, pages
from claude_factories.repositories.claude_accounts import ClaudeAccountsRepo
from claude_factories.repositories.projects import ProjectsRepo
from claude_factories.repositories.reviews import ReviewsRepo
from claude_factories.repositories.rounds import RoundsRepo
from claude_factories.repositories.runs import RunsRepo
from claude_factories.repositories.settings import SettingsRepo
from claude_factories.repositories.tasks import TasksRepo
from claude_factories.repositories.transcripts import TranscriptsRepo
from claude_factories.repositories.usage import UsageRepo
from claude_factories.repositories.workspaces import WorkspacesRepo


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
                                      claude, accounts, SettingsRepo(conn), 999)) == "Not Found"
    assert detail(lambda: pages.task(tasks, rounds, reviews, runs, TranscriptsRepo(conn), git, claude, accounts,
                                     UsageRepo(conn), 999)) == "Task #999 not found"
    assert detail(lambda: pages.review(tasks, rounds, reviews, git, 999, "latest", "")) == "Task #999 not found"
    assert detail(lambda: code.code(projects, git, 999, "")) == "Project #999 not found"
    commit(repo, {"README.md": "# hi\n"})
    project = projects.add(workspaces.get_or_create("personal"), "api", str(repo), None, "main", None)
    assert detail(lambda: code.code(projects, git, project, "nope.txt")) == "nope.txt is not a tracked file in api"
