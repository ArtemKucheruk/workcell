import re
from html import unescape
from urllib.parse import parse_qs, unquote, urlsplit

import pytest
from conftest import sql
from test_review import H, add_comment, add_task, header, not_found_page, page, post, project, section, task_row, text  # noqa: F401

SAMPLE = """\
diff --git a/app/auth.py b/app/auth.py
index 1111111..2222222 100644
--- a/app/auth.py
+++ b/app/auth.py
@@ -41,3 +41,3 @@ def login():
     user = authenticate(form)
-    if not user:
+    if not user and limiter.hit(client_key(request)):
         return deny()
@@ -60,2 +60,3 @@ def logout():
     session.clear()
+    audit("logout")
     return ok()
diff --git a/app/limits.py b/app/limits.py
new file mode 100644
index 0000000..3333333
--- /dev/null
+++ b/app/limits.py
@@ -0,0 +1,2 @@
+def client_key(request):
+    return request.client.host
\\ No newline at end of file
diff --git a/logo.png b/logo.png
new file mode 100644
index 0000000..4444444
Binary files /dev/null and b/logo.png differ
diff --git a/old_name b/new_name
similarity index 100%
rename from old_name
rename to new_name
diff --git a/tests/test_limits.py b/tests/test_limits.py
deleted file mode 100644
index 5555555..0000000
--- a/tests/test_limits.py
+++ /dev/null
@@ -1,2 +0,0 @@
-def test_old():
-    assert True
"""
B_PY = "diff --git a/b.py b/b.py\n--- a/b.py\n+++ b/b.py\n@@ -1 +1 @@\n-x\n+y\n"
FILES = ["app/auth.py", "app/limits.py", "logo.png", "new_name", "tests/test_limits.py"]


def submit(client, task, patch):
    r = client.post(f"/api/tasks/{task}/rounds", json={"base_sha": "abc1234", "patch": patch}, headers=H)
    assert r.status_code == 201, r.text
    return sql("SELECT id FROM rounds WHERE task_id = ? AND n = ?", (task, r.json()["round"]))[0][0]


@pytest.fixture
def sample(client, project):
    """A factory task (worktree and branch set) with the sample round as round 1."""
    task = add_task(project, branch="factory/12-x")
    submit(client, task, SAMPLE)
    return task


def files_tab(client, task, query="?round=1&tab=files"):
    return page(client, task, query)


def url(href):
    """(path, {param: value}, unquoted fragment) of an href taken from the page."""
    parts = urlsplit(unescape(href))
    return parts.path, {k: v[0] for k, v in parse_qs(parts.query).items()}, unquote(parts.fragment)


def tabs(html):
    """[(href, current, text)] of the tab bar's links."""
    nav = re.search(r'<nav class="tabs"[^>]*>(.*?)</nav>', html, re.S)[1]
    return [(url(href), bool(cur), text(t)) for href, cur, t in
            re.findall(r'<a href="([^"]*)"( aria-current="page")?>(.*?)</a>', nav, re.S)]


def table(html, path):
    """The <table> of the file section with id file:<path> (path HTML-escaped as on the page)."""
    found = re.search(rf'<section class="file" id="file:{re.escape(path)}">(.*?)</section>', html, re.S)[1]
    return re.search(r"<table [^>]*>.*?</table>", found, re.S)[0]


def trs(table_html):
    """[(class, inner html)] of a table's rows."""
    return re.findall(r'<tr class="([^"]*)">(.*?)</tr>', table_html, re.S)


def cell_text(cell):
    return unescape(re.sub(r"<[^>]+>", "", cell))


def row_tuple(cls, tr):
    """(class, *cell texts) with `·` for an empty cell; a one-cell row gives (class, text)."""
    return (cls, *(cell_text(c) or "·" for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)))


def rows(html, path):
    return [row_tuple(cls, tr) for cls, tr in trs(table(html, path))]


def after(html, path, anchor):
    """The (class, html) of the <tr> right after the row holding id="<anchor>"."""
    found = trs(table(html, path))
    i = next(i for i, (_, tr) in enumerate(found) if f'id="{anchor}"' in tr)
    return found[i + 1]


def add_inline(task, round_id, author, path, line, side, body):
    sql("INSERT INTO comments (task_id, round_id, author, path, line, side, body_md, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, '2026-01-01T00:00:00Z')", (task, round_id, author, path, line, side, body))


def round_id(task, n):
    return sql("SELECT id FROM rounds WHERE task_id = ? AND n = ?", (task, n))[0][0]


