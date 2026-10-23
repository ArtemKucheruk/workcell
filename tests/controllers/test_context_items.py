"""057: a project's context cards and groups (docs/data-model-and-api.md §6.1)."""

import os
import re

import pytest
from conftest import sql

from claude_factories.lib.markdown import render

from .test_projects import H, connect

TIMESTAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")
OLD = "2000-01-01T00:00:00Z"
KEYS = {"id", "parent_id", "kind", "title", "description", "content_md", "content_html", "source_path", "position",
        "created_at", "updated_at"}
NOT_UTF8 = b"# Title\n\n\xff\xfe\n"


@pytest.fixture
def project(client):
    return connect(client)["id"]


@pytest.fixture
def other(client):
    return connect(client, path="/code/web", name="web")["id"]


def items_url(project_id, tail=""):
    return f"/api/projects/{project_id}/context/items{tail}"


def post(client, project_id, body, headers=H):
    return client.post(items_url(project_id), json=body, headers=headers)


def created(client, project_id, **body) -> dict:
    r = post(client, project_id, {"title": "t"} | body)
    assert r.status_code == 201, r.text
    return r.json()


def group(client, project_id, title="Runbooks") -> dict:
    return created(client, project_id, kind="group", title=title)


def listed(client, project_id) -> list[dict]:
    r = client.get(items_url(project_id))
    assert r.status_code == 200, r.text
    return r.json()


def patch(client, item_id, body):
    return client.patch(f"/api/context/items/{item_id}", json=body, headers=H)


def patched(client, item_id, body) -> dict:
    r = patch(client, item_id, body)
    assert r.status_code == 200, r.text
    return r.json()


def upload(client, project_id, name, body: bytes, parent_id=None):
    params = {"name": name} | ({} if parent_id is None else {"parent_id": parent_id})
    return client.post(items_url(project_id, "/upload"), params=params, content=body, headers=H)


def from_path(client, project_id, path, parent_id=None):
    body = {"path": str(path)} | ({} if parent_id is None else {"parent_id": parent_id})
    return client.post(items_url(project_id, "/from-path"), json=body, headers=H)


def reload(client, item_id):
    return client.post(f"/api/context/items/{item_id}/reload", headers=H)


def snapshot():
    """Everything a refusal must leave as it was."""
    return sql("SELECT * FROM context_items ORDER BY id"), sql("SELECT id, context_md FROM projects ORDER BY id")


def refused(r, status, detail):
    assert (r.status_code, r.json()["detail"]) == (status, detail), r.text


def list_detail(r):
    assert r.status_code == 422, r.text
    assert isinstance(r.json()["detail"], list)


def set_context(client, project_id, text):
    r = client.put(f"/api/projects/{project_id}/context", json={"context_md": text}, headers=H)
    assert r.status_code == 200, r.text


# --- GET and POST /api/projects/{id}/context/items ----------------------------------------


def test_list_empty_and_unknown_project(client, project):  # BE2
    assert listed(client, project) == []
    refused(client.get(items_url(99)), 404, "Project #99 not found")


def test_create_card(client, project):  # BE3
    r = post(client, project, {"title": "  API   rules ", "content_md": "# A\n"})
    assert r.status_code == 201, r.text
    first = r.json()
    assert set(first) == KEYS
    assert first | {"id": 0, "created_at": "", "updated_at": ""} == {
        "id": 0, "parent_id": None, "kind": "item", "title": "API rules", "description": "", "content_md": "# A\n",
        "content_html": render("# A\n"), "source_path": None, "position": 1, "created_at": "", "updated_at": ""}
    assert TIMESTAMP.fullmatch(first["created_at"]) and first["created_at"] == first["updated_at"]
    second = created(client, project, title="Second")
    assert second["position"] == 2
    assert listed(client, project) == [first, second]


def test_create_group_and_its_card(client, project):  # BE4
    created(client, project, title="Top")
    g = group(client, project)
    assert (g["kind"], g["content_md"], g["content_html"], g["position"]) == ("group", "", "", 2)
    card = created(client, project, title="Deploy", parent_id=g["id"])
    assert (card["parent_id"], card["position"]) == (g["id"], 1)
    assert created(client, project, title="Roll back", parent_id=g["id"])["position"] == 2
    assert created(client, project, title="Top 2")["position"] == 3


def test_description_cap(client, project):  # BE5: 160 passes, counted after the whitespace runs collapse
    assert created(client, project, description="x" * 160)["description"] == "x" * 160
    spaced = created(client, project, description=" " + "x" * 80 + "  \n  " + "x" * 79 + " ")["description"]
    assert spaced == "x" * 80 + " " + "x" * 79


