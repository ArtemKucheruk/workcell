import os
import re
from html import unescape
from urllib.parse import parse_qs, urlsplit

import pytest
from conftest import commit, git, write
from test_review import H, header, not_found_page, text

SECRET = "TOP-SECRET-7f3a"
APP = 'def main():\n    x = "<b>&</b>"\n    return x\n'


def connect(client, path, name="demo") -> int:
    body = {"path": str(path), "workspace": "personal", "name": name, "default_branch": "main"}
    r = client.post("/api/projects/connect", json=body, headers=H)
    assert r.status_code == 200, r.text
    return r.json()["id"]


@pytest.fixture
def fixture_repo(repo, tmp_path):
    """The spec's fixture: 4 tracked files, an untracked notes.txt, an ignored .env, and a secret
    next to the repo."""
    commit(repo, {"README.md": "# Hello\n", "src/app.py": APP, "docs/guide.md": "Guide\n", ".gitignore": ".env\n"})
    write(repo, {"notes.txt": "untracked notes", ".env": "API=ignored-env"})
    (tmp_path / "secret.txt").write_text(SECRET)
    return repo


@pytest.fixture
def pid(client, fixture_repo):
    return connect(client, fixture_repo)


def get(client, pid, path=None):
    r = client.get(f"/projects/{pid}/code", params=None if path is None else {"path": path})
    return r


def page(client, pid, path=None):
    r = get(client, pid, path)
    assert r.status_code == 200, r.text
    return r.text


def links(html):
    """{tracked path: raw href} of the tree's file links."""
    hrefs = re.findall(r'<a href="(/projects/\d+/code\?[^"]*)"', html)
    return {parse_qs(urlsplit(unescape(h)).query)["path"][0]: unescape(h) for h in hrefs}


def gutter(html):
    return re.search(r'<pre class="gutter"[^>]*>(.*?)</pre>', html, re.S)[1].split("\n")


def test_tree_lists_tracked_files(client, pid):  # AC1
    html = page(client, pid)
    assert sorted(links(html)) == [".gitignore", "README.md", "docs/guide.md", "src/app.py"]
    for href in links(html).values():
        assert href.startswith(f"/projects/{pid}/code?path=")
    assert "notes.txt" not in html


@pytest.mark.parametrize("path", [None, ""])
def test_landing_renders_readme(client, pid, path):  # AC2
    assert "<h1>Hello</h1>" in page(client, pid, path)


def test_readme_raw_html_off(client, repo):  # AC3
    commit(repo, {"README.md": "# Hi\n\n<script>alert(1)</script>\n"})
    html = page(client, connect(client, repo))
    assert "&lt;script&gt;alert(1)" in html
    assert "<script>alert(1)" not in html


def test_no_readme(client, repo):  # AC4
    commit(repo, {"src/app.py": APP})
    html = page(client, connect(client, repo))
    assert list(links(html)) == ["src/app.py"]
    assert "No README.md in this project." in html


def test_no_tracked_files(client, repo):  # AC5
    html = page(client, connect(client, repo))
    assert "No tracked files." in html
    assert links(html) == {} and 'id="file-tree"' not in html


@pytest.mark.parametrize("content", ["a = 1\nb = 2\nc = 3\n", "a = 1\r\nb = 2\r\nc = 3", "a = 1\rb = 2\rc = 3\r"])
def test_line_numbers(client, repo, content):  # AC6
    commit(repo, {"src/app.py": content})
    html = page(client, connect(client, repo), "src/app.py")
    for line in ("a = 1", "b = 2", "c = 3"):
        assert line in html
    assert gutter(html) == ["1", "2", "3"]


def test_code_escaped(client, pid):  # AC7
    html = page(client, pid, "src/app.py")
    assert "&lt;b&gt;&amp;&lt;/b&gt;" in html
    assert "<b>&</b>" not in html


def test_language_from_extension(client, repo):  # AC8
    commit(repo, {"src/app.py": APP, "Makefile": "all:\n\techo hi\n"})
    pid = connect(client, repo)
    assert '<code data-lang="py">' in page(client, pid, "src/app.py")
    html = page(client, pid, "Makefile")
    assert "echo hi" in html and "<pre><code>all:" in html


