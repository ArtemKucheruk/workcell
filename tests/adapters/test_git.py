"""099: the git adapter's worktrunk calls (docs/MVP.md §4.1, §4.7)."""

import json
import subprocess
import tomllib

import pytest

from claude_factories.adapters import git as adapter
from claude_factories.domain.errors import Conflict


def test_every_subprocess_has_argv_and_timeout(monkeypatch):  # 099 AC6
    seen = []

    def fake_run(argv, **kwargs):
        seen.append((argv, kwargs))
        out = json.dumps({"path": "/r/.claude/worktrees/1-x"}) if "switch" in argv else ""
        if not kwargs.get("text"):  # git_ok and git_stdout read bytes
            return subprocess.CompletedProcess(argv, 0, out.encode(), b"")
        return subprocess.CompletedProcess(argv, 0, out, "")

    monkeypatch.setattr(adapter.subprocess, "run", fake_run)
    g = adapter.SubprocessGit()
    g.exclude_path("/r")
    assert g.wt_create("/r", "factory/1-x", "/r/.claude/worktrees/1-x", "main") == "/r/.claude/worktrees/1-x"
    g.wt_copy_ignored("/r/.claude/worktrees/1-x", "main")  # git ls-files before and after the copy
    g.wt_remove("/r", "factory/1-x")
    g.ls_files("/r")
    g.commit_all("/r", "m")
    assert len(seen) == 9
    for argv, kwargs in seen:
        assert isinstance(argv, list) and argv[0] in ("git", "wt")
        assert kwargs.get("timeout") and not kwargs.get("shell")
    wt = [(argv, kwargs["timeout"]) for argv, kwargs in seen if argv[0] == "wt"]
    assert wt == [
        (["wt", "-C", "/r", "switch", "--create", "factory/1-x", "--base", "main", "--no-cd", "--no-hooks",
          "--format", "json"], 60),
        (["wt", "-C", "/r/.claude/worktrees/1-x", "step", "copy-ignored"], 300),
        (["wt", "-C", "/r", "remove", "--foreground", "--no-delete-branch", "--no-hooks", "factory/1-x"], 60),
    ]


def test_wt_config():  # 099 Q1, Q2, round 1 security finding 1
    assert adapter.wt_config("/r/.claude/worktrees/1-x").splitlines() == [
        'worktree-path = "/r/.claude/worktrees/1-x"', "", "[step.copy-ignored]",
        'exclude = [".venv/", ".claude/worktrees/", ".claude/settings.local.json", ".fctl/"]']
    assert adapter.wt_config(None).splitlines()[0] == ""


def test_wt_config_is_toml_for_any_path():  # 099 round 1 security nit: an emoji, DEL, a quote, a backslash
    path = '/r/🚀 x\x7f"\\/.claude/worktrees/1-x'
    assert tomllib.loads(adapter.wt_config(path))["worktree-path"] == path


@pytest.mark.parametrize("out, path", [
    ('{"action": "created", "path": "/w"}', "/w"),
    ('{"worktree": {"branch": "b", "path": "/w"}}', "/w"),
    ('[{"path": "/w"}]', "/w"),
    ("not json", None),
    ('{"branch": "b"}', None),
])
def test_json_path(out, path):  # 099 AC1
    assert adapter.json_path(out) == path


def test_wt_missing_is_409(monkeypatch, tmp_path):  # 099 AC4
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(Conflict) as e:
        adapter.SubprocessGit().wt_create(str(tmp_path), "factory/1-x", str(tmp_path / "w"), "main")
    assert e.value.detail == "wt (worktrunk) isn't installed: brew install worktrunk, then run again"