def test_create_refusals(client, project, other):  # BE5
    item = created(client, project, title="Item")
    others = group(client, other)
    cases = [
        ({"title": " \n\t "}, 422, "title must not be blank"),
        ({"title": "t", "description": "x" * 161}, 422, "description over 160 characters"),
        ({"kind": "group", "title": "g", "content_md": "# no"}, 422, "a group has no content"),
        ({"kind": "group", "title": "g", "parent_id": item["id"]}, 422, "groups are one level deep"),
        ({"title": "t", "parent_id": 999}, 422, "parent_id 999 is not a group of this project"),
        ({"title": "t", "parent_id": item["id"]}, 422, f"parent_id {item['id']} is not a group of this project"),
        ({"title": "t", "parent_id": others["id"]}, 422, f"parent_id {others['id']} is not a group of this project"),
    ]
    before = snapshot()
    for body, status, detail in cases:
        refused(post(client, project, body), status, detail)
    refused(post(client, 99, {"title": "t"}), 404, "Project #99 not found")
    for body in ({"kind": "folder", "title": "t"}, {"title": None}, {}, {"title": "t", "description": None},
                 {"title": "t", "content_md": 5}, {"title": "t", "parent_id": 2**63}):
        list_detail(post(client, project, body))
    assert snapshot() == before


def test_card_size_cap(client, project):  # BE6: UTF-8 bytes, so é counts twice
    exact, over = "é" * 8192, "é" * 8192 + "a"
    card = created(client, project, content_md=exact)
    before = snapshot()
    refused(post(client, project, {"title": "t", "content_md": over}), 413, "card over 16 KB")
    refused(patch(client, card["id"], {"content_md": over}), 413, "card over 16 KB")
    assert snapshot() == before
    assert patched(client, card["id"], {"content_md": "é" + exact[1:]})["content_md"] == exact


def test_project_total_cap(client, project):  # BE7
    set_context(client, project, "c" * 16384)
    cards = [created(client, project, content_md="x" * size) for size in (16384, 16384, 16383)]
    created(client, project, content_md="y")  # exactly 65536
    g = group(client, project)
    before = snapshot()
    refused(post(client, project, {"title": "t", "content_md": "y"}), 413, "project context over 64 KB")
    refused(patch(client, cards[2]["id"], {"content_md": "x" * 16384}), 413, "project context over 64 KB")
    assert snapshot() == before
    sql("UPDATE projects SET context_md = context_md || 'over' WHERE id = ?", (project,))  # already over the cap
    for body in ({"title": "Renamed"}, {"parent_id": g["id"]}, {"position": 0.5}, {"description": "d"}):
        patched(client, cards[1]["id"], body)
    assert patched(client, cards[0]["id"], {"content_md": "small"})["content_md"] == "small"  # under it again


# --- PATCH and DELETE /api/context/items/{id} ------------------------------------------------


def test_patch_text(client, project):  # BE8
    card = created(client, project, title="Old", content_md="# Old\n")
    sql("UPDATE context_items SET created_at = ?, updated_at = ? WHERE id = ?", (OLD, OLD, card["id"]))
    out = patched(client, card["id"], {"title": " New \n title ", "description": "One\n\ntwo ", "content_md": "*b*\n"})
    assert (out["title"], out["description"], out["content_md"]) == ("New title", "One two", "*b*\n")
    assert out["content_html"] == render("*b*\n")
    assert out["created_at"] == OLD and out["updated_at"] > OLD and TIMESTAMP.fullmatch(out["updated_at"])
    assert listed(client, project) == [out]


def test_patch_moves(client, project):  # BE9
    a, b = created(client, project, title="A"), created(client, project, title="B")
    g = group(client, project)
    created(client, project, title="In", parent_id=g["id"])
    moved = patched(client, a["id"], {"parent_id": g["id"]})
    assert (moved["parent_id"], moved["position"]) == (g["id"], 2)
    assert patched(client, a["id"], {"parent_id": g["id"]})["position"] == 2  # the same parent: left alone
    sql("UPDATE context_items SET position = 7.5 WHERE id = ?", (a["id"],))
    assert patched(client, a["id"], {"parent_id": g["id"], "title": "A"})["position"] == 7.5
    out = patched(client, a["id"], {"parent_id": None})
    assert (out["parent_id"], out["position"]) == (None, 4)  # after B (2) and the group (3)
    assert patched(client, b["id"], {"parent_id": g["id"], "position": 0.25})["position"] == 0.25
    top = [i["title"] for i in listed(client, project) if i["parent_id"] is None]
    assert top == ["Runbooks", "A"]
    assert patched(client, a["id"], {"position": 1.5})["position"] == 1.5
    sql("UPDATE context_items SET position = 1.5 WHERE id = ?", (g["id"],))  # a tie: by id
    assert [i["title"] for i in listed(client, project)] == ["B", "In", "A", "Runbooks"]


