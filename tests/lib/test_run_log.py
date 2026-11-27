from controllers.test_agents_page import AGENTS, AGENTS_LOG, MALFORMED_LOG
from controllers.test_run_control import FIXTURE_ITEMS, FIXTURE_LOG

from workcell.lib.run_log import log_items, run_agents


def test_log_items_without_the_app():  # 036 AC7
    lines = FIXTURE_LOG.split("\n")[:-1]
    assert len(lines) == 8
    assert log_items(lines, 0) == FIXTURE_ITEMS
    assert log_items(lines, 3) == FIXTURE_ITEMS[-4:]


def test_run_agents_without_the_app():  # 053 BE3, BE6
    assert run_agents(AGENTS_LOG.split("\n")[:-1]) == AGENTS
    assert run_agents(MALFORMED_LOG.split("\n")) == AGENTS  # the trailing partial line too
    assert run_agents([]) == [AGENTS[0] | {"last_tool": None}]
