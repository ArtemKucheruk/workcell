import json

import pytest

from workcell.lib.transcript import events, first_round, folder_name, summary


def line(**fields) -> str:
    return json.dumps(fields)


def user(content, ts="2026-10-18T14:21:00.100Z") -> str:
    return line(type="user", timestamp=ts, message={"role": "user", "content": content})


def assistant(msg_id, model, usage, ts, text="ok") -> str:
    return line(type="assistant", timestamp=ts, message={"id": msg_id, "model": model, "usage": usage,
                                                          "content": [{"type": "text", "text": text}]})


def parsed(*lines: str) -> list[dict]:
    return events("\n".join(lines).encode())


def test_folder_name():  # AC3
    assert folder_name("/x/repo/.claude/worktrees/12-rate_limit") == "-x-repo--claude-worktrees-12-rate-limit"


def test_folder_name_resolves_symlinks(tmp_path):  # AC3: after os.path.realpath
    (tmp_path / "real").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "real")
    assert folder_name(str(tmp_path / "link")) == folder_name(str(tmp_path / "real"))
    assert folder_name(str(tmp_path / "link")).endswith("-real")


@pytest.mark.parametrize("content, n", [
    ("Task 12, round 2.", 2),
    ("Job 030-agent-transcripts, round 1.", 1),
    ('<teammate-message teammate_id="team-lead">\nJob 030-agent-transcripts, round 1.\n</teammate-message>', 1),
    ([{"type": "text", "text": "Read the spec.\nTask 7, round 3. Go."}], 3),
    ("Task 12.", None),
    ("/factory 12", None),
])
def test_round(content, n):  # AC7
    assert first_round(parsed(user(content))) == n
    assert summary(parsed(user(content)))["round"] == n


def test_round_only_from_first_user_message():  # AC7
    lines = parsed(line(type="system", content="Task 1, round 9."), user("Task 12."), user("Task 12, round 2."))
    assert first_round(lines) is None


def test_summary():  # AC8
    a = {"input_tokens": 10, "cache_creation_input_tokens": 500, "cache_read_input_tokens": 1000, "output_tokens": 3}
    b = {"input_tokens": 1, "cache_creation_input_tokens": 7, "cache_read_input_tokens": 2000, "output_tokens": 40}
    found = summary(parsed(
        user("Task 12, round 2.", ts="2026-10-18T14:21:38.689Z"),
        assistant("A", "claude-opus-4-1", a, "2026-10-18T14:21:40.000Z", text="part 1"),
        assistant("A", "claude-opus-4-1", a, "2026-10-18T14:21:41.000Z", text="part 2"),
        line(type="attachment", timestamp="2026-10-18T14:22:00.000Z"),
        assistant("B", "claude-sonnet-4-5", b, "2026-10-18T14:25:09.999Z"),
        "not json",
    ))
    assert found == {
        "round": 2, "model": "claude-opus-4-1", "turns": 2,
        "input_tokens": 11, "cache_read_tokens": 3000, "output_tokens": 43,
        "started_at": "2026-10-18T14:21:38Z", "ended_at": "2026-10-18T14:25:09Z",
        "team_name": None, "agent_name": None,
    }


def test_summary_skips_synthetic_model_and_lines_without_id():  # AC8, Q5
    usage = {"input_tokens": 5, "cache_read_input_tokens": 6, "output_tokens": 7}
    found = summary(parsed(
        line(type="assistant", message={"model": "<synthetic>", "usage": usage, "content": []}),
        assistant("A", "claude-opus-4-1", usage, "2026-10-18T14:21:40Z"),
    ))
    assert (found["model"], found["turns"], found["input_tokens"], found["output_tokens"]) == ("claude-opus-4-1", 1, 5, 7)


def test_summary_of_nothing():  # Q6: no timestamp → None
    assert summary([]) == {
        "round": None, "model": None, "turns": 0, "input_tokens": 0, "cache_read_tokens": 0, "output_tokens": 0,
        "started_at": None, "ended_at": None, "team_name": None, "agent_name": None,
    }


def test_summary_team():  # AC6, Q2: the first line carrying a teamName
    found = summary(parsed(line(type="user", teamName="session-6f1c2e0a", agentName="builder-12"),
                           line(type="user", teamName="session-other", agentName="x")))
    assert (found["team_name"], found["agent_name"]) == ("session-6f1c2e0a", "builder-12")
