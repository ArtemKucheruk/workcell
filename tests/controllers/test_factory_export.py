"""052: a factory design's files: GET …/files, GET …/download, POST …/write (docs/data-model-and-api.md §6.1)."""

import io
import zipfile

import pytest

from .test_factory import BUILDER, H, HINT, NO_TEST_CMD, PATHS, SKILL, connect, create, frontmatter

DEFAULT_LOOP = """1. `fctl show <id>`: read the task, then continue from its current stage (table above).
2. spec → `fctl stage <id> spec`. Spawn `spec-writer`: "Task <id>." Wait for it.
   `fctl show <id>` still says `_No spec yet._` → stop and report.
3. build, the next round n → `fctl stage <id> build`.
   - Round 1, or no `builder-<id>` in this session: spawn `builder` named `builder-<id>`:
     "Task <id>, round <n>."
   - Otherwise SendMessage `builder-<id>`: "Round <n>. Round <n-1> verdicts: `fctl show <id> --round <n-1>`."
     SendMessage may be a deferred tool: load it with ToolSearch `select:SendMessage`.

   Wait for it. Done when the builder has run `fctl submit <id>` and `fctl round <id>` shows
   round n. Not there → ask the builder once to submit, then stop and report.
4. agent_review → `fctl stage <id> agent_review`. Spawn these in ONE message, each with "Task <id>.":
   `review-security`, `review-ux`, `review-ui`, `review-code`.
   WAIT FOR ALL: go on only when `fctl round <id>` shows a verdict from each. Spawn a reviewer
   that ended without posting its verdict once more. Never message the builder mid-round.
5. All reviews PASS? yes → step 6, no → step 7.
6. approval → `fctl stage <id> approval`. Spawn `approver`: "Task <id>, rounds used <x> of 2."
   Rounds exhausted with CHANGES → it must ESCALATE. Wait for it.
   Then step 8.
7. Rounds used < 2? yes → step 3, no → step 6.
8. Read the approver's latest decision in `fctl show <id> --round <n>`. APPROVE →
   `fctl stage <id> human_review`. ESCALATE, no decision, or anything else →
   `fctl stage <id> escalated`. Stop and report the decision's summary: the task now waits
   on me in Review."""
CONDITION_EDGE = {"id": "e99", "source": "builder", "sourceHandle": None, "target": "all-pass"}  # BE7's
BE7_DETAIL = ("builder leads to review-security, review-ux, review-ui, review-code, All reviews PASS?:"
              " a condition must be the only node it leads to")


def new_factory(client, project_id, name="factory") -> dict:
    r = client.post(f"/api/projects/{project_id}/factories", json={"name": name}, headers=H)
    assert r.status_code == 201, r.text
    return r.json()


def save_graph(client, factory, graph):
    r = client.put(f"/api/factories/{factory['id']}", json={"graph": graph}, headers=H)
    assert r.status_code == 200, r.text


def files(client, factory_id):
    return client.get(f"/api/factories/{factory_id}/files")


def contents(client, factory_id) -> dict[str, str]:
    r = files(client, factory_id)
    assert r.status_code == 200, r.text
    return {f["path"]: f["content"] for f in r.json()}


def download(client, factory_id):
    return client.get(f"/api/factories/{factory_id}/download")


def write(client, factory_id, body=None, headers=H):
    return client.post(f"/api/factories/{factory_id}/write", json={"overwrite": False} if body is None else body,
                       headers=headers)


def tree(root) -> dict[str, bytes]:
    """Every file under root but .git, by relative path, with its bytes (read through symlinks)."""
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*"))
            if p.is_file() and p.relative_to(root).parts[0] != ".git"}


def loop_body(skill_md: str) -> str:
    return skill_md.split("\n## The loop\n\n")[1].split("\n\n## Conditions\n")[0]