# --- Tabs ----------------------------------------------------------------------------


def test_tab_bar(client, sample):  # AC1
    review = f"/tasks/{sample}/review"
    conversation = ((review, {"round": "1"}, ""), "Conversation")
    files = ((review, {"round": "1", "tab": "files"}, ""), "Files changed 5")
    for query, current in (("", "Conversation"), ("?tab=files", "Files changed 5")):
        html = page(client, sample, query)
        assert html.index("</header>") < html.index('<nav class="tabs"')
        assert [(link, label) for link, _, label in tabs(html)] == [conversation, files]
        assert [label for _, cur, label in tabs(html) if cur] == [current]


def test_tab_bodies(client, sample):  # AC2
    html = files_tab(client, sample)
    for name in ("description", "rounds", "approver", "timeline"):
        assert section(html, name) is None
    assert "<textarea" not in html.split("</header>", 1)[1]  # 009's Summary box sits in the header
    for query in ("", "?tab=conversation", "?tab=xyz"):
        html = page(client, sample, query)
        assert section(html, "timeline") is not None
        assert 'id="file-tree"' not in html and 'class="diff-table"' not in html  # base.html's CSS names it


def test_round_form_keeps_tab(client, sample):  # AC3
    hidden = '<input type="hidden" name="tab" value="files">'
    form = re.search(r'<form method="get"[^>]*>(.*?)</form>', header(files_tab(client, sample)), re.S)[1]
    assert hidden in form
    form = re.search(r'<form method="get"[^>]*>(.*?)</form>', header(page(client, sample)), re.S)[1]
    assert 'name="tab"' not in form


def test_no_rounds(client, project):  # AC4
    task = add_task(project)
    html = page(client, task, "?tab=files")
    review = f"/tasks/{task}/review"
    assert [(link, label) for link, _, label in tabs(html)] == [
        ((review, {}, ""), "Conversation"), ((review, {"tab": "files"}, ""), "Files changed 0")]
    body = html.split("</nav>", 1)[1]
    assert text(body.split("</main>")[0]) == "No rounds yet."


def test_round_picks_diff(client, sample):  # AC5
    submit(client, sample, B_PY)
    ids = lambda html: re.findall(r'<section class="file" id="file:([^"]*)"', html)  # noqa: E731
    assert ids(page(client, sample, "?tab=files")) == ["b.py"]
    assert ids(files_tab(client, sample)) == FILES
    assert not_found_page(client.get(f"/tasks/{sample}/review?round=99&tab=files")) == f"#{sample} has no round 99"


# --- File tree -----------------------------------------------------------------------


def tree(html):
    nav = re.search(r'<nav id="file-tree"[^>]*>(.*?)</nav>', html, re.S)[1]
    return re.sub(r">\s+<", "><", nav)


def test_file_tree(client, sample):  # AC6
    nav = tree(files_tab(client, sample))
    assert nav.startswith("<ul>")
    entries = [text(e) for e in re.findall(r"<li>(.*?)(?:<ul>|</li>)", nav)]
    assert entries == ["app/", "auth.py +2 −1", "limits.py +2 −0", "logo.png +0 −0", "new_name +0 −0", "tests/",
                       "test_limits.py +0 −2"]
    app_dir = re.search(r"<li>app/<ul>(.*?)</ul></li>", nav)[1]
    assert "auth.py +2" in text(app_dir) and "limits.py +2" in text(app_dir) and "logo" not in app_dir
    tests_dir = re.search(r"<li>tests/<ul>(.*?)</ul></li>", nav)[1]
    assert text(tests_dir) == "test_limits.py +0 −2"
    assert "−" in nav and " -" not in text(nav)


def test_tree_links(client, sample):  # AC7
    html = files_tab(client, sample)
    assert re.findall(r'<a href="#([^"]*)">', tree(html)) == [f"file:{p}" for p in FILES]
    assert re.findall(r'id="(file:[^"]*)"', html) == [f"file:{p}" for p in FILES]


# --- File sections -------------------------------------------------------------------


def test_file_headers(client, sample):  # AC8
    found = re.findall(r'<h3 class="file-header">(.*?)</h3>', files_tab(client, sample), re.S)
    assert [text(h) for h in found] == [
        "app/auth.py +2 −1", "app/limits.py (new) +2 −0", "logo.png (new) +0 −0",
        "new_name (renamed from old_name) +0 −0", "tests/test_limits.py (deleted) +0 −2"]