def test_binary_not_shown(client, repo):  # AC9
    commit(repo, {"blob.bin": b"BINARYTEXT\0" + b"more BINARYTEXT"})
    html = page(client, connect(client, repo), "blob.bin")
    assert "Binary file not shown." in html
    assert "BINARYTEXT" not in html


def test_size_limit(client, repo):  # AC10
    commit(repo, {"big.txt": b"x" * (1024 * 1024 + 1), "max.txt": b"y" * (1024 * 1024)})
    pid = connect(client, repo)
    html = page(client, pid, "big.txt")
    assert "File over 1 MB not shown." in html and "x" * 100 not in html
    html = page(client, pid, "max.txt")
    assert "y" * (1024 * 1024) in html and "not shown" not in html


def test_non_utf8_replaced(client, repo):  # AC11
    commit(repo, {"latin.txt": b"caf\xe9\n"})
    assert "caf�" in page(client, connect(client, repo), "latin.txt")


def test_header_branch(client, pid, fixture_repo):  # AC12
    top = header(page(client, pid))
    assert f'<a href="/projects/{pid}">demo</a>' in top
    assert "<code>main</code>" in top
    git(fixture_repo, "checkout", "-q", "-b", "feature-x")
    assert "<code>feature-x</code>" in header(page(client, pid))
    git(fixture_repo, "checkout", "-q", "--detach")
    assert "<code>detached HEAD</code>" in header(page(client, pid))


def test_dotdot_404(client, pid):  # AC13
    r = get(client, pid, "../secret.txt")
    assert not_found_page(r) == "../secret.txt is not a tracked file in demo"
    assert SECRET not in r.text


def test_untracked_paths_404(client, pid, tmp_path):  # AC14
    for path in (str(tmp_path / "secret.txt"), "notes.txt", ".env", ".git/config", "src"):
        r = get(client, pid, path)
        assert not_found_page(r), path
        assert SECRET not in r.text and "ignored-env" not in r.text and "untracked notes" not in r.text


def test_symlink_outside(client, fixture_repo, tmp_path):  # AC15
    os.symlink(tmp_path / "secret.txt", fixture_repo / "leak")
    commit(fixture_repo)
    pid = connect(client, fixture_repo)
    assert "leak" in links(page(client, pid))
    html = page(client, pid, "leak")
    assert "Not shown: points outside the project." in html
    assert SECRET not in html


def test_readme_symlink_outside(client, repo, tmp_path):  # AC16
    (tmp_path / "secret.txt").write_text(SECRET)
    os.symlink(tmp_path / "secret.txt", repo / "README.md")
    commit(repo)
    html = page(client, connect(client, repo))
    assert "Not shown: points outside the project." in html
    assert SECRET not in html


def test_symlink_inside(client, fixture_repo):  # AC17
    os.symlink("src/app.py", fixture_repo / "alias.py")
    commit(fixture_repo)
    html = page(client, connect(client, fixture_repo), "alias.py")
    assert "&lt;b&gt;&amp;&lt;/b&gt;" in html and "def main():" in html


def test_odd_name_link(client, repo):  # AC18
    commit(repo, {"a b#c&d.txt": "odd name content\n"})
    pid = connect(client, repo)
    r = client.get(links(page(client, pid))["a b#c&d.txt"])
    assert r.status_code == 200 and "odd name content" in r.text


def test_tree_open_and_current(client, pid):  # AC19
    html = page(client, pid, "src/app.py")
    assert re.search(r"<details open><summary>src/</summary>", html)
    assert re.search(r"<details><summary>docs/</summary>", html)
    assert re.search(r'<a href="[^"]*path=src/app.py" aria-current="page">app.py</a>', html)
    assert html.count(' aria-current="page">') == 1


def test_unknown_project_404(client):  # AC20
    assert not_found_page(client.get("/projects/999/code")) == "Project #999 not found"


@pytest.mark.parametrize("kind", ["missing", "not a repo"])
def test_git_failure_alert(client, tmp_path, kind):  # AC21
    path = tmp_path / kind.replace(" ", "-")
    if kind == "not a repo":
        path.mkdir()
    html = page(client, connect(client, path))
    alert = re.search(r'<p role="alert">(.*?)</p>', html, re.S)[1]
    assert unescape(text(alert)).startswith(f"Can't list files in {path}: ")
    assert 'id="file-tree"' not in html and links(html) == {}