def same_as_create_factory(client, repo, **extra):
    """BE1/BE2: the default graph's files equal, byte for byte, what Create factory writes into the fresh repo."""
    pid = connect(client, repo, **extra)
    r = files(client, new_factory(client, pid)["id"])
    assert r.status_code == 200
    assert [f["path"] for f in r.json()] == PATHS
    assert create(client, pid).status_code == 200
    for f in r.json():
        assert (repo / f["path"]).read_bytes() == f["content"].encode(), f["path"]
    return {f["path"]: f["content"] for f in r.json()}


# --- GET /api/factories/{id}/files ----------------------------------------------------


def test_default_graph_is_create_factory(client, repo):  # BE1
    same_as_create_factory(client, repo, default_branch="develop")


def test_default_graph_test_cmd_verbatim(client, repo):  # BE2
    cmd = '{{ name }} && echo "<b>&amp;"'
    got = same_as_create_factory(client, repo, test_cmd=cmd)
    for agent in (BUILDER, ".claude/agents/review-code.md"):
        assert f"Test command for this repo: {cmd}\n" in got[agent]


def test_default_skill_md(client, repo):  # BE3
    text = contents(client, new_factory(client, connect(client, repo))["id"])[SKILL]
    assert frontmatter(text)["name"] == "factory"
    assert "\n# /factory $ARGUMENTS\n" in text
    assert loop_body(text) == DEFAULT_LOOP


def test_skill_named_by_slug(client, repo):  # BE4
    pid = connect(client, repo)
    got = contents(client, new_factory(client, pid, "Nightly Build!")["id"])
    path = ".claude/skills/nightly-build/SKILL.md"
    assert list(got)[0] == path
    meta = frontmatter(got[path])
    assert meta["name"] == "nightly-build"
    assert '"/nightly-build <task-id>"' in meta["description"]
    assert "\n# /nightly-build $ARGUMENTS\n" in got[path]
    assert list(contents(client, new_factory(client, pid, "!!!")["id"]))[0] == SKILL


# --- Refusals, on all three -------------------------------------------------------------


def test_compile_refusal_everywhere(client, repo):  # BE10
    f = new_factory(client, connect(client, repo))
    save_graph(client, f, f["graph"] | {"edges": [*f["graph"]["edges"], CONDITION_EDGE]})
    for r in (files(client, f["id"]), download(client, f["id"]), write(client, f["id"]),
              write(client, f["id"], {"overwrite": True})):
        assert r.status_code == 422
        assert r.json() == {"detail": BE7_DETAIL}
    assert not (repo / ".claude").exists()


@pytest.mark.parametrize("test_cmd", [None, "   "])
def test_no_test_cmd_and_unknown_id(client, repo, test_cmd):  # BE11
    f = new_factory(client, connect(client, repo, test_cmd=test_cmd))
    for r in (files(client, f["id"]), download(client, f["id"]), write(client, f["id"])):
        assert r.status_code == 409
        assert r.json() == {"detail": NO_TEST_CMD}
    assert tree(repo) == {}
    for r in (files(client, 99), download(client, 99), write(client, 99)):
        assert r.status_code == 404
        assert r.json() == {"detail": "Factory #99 not found"}


# --- GET /api/factories/{id}/download ------------------------------------------------------


def test_download(client, repo, tmp_path):  # BE12
    f = new_factory(client, connect(client, repo), "default")
    r = download(client, f["id"])
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert r.headers["content-disposition"] == 'attachment; filename="api-server-default.zip"'
    assert r.headers["x-content-type-options"] == "nosniff"
    want = files(client, f["id"]).json()
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        assert [i.filename for i in zf.infolist()] == [w["path"] for w in want]
        assert all(i.compress_type == zipfile.ZIP_DEFLATED for i in zf.infolist())
        for w in want:
            assert zf.read(w["path"]) == w["content"].encode()

    other = tmp_path / "other"
    other.mkdir()
    f = new_factory(client, connect(client, other, name="My App"), 'Night "run"')
    assert download(client, f["id"]).headers["content-disposition"] == 'attachment; filename="my-app-night-run.zip"'