def test_auth_rows(client, sample):  # AC9
    html = files_tab(client, sample)
    assert html.count('<table class="diff-table"') == 5
    for path in FILES:
        assert len(re.findall(r"<table ", table(html, path))) == 1
    hunk = re.search(r'<tr class="hunk">(.*?)</tr>', table(html, "app/auth.py"), re.S)[1]
    assert re.fullmatch(r'<td colspan="4">[^<]*</td>', hunk)
    assert rows(html, "app/auth.py") == [
        ("hunk", "@@ -41,3 +41,3 @@ def login():"),
        ("ctx", "41", "41", "·", "    user = authenticate(form)"),
        ("del", "42", "·", "-", "    if not user:"),
        ("add", "·", "42", "+", "    if not user and limiter.hit(client_key(request)):"),
        ("ctx", "43", "43", "·", "        return deny()"),
        ("hunk", "@@ -60,2 +60,3 @@ def logout():"),
        ("ctx", "60", "60", "·", "    session.clear()"),
        ("add", "·", "61", "+", '    audit("logout")'),
        ("ctx", "61", "62", "·", "    return ok()"),
    ]
    assert "diff --git" not in html and "index 1111111" not in html and "+++ b/" not in html


def test_no_newline_note(client, sample):  # AC10
    html = files_tab(client, sample)
    assert rows(html, "app/limits.py") == [
        ("hunk", "@@ -0,0 +1,2 @@"),
        ("add", "·", "1", "+", "def client_key(request):"),
        ("add", "·", "2", "+", "    return request.client.host"),
        ("note", "\\ No newline at end of file"),
    ]
    note = trs(table(html, "app/limits.py"))[-1][1]
    assert "<a" not in note and "id=" not in note


def test_binary_and_rename_notes(client, sample):  # AC11
    html = files_tab(client, sample)
    assert rows(html, "logo.png") == [("note", "Binary file not shown.")]
    assert rows(html, "new_name") == [("note", "No content changes.")]


def test_crlf(client, sample):  # AC12
    submit(client, sample, "diff --git a/win.txt b/win.txt\n--- a/win.txt\n+++ b/win.txt\n@@ -1 +1 @@\n-old\r\n+new\r\n")
    html = page(client, sample, "?round=2&tab=files")
    [add] = [tr for cls, tr in trs(table(html, "win.txt")) if cls == "add"]
    code = re.search(r'<td class="code">(.*?)</td>', add, re.S)[1]
    assert cell_text(code) == "new" and "\r" not in code


def test_escaped(client, project):  # AC13
    task = add_task(project)
    submit(client, task, "diff --git a/x.html b/x.html\nnew file mode 100644\n--- /dev/null\n+++ b/x.html\n"
                         "@@ -0,0 +1 @@\n+<script>alert(1)</script>\n")
    html = page(client, task, "?tab=files")
    code = re.search(r'<td class="code">(.*?)</td>', table(html, "x.html"), re.S)[1]
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in code
    assert "<script>alert" not in html
    submit(client, task, "diff --git a/<b>.txt b/<b>.txt\nnew file mode 100644\n--- /dev/null\n+++ b/<b>.txt\n"
                         "@@ -0,0 +1 @@\n+hi\n")
    html = page(client, task, "?tab=files")
    assert "<b>" not in html
    assert "&lt;b&gt;.txt +1 −0" in text(tree(html))
    assert re.search(r'<h3 class="file-header"><code>&lt;b&gt;.txt</code>', html)
    assert 'id="file:&lt;b&gt;.txt"' in html


# --- Anchors and the comment link ----------------------------------------------------


def test_line_anchors(client, sample):  # AC14
    found = trs(table(files_tab(client, sample), "app/auth.py"))
    ids = [(cls, re.findall(r'<a id="([^"]*)"', tr)) for cls, tr in found]
    assert ids[:5] == [
        ("hunk", []),
        ("ctx", ["app/auth.py:old:41", "app/auth.py:new:41"]),
        ("del", ["app/auth.py:old:42"]),
        ("add", ["app/auth.py:new:42"]),
        ("ctx", ["app/auth.py:old:43", "app/auth.py:new:43"]),
    ]
    assert ids[5] == ("hunk", [])
    note = trs(table(files_tab(client, sample), "app/limits.py"))[-1]
    assert note[0] == "note" and "id=" not in note[1]