def test_patch_refusals(client, project):  # BE10
    card, g = created(client, project, title="Card"), group(client, project)
    other_group = group(client, project, "Other")
    before = snapshot()
    send = "send at least one of: title, description, content_md, parent_id, position"
    refused(patch(client, card["id"], {}), 422, send)
    refused(patch(client, card["id"], {"color": "red"}), 422, send)
    for body in ({"title": None}, {"description": None}, {"content_md": None}, {"position": None},
                 {"title": 5}, {"description": []}, {"content_md": {}}, {"position": "x"}, {"parent_id": "x"}):
        list_detail(patch(client, card["id"], body))
    for value in ("NaN", "Infinity", "-Infinity"):
        r = client.patch(f"/api/context/items/{card['id']}", content=f'{{"position": {value}}}',
                         headers=H | {"Content-Type": "application/json"})
        list_detail(r)
    refused(patch(client, card["id"], {"title": "  "}), 422, "title must not be blank")
    refused(patch(client, card["id"], {"description": "x" * 161}), 422, "description over 160 characters")
    refused(patch(client, g["id"], {"parent_id": other_group["id"]}), 422, "groups are one level deep")
    refused(patch(client, g["id"], {"content_md": "# no"}), 422, "a group has no content")
    refused(patch(client, card["id"], {"parent_id": card["id"]}), 422,
            f"parent_id {card['id']} is not a group of this project")
    refused(patch(client, card["id"], {"parent_id": 999}), 422, "parent_id 999 is not a group of this project")
    refused(patch(client, 99, {"title": "t"}), 404, "Context item #99 not found")
    assert snapshot() == before


def test_delete(client, project):  # BE11
    keep, card, g = created(client, project, title="Keep"), created(client, project), group(client, project)
    created(client, project, parent_id=g["id"])
    r = client.delete(f"/api/context/items/{card['id']}", headers=H)
    assert (r.status_code, r.content) == (204, b"")
    assert client.delete(f"/api/context/items/{g['id']}", headers=H).status_code == 204
    assert listed(client, project) == [keep]
    refused(client.delete("/api/context/items/99", headers=H), 404, "Context item #99 not found")


def test_delete_project_removes_items(client, project, other):  # BE11
    g = group(client, project)
    created(client, project, parent_id=g["id"])
    kept = created(client, other)
    assert client.delete(f"/api/projects/{project}", headers=H).status_code == 204
    assert sql("SELECT id FROM context_items") == [(kept["id"],)]


def test_mutations_need_header(client, project):  # §4.5
    card = created(client, project)
    for r in (post(client, project, {"title": "t"}, headers={}),
              client.patch(f"/api/context/items/{card['id']}", json={"title": "x"}),
              client.delete(f"/api/context/items/{card['id']}"),
              client.post(f"/api/context/items/{card['id']}/reload"),
              client.post(items_url(project, "/upload?name=a.md"), content=b"x"),
              client.post(items_url(project, "/from-path"), json={"path": "/tmp"})):
        assert r.status_code == 403
    assert listed(client, project) == [card]


# --- POST …/upload ---------------------------------------------------------------------------------


def test_upload(client, project):  # BE12
    body = "# API rules\n\nUse JSON\neverywhere.\n"
    r = upload(client, project, "api.md", body.encode())
    assert r.status_code == 201, r.text
    card = r.json()
    assert (card["kind"], card["title"], card["description"], card["content_md"], card["source_path"]) == (
        "item", "API rules", "Use JSON everywhere.", body, None)
    assert card["content_html"] == render(body)
    g = group(client, project)
    created(client, project, parent_id=g["id"])
    r = upload(client, project, "b.txt", b"plain", parent_id=g["id"])
    assert r.status_code == 201, r.text
    assert (r.json()["parent_id"], r.json()["position"]) == (g["id"], 2)


def test_upload_derives_title(client, project):  # BE13, once through upload
    text = "```\n# not a title\n```\n\n## Section\n\nFirst   para\ngoes on.\n"
    card = upload(client, project, "notes.txt", text.encode()).json()
    assert (card["title"], card["description"]) == ("notes.txt", "First para goes on.")
    assert upload(client, project, "A.MD", b"").json()["title"] == "A.MD"  # BE14: any case passes


