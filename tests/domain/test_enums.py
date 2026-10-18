from claude_factories.domain.enums import STAGE_STATUS, Reviewer, Stage, Status


def test_enums():  # 034 AC15
    assert list(Status) == ["backlog", "in_progress", "review", "done"]
    assert list(Stage) == ["spec", "build", "agent_review", "approval", "rework", "human_review", "escalated"]
    assert list(Reviewer) == ["security", "ux", "ui", "code"]


def test_stage_status():  # 034 AC15
    assert STAGE_STATUS == {
        "spec": "in_progress", "build": "in_progress", "agent_review": "in_progress", "approval": "in_progress",
        "rework": "in_progress", "human_review": "review", "escalated": "review",
    }
    assert list(STAGE_STATUS) == list(Stage)
