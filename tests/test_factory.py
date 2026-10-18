import html
import re

from conftest import git
from controllers.test_factory import BUILDER, H, HINT, NO_TEST_CMD, PATHS, SKILL, connect, files_outside_git


# --- Board -----------------------------------------------------------------------------


def header(client, project_id):
    """The page before #board, and the whole page."""
    r = client.get(f"/projects/{project_id}")
    assert r.status_code == 200
    return r.text.split('<div id="board"')[0], r.text


def factory_form(head, project_id):
    return re.findall(rf'<form hx-post="/projects/{project_id}/factory" hx-target="#factory-result">(.*?)</form>',
                      head, re.S)


def text(fragment):
    """Tags stripped, entities unescaped, whitespace collapsed."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def test_create_factory_form(client, repo):  # AC20
    pid = connect(client, repo)
    head, _ = header(client, pid)
    [form] = factory_form(head, pid)
    [label] = re.findall(r"<label>(.*?)</label>", form, re.S)
    assert '<input type="checkbox" name="overwrite">' in label
    assert "Overwrite" in text(label)
    assert re.findall(r"<button[^>]*>(.*?)</button>", form) == ["Create factory"]
    assert 'id="factory-result"' in head


def test_form_by_state(client, repo):  # AC21
    pid = connect(client, repo)
    (repo / SKILL).parent.mkdir(parents=True)
    (repo / SKILL).write_text("# factory\n")
    head, _ = header(client, pid)
    assert len(factory_form(head, pid)) == 1
    git(repo, "add", SKILL)
    git(repo, "commit", "-q", "-m", "Add factory")
    _, page = header(client, pid)
    assert f'hx-post="/projects/{pid}/factory"' not in page
    assert "Create factory" not in page
    assert "Factory: ready ✓" in page


def post_form(client, project_id, data=None, headers=H):
    return client.post(f"/projects/{project_id}/factory", data=data or {}, headers=headers)


def test_form_post_writes(client, repo):  # AC22
    r = post_form(client, connect(client, repo))
    assert r.status_code == 200
    assert "<html" not in r.text
    shown = text(r.text)
    assert "Wrote 8 files:" in shown
    for p in PATHS:
        assert p in shown
        assert (repo / p).is_file()
    assert HINT in shown


def test_form_post_skips_then_overwrites(client, repo):  # AC23
    pid = connect(client, repo)
    post_form(client, pid)
    shown = text(post_form(client, pid).text)
    assert "Skipped 8 existing files" in shown and "Wrote" not in shown
    assert "Overwrite" in shown
    assert all(p in shown for p in PATHS)
    (repo / BUILDER).write_text("hand edit\n")
    shown = text(post_form(client, pid, {"overwrite": "on"}).text)
    assert "Wrote 8 files:" in shown and "Skipped" not in shown
    assert all(p in shown for p in PATHS)
    assert "fctl submit <id>" in (repo / BUILDER).read_text()


def test_form_post_error(client, repo):  # AC24
    r = post_form(client, connect(client, repo, test_cmd=None))
    assert r.status_code == 200
    [alert] = re.findall(r'<(\w+) role="alert">(.*?)</\1>', r.text, re.S)
    assert html.unescape(alert[1]) == NO_TEST_CMD
    assert not (repo / ".claude").exists()


def test_form_post_needs_header(client, repo):  # AC25
    assert post_form(client, connect(client, repo), headers={}).status_code == 403
    assert files_outside_git(repo) == set()
