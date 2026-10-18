import re

import pytest
from conftest import git, sql

H = {"X-Requested-By": "fctl"}
SKILL = ".claude/skills/factory/SKILL.md"
AGENTS = ["spec-writer", "builder", "review-security", "review-ux", "review-ui", "review-code", "approver"]
PATHS = [SKILL, *(f".claude/agents/{a}.md" for a in AGENTS)]
BUILDER = ".claude/agents/builder.md"
HINT = 'git add .claude/skills/factory .claude/agents && git commit -m "Add factory"'
NO_TEST_CMD = 'no test command: in the repo, run fctl connect --workspace personal --test-cmd "<your test command>"'


def connect(client, path, **extra):
    body = {"path": str(path), "workspace": "personal", "name": "api-server", "default_branch": "main",
            "test_cmd": "make check"} | extra
    r = client.post("/api/projects/connect", json=body, headers=H)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def create(client, project_id, body=None, headers=H):
    return client.post(f"/api/projects/{project_id}/factory", json={"overwrite": False} if body is None else body,
                       headers=headers)


def rendered(client, repo, **extra) -> dict[str, str]:
    """Connect, create the factory, and return {relative path: text} of the 8 files."""
    r = create(client, connect(client, repo, **extra))
    assert r.status_code == 200, r.text
    return {p: (repo / p).read_text(encoding="utf-8") for p in PATHS}


def files_outside_git(repo) -> set[str]:
    return {p.relative_to(repo).as_posix() for p in repo.rglob("*")
            if p.is_file() and p.relative_to(repo).parts[0] != ".git"}


def frontmatter(text) -> dict[str, str]:
    assert text.startswith("---\n")
    head = text[4:text.index("\n---\n")]
    return dict(line.split(": ", 1) for line in head.splitlines())


def snapshot(repo) -> dict[str, bytes]:
    return {p: (repo / p).read_bytes() for p in PATHS}


# --- Template content ----------------------------------------------------------------


def test_exactly_eight_files(client, repo):  # AC1
    assert files_outside_git(repo) == set()
    rendered(client, repo)
    assert files_outside_git(repo) == set(PATHS)


def test_agent_frontmatter(client, repo):  # AC2
    files = rendered(client, repo)
    opus = {"spec-writer", "builder", "review-security", "approver"}
    for agent in AGENTS:
        meta = frontmatter(files[f".claude/agents/{agent}.md"])
        assert meta["name"] == agent
        assert meta["model"] == ("opus" if agent in opus else "sonnet")
        assert meta["tools"] == ("Read, Edit, Write, Grep, Glob, Bash" if agent == "builder"
                                 else "Read, Grep, Glob, Bash")


def test_skill_frontmatter(client, repo):  # AC3
    text = rendered(client, repo)[SKILL]
    meta = frontmatter(text)
    assert meta["name"] == "factory"
    assert meta["description"].strip()
    assert "disable-model-invocation" not in text
    assert "$ARGUMENTS" in text[text.index("\n---\n") + 5:]


def test_skill_commands(client, repo):  # AC4
    text = rendered(client, repo)[SKILL]
    for stage in ("spec", "build", "agent_review", "approval", "human_review", "escalated"):
        assert f"fctl stage <id> {stage}" in text
    for needed in ("fctl show <id>", "fctl show <id> --feedback", "fctl round <id>", "builder-<id>"):
        assert needed in text


def test_agents_post_own_records(client, repo):  # AC5
    files = rendered(client, repo)
    agent = {a: files[f".claude/agents/{a}.md"] for a in AGENTS}
    assert "fctl spec <id>" in agent["spec-writer"]
    assert "fctl submit <id>" in agent["builder"]
    for r in ("security", "ux", "ui", "code"):
        assert f"fctl verdict <id> {r}" in agent[f"review-{r}"]
        assert f"fctl comment <id> {r}" in agent[f"review-{r}"]
    assert "fctl decide <id>" in agent["approver"]
    for name, text in agent.items():
        assert "fctl show <id>" in text
        if name.startswith("review-") or name == "approver":
            assert "fctl diff <id>" in text


def test_values_rendered(client, repo):  # AC6
    files = rendered(client, repo, default_branch="develop")
    for value in ("api-server", "develop", "make check"):
        assert value in files[SKILL]
    assert "make check" in files[BUILDER]
    assert "make check" in files[".claude/agents/review-code.md"]
    for text in files.values():
        for leftover in ("{{", "}}", "{%"):
            assert leftover not in text


def test_only_allowlisted_fctl_commands(client, repo):  # AC7
    files = rendered(client, repo)
    allowed = {"show", "diff", "spec", "submit", "verdict", "comment", "decide", "stage", "round"}
    for path, text in files.items():
        assert set(re.findall(r"\bfctl ([a-z]+)\b", text)) <= allowed, path
    assert "never commit" in files[SKILL].lower()
    assert "never commit" in files[BUILDER].lower()