def test_upload_refusals(client, project, other):  # BE14
    item, others = created(client, project), group(client, other)
    before = snapshot()
    for name in ("a.pdf", "README", "md"):
        refused(upload(client, project, name, b"# x\n"), 422, "only .md, .markdown, and .txt files")
    refused(upload(client, project, "a.md", NOT_UTF8), 422, "not UTF-8")
    refused(upload(client, project, "a.md", b"x" * 16385), 413, "card over 16 KB")
    chunks = (b"x" * 4096 for _ in range(5))  # no Content-Length: refused once the stream passes 16384
    r = client.post(items_url(project, "/upload"), params={"name": "a.md"}, content=chunks, headers=H)
    refused(r, 413, "card over 16 KB")
    refused(upload(client, project, "a.md", b"x", parent_id=item["id"]), 422,
            f"parent_id {item['id']} is not a group of this project")
    refused(upload(client, project, "a.md", b"x", parent_id=others["id"]), 422,
            f"parent_id {others['id']} is not a group of this project")
    refused(upload(client, 99, "a.md", b"x"), 404, "Project #99 not found")
    list_detail(client.post(items_url(project, "/upload"), content=b"x", headers=H))  # name missing
    assert snapshot() == before
    set_context(client, project, "c" * 16384)
    for _ in range(3):
        assert upload(client, project, "big.md", b"x" * 16384).status_code == 201
    before = snapshot()
    refused(upload(client, project, "a.md", b"x"), 413, "project context over 64 KB")
    assert snapshot() == before
    assert upload(client, project, "exact.md", b"").status_code == 201  # 0 bytes keeps it at 65536


def test_upload_exactly_16_kb(client, project):  # BE14
    assert upload(client, project, "a.md", b"x" * 16384).status_code == 201


# --- POST …/from-path ------------------------------------------------------------------------------


def test_from_path_file(client, project, tmp_path):  # BE15
    text = "Intro line\nwraps.\n\n# Deploy\n\nSteps.\n"
    f = tmp_path / "deploy.md"
    f.write_text(text)
    r = from_path(client, project, f)
    assert r.status_code == 201, r.text
    [card] = r.json()
    assert (card["kind"], card["title"], card["description"], card["content_md"], card["source_path"]) == (
        "item", "Deploy", "Intro line wraps.", text, str(f))
    g = group(client, project)
    [inside] = from_path(client, project, f, parent_id=g["id"]).json()
    assert (inside["parent_id"], inside["position"]) == (g["id"], 1)


def test_from_path_folder(client, project, tmp_path):  # BE16
    folder = tmp_path / "notes"
    (folder / "sub").mkdir(parents=True)
    for name, text in {"b.markdown": "# B\n", "a.md": "# A\n\nAbout a.\n", "c.txt": "plain c\n", "d.pdf": "%PDF",
                       "sub/e.md": "# E\n"}.items():
        (folder / name).write_text(text)
    created(client, project, title="First")
    r = from_path(client, project, f"{folder}/")
    assert r.status_code == 201, r.text
    g, a, b, c = r.json()
    assert (g["kind"], g["title"], g["description"], g["content_md"], g["source_path"], g["parent_id"],
            g["position"]) == ("group", "notes", "", "", str(folder), None, 2)
    assert [(x["title"], x["description"], x["parent_id"], x["position"], x["source_path"]) for x in (a, b, c)] == [
        ("A", "About a.", g["id"], 1, str(folder / "a.md")), ("B", "", g["id"], 2, str(folder / "b.markdown")),
        ("c.txt", "plain c", g["id"], 3, str(folder / "c.txt"))]
    assert sorted(listed(client, project), key=lambda i: i["id"])[1:] == [g, a, b, c]