def test_line_link(client, sample):  # AC15
    href = re.search(r'<a id="app/auth.py:old:42" href="([^"]*)"', files_tab(client, sample))[1]
    assert url(href) == (f"/tasks/{sample}/review",
                         {"round": "1", "tab": "files", "path": "app/auth.py", "side": "old", "line": "42"},
                         "app/auth.py:old:42")


# --- Highlighting --------------------------------------------------------------------


def inline_scripts(html):
    return re.findall(r"<script>(.*?)</script>", html, re.S)


def test_highlight(client, sample):  # AC16
    html = files_tab(client, sample)
    assert re.search(r'<table class="diff-table" ([^>]*)>', table(html, "app/auth.py"))[1] == 'data-lang="py"'
    assert table(html, "new_name").startswith('<table class="diff-table">')
    [script] = [s for s in inline_scripts(html) if "hljs" in s]
    assert "hljs.getLanguage" in script and "hljs.highlight(" in script
    assert "highlightAuto" not in script and "highlightAll" not in script
    assert not [s for s in inline_scripts(page(client, sample)) if "hljs" in s]


# --- Inline comment form -------------------------------------------------------------


FORM_Q = "?round=1&tab=files&path=app/auth.py&side=new&line=42"


def test_inline_form(client, sample):  # AC17
    html = files_tab(client, sample, FORM_Q)
    assert len(re.findall(rf'<form hx-post="/tasks/{sample}/comments"', html)) == 1
    cls, tr = after(html, "app/auth.py", "app/auth.py:new:42")
    assert cls == "comment-form"
    form = re.search(rf'<form hx-post="/tasks/{sample}/comments"[^>]*>(.*?)</form>', tr, re.S)[1]
    assert re.findall(r'<input type="hidden" name="(\w+)" value="([^"]*)">', form) == [
        ("round", "1"), ("path", "app/auth.py"), ("side", "new"), ("line", "42")]
    [textarea] = re.findall(r'<textarea [^>]*name="body_md"[^>]*>', form)
    assert " required" in textarea and " autofocus" in textarea
    assert re.findall(r"<button[^>]*>(.*?)</button>", form) == ["Comment"]
    [cancel] = re.findall(r'<a href="([^"]*)">Cancel</a>', form)
    assert url(cancel) == (f"/tasks/{sample}/review", {"round": "1", "tab": "files"}, "app/auth.py:new:42")
    add_inline(sample, round_id(sample, 1), "ux", "app/auth.py", 42, "new", "hm")  # the comments row comes first
    found = trs(table(files_tab(client, sample, FORM_Q), "app/auth.py"))
    i = next(i for i, (_, tr) in enumerate(found) if 'id="app/auth.py:new:42"' in tr)
    assert [cls for cls, _ in found[i + 1:i + 3]] == ["comments", "comment-form"]


@pytest.mark.parametrize("target", [
    "path=app/auth.py&side=new&line=99", "path=app/auth.py&side=new&line=x", "path=app/auth.py&side=new&line=042",
    "path=app/auth.py&side=both&line=42", "path=nope.py&side=new&line=42", "path=app/auth.py",
])
def test_no_form_for_bad_target(client, sample, target):  # AC18
    html = files_tab(client, sample, f"?round=1&tab=files&{target}").split("</header>", 1)[1]  # past 009's forms
    assert "hx-post" not in html and "<textarea" not in html


def test_inline_post(client, sample):  # AC19
    before, events = task_row(sample), sql("SELECT COUNT(*) FROM events")
    data = {"body_md": "Use a bucket", "round": "1", "path": "app/auth.py", "side": "new", "line": "42"}
    r = post(client, sample, data)
    assert r.status_code == 204
    assert url(r.headers["HX-Redirect"]) == (f"/tasks/{sample}/review", {"round": "1", "tab": "files"},
                                             "app/auth.py:new:42")
    assert sql("SELECT author, round_id, path, line, side, body_md FROM comments") == [
        ("me", round_id(sample, 1), "app/auth.py", 42, "new", "Use a bucket")]
    assert sql("SELECT COUNT(*) FROM events") == events
    assert task_row(sample) == before


def test_inline_post_viewed_round(client, sample):  # AC20
    submit(client, sample, B_PY)
    data = {"body_md": "x", "round": "1", "path": "app/auth.py", "side": "new", "line": "42"}
    assert post(client, sample, data).status_code == 204
    assert sql("SELECT round_id FROM comments") == [(round_id(sample, 1),)]