def test_no_bootstrap_factory_leftovers(client, repo):  # AC8
    banned = ("board.json", "factory/jobs", "FACTORY.md", "§", "gh pr", "git worktree", "/factory next",
              "/factory approve", "/factory rework", "/factory resume", "FCTL_HOME", "uv run pytest")
    for path, text in rendered(client, repo).items():
        for word in banned:
            assert word not in text, (path, word)


def test_test_cmd_verbatim(client, repo):  # AC9
    cmd = '{{ name }} && echo "<b>&amp;"'
    assert cmd in rendered(client, repo, test_cmd=cmd)[BUILDER]


# --- POST /api/projects/{id}/factory -----------------------------------------------


def test_create_fresh(client, repo):  # AC10
    r = create(client, connect(client, repo), {"overwrite": False})
    assert r.status_code == 200
    assert r.json() == {"written": PATHS, "skipped": [], "commit_hint": HINT}


def test_existing_files_skipped(client, repo):  # AC11
    pid = connect(client, repo)
    create(client, pid)
    (repo / BUILDER).write_text("hand edit\n")
    before = snapshot(repo)
    r = create(client, pid, {})
    assert r.status_code == 200
    assert r.json() == {"written": [], "skipped": PATHS, "commit_hint": HINT}
    assert snapshot(repo) == before
    assert before[BUILDER] == b"hand edit\n"


def custom_builder(repo):
    (repo / BUILDER).parent.mkdir(parents=True)
    (repo / BUILDER).write_text("custom\n")


def test_one_existing_skipped(client, repo):  # AC12
    custom_builder(repo)
    r = create(client, connect(client, repo), {"overwrite": False})
    assert r.json() == {"written": [p for p in PATHS if p != BUILDER], "skipped": [BUILDER], "commit_hint": HINT}
    assert (repo / BUILDER).read_text() == "custom\n"


def test_overwrite(client, repo):  # AC13
    custom_builder(repo)
    r = create(client, connect(client, repo), {"overwrite": True})
    assert r.json() == {"written": PATHS, "skipped": [], "commit_hint": HINT}
    assert "fctl submit <id>" in (repo / BUILDER).read_text()


def test_factory_state_through_commit(client, repo):  # AC14
    pid = connect(client, repo)

    def state():
        return client.get("/api/projects", params={"path": str(repo)}).json()["factory"]

    assert state() == "none"
    create(client, pid)
    assert state() == "uncommitted"
    git(repo, "add", ".claude/skills/factory", ".claude/agents")
    git(repo, "commit", "-q", "-m", "Add factory")
    assert state() == "ready"
    assert git(repo, "status", "--porcelain") == ""


def test_factory_version(client, repo, tmp_path):  # AC15
    pid = connect(client, repo)
    version = "SELECT factory_version FROM projects WHERE id = ?"
    assert sql(version, (pid,)) == [(None,)]
    create(client, pid)
    assert sql(version, (pid,)) == [(1,)]

    other = tmp_path / "other"
    git(tmp_path, "init", "-q", "-b", "main", str(other))
    for p in PATHS:
        (other / p).parent.mkdir(parents=True, exist_ok=True)
        (other / p).write_text("mine\n")
    other_id = connect(client, other)
    assert create(client, other_id).json()["written"] == []
    assert sql(version, (other_id,)) == [(None,)]


@pytest.mark.parametrize("test_cmd", [None, "   "])
def test_no_test_cmd(client, repo, test_cmd):  # AC16
    r = create(client, connect(client, repo, test_cmd=test_cmd))
    assert r.status_code == 409
    assert r.json() == {"detail": NO_TEST_CMD}
    assert not (repo / ".claude").exists()


@pytest.mark.parametrize("kind", ["deleted", "file"])
def test_path_not_a_directory(client, tmp_path, kind):  # AC17
    path = tmp_path / "project"
    if kind == "file":
        path.write_text("x")
    r = create(client, connect(client, path))
    assert r.status_code == 409
    assert r.json() == {"detail": f"{path} is not a directory"}
    if kind == "file":
        assert path.read_text() == "x"
    else:
        assert not path.exists()


@pytest.mark.parametrize("overwrite", [False, True])
def test_symlink_out_refused(client, repo, tmp_path, overwrite):  # AC18
    outside = tmp_path / "outside"
    outside.mkdir()
    (repo / ".claude").mkdir()
    (repo / ".claude" / "agents").symlink_to(outside)
    r = create(client, connect(client, repo), {"overwrite": overwrite})
    assert r.status_code == 409
    assert r.json() == {"detail": ".claude/agents/spec-writer.md resolves outside the project"}
    assert list(outside.iterdir()) == []
    assert not (repo / SKILL).exists()


def test_unknown_project_and_no_header(client, repo):  # AC19
    assert create(client, 999).status_code == 404
    assert create(client, connect(client, repo), headers={}).status_code == 403
    assert files_outside_git(repo) == set()


def test_review_code_checks_layout(client, repo):  # 034 AC3
    text = rendered(client, repo)[".claude/agents/review-code.md"]
    assert "layout and import rules" in text
    assert "§" not in text and "FACTORY.md" not in text