def test_from_path_refusals(client, project, other, tmp_path):  # BE17
    pdf, bad, big = tmp_path / "a.pdf", tmp_path / "bad.md", tmp_path / "big.md"
    pdf.write_text("%PDF")
    bad.write_bytes(NOT_UTF8)
    big.write_text("x" * 16385)
    folders = {}
    for name, files in {"bad": {"a.md": "ok", "z.md": NOT_UTF8}, "big": {"a.md": "ok", "z.txt": "x" * 16385},
                        "none": {"a.pdf": "x"}, "many": {f"{i:02}.md": "x" for i in range(51)},
                        "good": {"a.md": "ok"}}.items():
        folders[name] = tmp_path / name
        folders[name].mkdir()
        (folders[name] / "sub.md").mkdir()  # a folder with a matching name doesn't count
        for file, text in files.items():
            (folders[name] / file).write_bytes(text if isinstance(text, bytes) else text.encode())
    item = created(client, project)
    cases = [
        ("notes", None, 422, "path must be absolute"),
        (tmp_path / "nope", None, 404, f"no file or folder at {tmp_path / 'nope'}"),
        (pdf, None, 422, f"{pdf}: only .md, .markdown, and .txt files"),
        (bad, None, 422, f"{bad}: not UTF-8"),
        (folders["bad"], None, 422, f"{folders['bad'] / 'z.md'}: not UTF-8"),
        (big, None, 413, f"{big}: card over 16 KB"),
        (folders["big"], None, 413, f"{folders['big'] / 'z.txt'}: card over 16 KB"),
        (folders["none"], None, 422, f"{folders['none']}: no .md, .markdown, or .txt files"),
        (folders["many"], None, 413, f"{folders['many']}: 51 files; the limit is 50"),
    ]
    g = group(client, project)
    others = group(client, other)
    before = snapshot()
    for path, parent, status, detail in cases:
        refused(from_path(client, project, path, parent), status, detail)
    ok = tmp_path / "ok.md"
    ok.write_text("ok")
    refused(from_path(client, project, folders["good"], g["id"]), 422, "groups are one level deep")
    for parent in (item["id"], others["id"], 999):
        refused(from_path(client, project, ok, parent), 422, f"parent_id {parent} is not a group of this project")
    refused(from_path(client, 99, ok), 404, "Project #99 not found")
    list_detail(client.post(items_url(project, "/from-path"), json={}, headers=H))
    r = client.post(items_url(project, "/from-path"), content='{"path": "/a\\ud800.md"}',
                    headers=H | {"Content-Type": "application/json"})
    refused(r, 422, "text must not contain lone surrogates")
    assert snapshot() == before
    (folders["many"] / "50.md").unlink()
    assert len(from_path(client, project, folders["many"]).json()) == 51  # the group and 50 cards


def test_from_path_total_cap(client, project, tmp_path):  # BE17
    set_context(client, project, "c" * 16384)
    created(client, project, content_md="x" * 16384)
    folder = tmp_path / "f"
    folder.mkdir()
    for name in ("a.md", "b.md", "c.md"):
        (folder / name).write_text("x" * 16384)
    before = snapshot()
    refused(from_path(client, project, folder), 413, "project context over 64 KB")
    assert snapshot() == before
    (folder / "c.md").unlink()
    assert from_path(client, project, folder).status_code == 201  # exactly 65536


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads any file")
def test_from_path_os_error(client, project, tmp_path):  # Q7
    f = tmp_path / "locked.md"
    f.write_text("x")
    f.chmod(0)
    refused(from_path(client, project, f), 422, f"{f}: Permission denied")


# --- POST /api/context/items/{id}/reload --------------------------------------------------------------


def test_reload(client, project, tmp_path):  # BE18
    f = tmp_path / "a.md"
    f.write_text("# A\n\nAbout a.\n")
    [card] = from_path(client, project, f).json()
    sql("UPDATE context_items SET updated_at = ? WHERE id = ?", (OLD, card["id"]))
    f.write_text("# Another title\n\nAnother description.\n\n- new\n")
    r = reload(client, card["id"])
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["content_md"] == f.read_text() and out["content_html"] == render(f.read_text())
    assert (out["title"], out["description"], out["created_at"]) == ("A", "About a.", card["created_at"])
    assert out["updated_at"] > OLD


def test_reload_refusals(client, project, tmp_path):  # BE19
    f = tmp_path / "a.md"
    f.write_text("small")
    [card] = from_path(client, project, f).json()
    folder = tmp_path / "f"
    folder.mkdir()
    (folder / "x.md").write_text("x")
    folder_group = from_path(client, project, folder).json()[0]
    typed, g = created(client, project), group(client, project)
    before = snapshot()
    for item in (typed, g, folder_group):
        refused(reload(client, item["id"]), 422, "only a card read from a path can be reloaded")
    f.write_bytes(NOT_UTF8)
    refused(reload(client, card["id"]), 422, f"{f}: not UTF-8")
    f.write_text("x" * 16385)
    refused(reload(client, card["id"]), 413, f"{f}: card over 16 KB")
    assert snapshot() == before
    set_context(client, project, "c" * 16384)
    for size in (16384, 16384, 1):  # with "small" and x.md's "x": 49159 bytes
        created(client, project, content_md="x" * size)
    before = snapshot()
    f.write_text("x" * 16384)
    refused(reload(client, card["id"]), 413, "project context over 64 KB")
    f.unlink()
    refused(reload(client, card["id"]), 404, f"no file at {f}")
    refused(reload(client, 99), 404, "Context item #99 not found")
    assert snapshot() == before