INLINE = {"body_md": "x", "round": "1", "path": "app/auth.py", "side": "new", "line": "42"}


@pytest.mark.parametrize("change, status", [
    ({"line": "abc"}, 422), ({"line": "0"}, 422), ({"side": "both"}, 422), ({"round": "x"}, 422),
    ({"line": ""}, 422), ({"path": ""}, 422), ({"path": "nope.py"}, 422), ({"body_md": "  "}, 422),
    ({"round": "9"}, 404),
])
def test_inline_post_refused(client, sample, change, status):  # AC21
    r = post(client, sample, INLINE | change)
    assert r.status_code == status, r.text
    assert sql("SELECT COUNT(*) FROM comments") == [(0,)]
    assert post(client, sample, INLINE, headers={}).status_code == 403
    assert sql("SELECT COUNT(*) FROM comments") == [(0,)]


def test_conversation_post_unchanged(client, sample):  # AC22
    submit(client, sample, B_PY)
    r = post(client, sample, {"body_md": "Looks good"})
    assert (r.status_code, r.headers["HX-Redirect"]) == (204, f"/tasks/{sample}/review")
    assert sql("SELECT round_id, path, line, side FROM comments") == [(round_id(sample, 2), None, None, None)]


# --- Comments in place ---------------------------------------------------------------


def test_comments_in_place(client, sample):  # AC23
    r1, r2 = round_id(sample, 1), submit(client, sample, B_PY)
    add_inline(sample, r1, "security", "app/auth.py", 42, "new", "Trusts **XFF**")
    add_inline(sample, r1, "me", "app/auth.py", 42, "new", "Agreed")
    add_inline(sample, r1, "ux", "app/auth.py", 42, "old", "Old line")
    add_inline(sample, r1, "code", "app/limits.py", 99, "new", "Off the diff")
    add_comment(sample, r1, "me", "General")
    add_inline(sample, r2, "me", "b.py", 1, "new", "Later")
    html = files_tab(client, sample)
    cls, tr = after(html, "app/auth.py", "app/auth.py:new:42")
    assert cls == "comments"
    assert re.findall(r"<strong>(\w+)</strong>", tr) == ["security", "XFF", "me"]
    assert text(tr) == "security Trusts XFF me Agreed"
    cls, tr = after(html, "app/auth.py", "app/auth.py:old:42")
    assert cls == "comments" and text(tr) == "ux Old line"
    cls, tr = trs(table(html, "app/limits.py"))[-1]
    assert cls == "comments" and text(tr) == "code on line 99 (new) Off the diff"
    assert "<strong>code</strong>" in tr
    assert "General" not in html and "Later" not in html


def test_comment_escaped(client, sample):  # AC24
    add_inline(sample, round_id(sample, 1), "security", "app/auth.py", 42, "new", "<img src=x onerror=alert(1)>")
    html = files_tab(client, sample)
    cls, tr = after(html, "app/auth.py", "app/auth.py:new:42")
    assert cls == "comments" and "&lt;img" in tr
    assert "<img" not in html


def test_posted_comment_shows(client, sample):  # AC25
    data = {"body_md": "Use a bucket", "round": "1", "path": "app/auth.py", "side": "new", "line": "42"}
    assert post(client, sample, data).status_code == 204
    cls, tr = after(files_tab(client, sample), "app/auth.py", "app/auth.py:new:42")
    assert cls == "comments" and "Use a bucket" in text(tr)


# --- Round 2 review fixes ------------------------------------------------------------


def test_form_errors(client, sample):  # ui review round 1: a failed post says why
    err = '<p class="form-error" role="alert"></p>'
    html = files_tab(client, sample, FORM_Q)
    [form] = re.findall(rf'<form hx-post="/tasks/{sample}/comments"[^>]*>(.*?)</form>', html, re.S)
    assert err in form
    html = page(client, sample)
    [form] = re.findall(rf'<form hx-post="/tasks/{sample}/comments"[^>]*>(.*?)</form>', html, re.S)
    assert err in form
    [script] = [s for s in inline_scripts(html) if "htmx:responseError" in s]
    assert '.querySelector(".form-error")' in script and "box.textContent =" in script and "innerHTML" not in script


def test_huge_hunk_number(client, sample):  # security review round 1: no 500 on a 5000-digit hunk header
    submit(client, sample, f"diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -{'9' * 5000} +1 @@\n-x\n+y\n")
    assert rows(page(client, sample, "?round=2&tab=files"), "a.py") == [("note", "No content changes.")]