# --- POST /api/factories/{id}/write ---------------------------------------------------------


@pytest.mark.parametrize("name, hint", [
    ("nightly", 'git add .claude/skills/nightly .claude/agents && git commit -m "Add factory"'),
    ("factory", HINT),
])
def test_write_fresh(client, repo, name, hint):  # BE13
    f = new_factory(client, connect(client, repo), name)
    want = contents(client, f["id"])
    r = write(client, f["id"], {"overwrite": False})
    assert r.status_code == 200
    assert r.json() == {"written": list(want), "skipped": [], "commit_hint": hint}
    assert tree(repo) == {path: content.encode() for path, content in want.items()}


def test_write_skips_then_overwrites(client, repo):  # BE14
    f = new_factory(client, connect(client, repo), "nightly")
    paths = list(contents(client, f["id"]))
    write(client, f["id"])
    (repo / BUILDER).write_text("hand edit\n")
    before = tree(repo)
    r = write(client, f["id"], {})
    assert r.status_code == 200
    assert (r.json()["written"], r.json()["skipped"]) == ([], paths)
    assert tree(repo) == before
    r = write(client, f["id"], {"overwrite": True})
    assert (r.json()["written"], r.json()["skipped"]) == (paths, [])
    assert "fctl submit <id>" in (repo / BUILDER).read_text()


@pytest.mark.parametrize("overwrite", [False, True])
def test_write_symlink_out(client, repo, tmp_path, overwrite):  # BE15
    outside = tmp_path / "outside"
    outside.mkdir()
    (repo / ".claude").mkdir()
    (repo / ".claude" / "agents").symlink_to(outside)
    f = new_factory(client, connect(client, repo), "nightly")
    r = write(client, f["id"], {"overwrite": overwrite})
    assert r.status_code == 409
    assert r.json() == {"detail": ".claude/agents/spec-writer.md resolves outside the project"}
    assert list(outside.iterdir()) == []
    assert not (repo / ".claude" / "skills").exists()


@pytest.mark.parametrize("overwrite", [False, True])
def test_write_symlink_inside_and_not_a_directory(client, repo, tmp_path, overwrite):  # BE16
    (repo / "elsewhere").mkdir()
    (repo / ".claude").mkdir()
    (repo / ".claude" / "skills").symlink_to(repo / "elsewhere")
    f = new_factory(client, connect(client, repo), "nightly")
    r = write(client, f["id"], {"overwrite": overwrite})
    assert r.status_code == 409
    assert r.json() == {"detail": ".claude/skills is a symlink"}
    assert tree(repo) == {}

    (repo / ".claude" / "skills").unlink()
    (repo / "notes.md").write_text("mine\n")
    (repo / ".claude" / "agents").mkdir()
    (repo / BUILDER).symlink_to(repo / "notes.md")
    r = write(client, f["id"], {"overwrite": overwrite})
    assert r.status_code == 409
    assert r.json() == {"detail": ".claude/agents/builder.md is a symlink"}
    assert tree(repo) == {"notes.md": b"mine\n", BUILDER: b"mine\n"}

    path = tmp_path / "project"
    f = new_factory(client, connect(client, path, name="gone"), "nightly")
    r = write(client, f["id"], {"overwrite": overwrite})
    assert r.status_code == 409
    assert r.json() == {"detail": f"{path} is not a directory"}
    assert not path.exists()


def test_factory_state_unchanged(client, repo):  # BE18
    pid = connect(client, repo)

    def state():
        return client.get("/api/projects", params={"path": str(repo)}).json()["factory"]

    assert write(client, new_factory(client, pid, "nightly")["id"]).status_code == 200
    assert state() == "none"
    assert write(client, new_factory(client, pid, "factory")["id"]).status_code == 200
    assert state() == "uncommitted"


def test_write_needs_header(client, repo):  # BE19
    f = new_factory(client, connect(client, repo))
    assert write(client, f["id"], headers={}).status_code == 403
    assert tree(repo) == {}
