from controllers.test_run_control import FIXTURE_ITEMS, FIXTURE_LOG

from claude_factories.lib.run_log import log_items


def test_log_items_without_the_app():  # 036 AC7
    lines = FIXTURE_LOG.split("\n")[:-1]
    assert len(lines) == 8
    assert log_items(lines, 0) == FIXTURE_ITEMS
    assert log_items(lines, 3) == FIXTURE_ITEMS[-4:]
