"""057: a project's context cards and groups (docs/data-model-and-api.md §6.1): list, create, patch, delete,
upload, read from a path, and reload. Every refusal raises inside the request's transaction, so it writes
nothing; the 64 KB total is measured after the write (Q4) for the same reason."""

from contextlib import contextmanager
from pathlib import Path

from .. import config
from ..domain.errors import Invalid, NotFound, TooLarge
from ..dto.context_items import ContextItemOut, ContextItemPatch, NewContextItem
from ..lib.context_file import MAX_DESCRIPTION, allowed, derive, one_line
from ..lib.markdown import render
from ..repositories.context_items import ContextItemsRepo
from ..repositories.projects import ProjectsRepo
from ..repositories.tasks import TasksRepo

EXTENSION = "only .md, .markdown, and .txt files"
SENDABLE = "title, description, content_md, parent_id, position"


def item_out(row) -> ContextItemOut:
    return ContextItemOut(**dict(row), content_html=render(row["content_md"]))


def title_of(title: str) -> str:
    title = one_line(title)
    if not title:
        raise Invalid("title must not be blank")
    return title


def description_of(description: str) -> str:
    description = one_line(description)
    if len(description) > MAX_DESCRIPTION:
        raise Invalid(f"description over {MAX_DESCRIPTION} characters")
    return description


def check_size(size: int, where: str = "") -> None:
    """MAX_CONTEXT, in UTF-8 bytes; exactly 16384 passes. Also the upload body's cap, as it streams in."""
    if size > config.MAX_CONTEXT:
        raise TooLarge(f"{where}card over 16 KB")


def check_group(kind: str, content_md: str) -> None:
    if kind == "group" and content_md:
        raise Invalid("a group has no content")


def check_parent(items: ContextItemsRepo, project_id: int, kind: str, parent_id: int | None) -> None:
    if parent_id is None:
        return
    if kind == "group":
        raise Invalid("groups are one level deep")
    if not items.is_group(project_id, parent_id):
        raise Invalid(f"parent_id {parent_id} is not a group of this project")


def check_total(items: ContextItemsRepo, project_id: int) -> None:
    if items.total_bytes(project_id) > config.MAX_CONTEXT_TOTAL:
        raise TooLarge("project context over 64 KB")


def locked_project(projects: ProjectsRepo, tasks: TasksRepo, project_id: int) -> None:
    """The write lock first, so the parent check, the positions, the inserts, and the total commit together."""
    tasks.lock()
    if not projects.exists(project_id):
        raise NotFound(f"Project #{project_id} not found")


def list_items(projects: ProjectsRepo, items: ContextItemsRepo, project_id: int) -> list[ContextItemOut]:
    if not projects.exists(project_id):
        raise NotFound(f"Project #{project_id} not found")
    return [item_out(row) for row in items.for_project(project_id)]


def create(projects: ProjectsRepo, items: ContextItemsRepo, tasks: TasksRepo, project_id: int,
           body: NewContextItem) -> ContextItemOut:
    title, description = title_of(body.title), description_of(body.description)
    check_group(body.kind, body.content_md)
    check_size(len(body.content_md.encode()))
    locked_project(projects, tasks, project_id)
    check_parent(items, project_id, body.kind, body.parent_id)
    item_id = items.add(project_id, body.parent_id, body.kind, title, description, body.content_md, None)
    check_total(items, project_id)
    return item_out(items.get(item_id))


def upload(projects: ProjectsRepo, items: ContextItemsRepo, tasks: TasksRepo, project_id: int, name: str,
           parent_id: int | None, body: bytes) -> ContextItemOut:
    """Q1: one file per request; the name drives the extension check and the title fallback, never a path. The
    body's 16 KB cap is checked as it comes in. Details carry no file name: the SPA prefixes it."""
    if not allowed(name):
        raise Invalid(EXTENSION)
    try:
        text = body.decode()
    except UnicodeDecodeError:
        raise Invalid("not UTF-8") from None
    title, description = derive(text, name)
    locked_project(projects, tasks, project_id)
    check_parent(items, project_id, "item", parent_id)
    item_id = items.add(project_id, parent_id, "item", title, description, text, None)
    check_total(items, project_id)
    return item_out(items.get(item_id))


@contextmanager
def os_errors(path: Path):
    """Q7: any OS error reading a path is a 422 naming the file."""
    try:
        yield
    except OSError as e:
        raise Invalid(f"{e.filename or path}: {e.strerror or e}") from None


def read_text(path: Path) -> str:
    """A file's text, reading at most one byte past the cap. Inside os_errors."""
    with open(path, "rb") as f:
        data = f.read(config.MAX_CONTEXT + 1)
    check_size(len(data), f"{path}: ")
    try:
        return data.decode()
    except UnicodeDecodeError:
        raise Invalid(f"{path}: not UTF-8") from None


def read_path(path: Path) -> tuple[bool, list[Path]]:
    """(whether it is a folder, the files a path read takes, Q6): the file itself, or a folder's matching regular
    files directly in it, symlinks followed, by name. Inside os_errors."""
    if path.is_dir():
        files = sorted((f for f in path.iterdir() if allowed(f.name) and f.is_file()), key=lambda f: f.name)
        if not files:
            raise Invalid(f"{path}: no .md, .markdown, or .txt files")
        if len(files) > config.MAX_CONTEXT_FILES:
            raise TooLarge(f"{path}: {len(files)} files; the limit is {config.MAX_CONTEXT_FILES}")
        return True, files
    # ponytail: a FIFO, socket, or device counts as missing, so open() never blocks on one
    if not path.is_file():
        raise NotFound(f"no file or folder at {path}")
    if not allowed(path.name):
        raise Invalid(f"{path}: {EXTENSION}")
    return False, [path]


def from_path(projects: ProjectsRepo, items: ContextItemsRepo, tasks: TasksRepo, project_id: int, path: str,
              parent_id: int | None) -> list[ContextItemOut]:
    """Q13: the created rows, a folder's group first. The disk is read before the write lock; nothing is
    written to it (MVP §4.5)."""
    path.encode()  # a lone surrogate is server/app.py's 422 here, before a detail could echo it
    root = Path(path)
    if not root.is_absolute():
        raise Invalid("path must be absolute")
    with os_errors(root):
        folder, paths = read_path(root)
        files = [(f, read_text(f)) for f in paths]
    locked_project(projects, tasks, project_id)
    check_parent(items, project_id, "group" if folder else "item", parent_id)
    ids = []
    if folder:  # Q5: titled with the folder's name, or "/" for the root, which has none
        parent_id = items.add(project_id, None, "group", root.name or str(root), "", "", str(root))
        ids.append(parent_id)
    for f, text in files:
        ids.append(items.add(project_id, parent_id, "item", *derive(text, f.name), text, str(f)))
    check_total(items, project_id)
    return [item_out(items.get(i)) for i in ids]


def found(items: ContextItemsRepo, item_id: int):
    row = items.get(item_id)
    if row is None:
        raise NotFound(f"Context item #{item_id} not found")
    return row


def patch(items: ContextItemsRepo, tasks: TasksRepo, item_id: int, body: ContextItemPatch) -> ContextItemOut:
    """A parent_id that changes the parent, sent without position, puts the card last in the new list. Only a
    PATCH with content_md checks the 64 KB total (Q4), so moves and renames are never refused for size."""
    fields = {key: getattr(body, key) for key in body.model_fields_set}
    if not fields:
        raise Invalid(f"send at least one of: {SENDABLE}")
    if "title" in fields:
        fields["title"] = title_of(fields["title"])
    if "description" in fields:
        fields["description"] = description_of(fields["description"])
    if "content_md" in fields:
        check_size(len(fields["content_md"].encode()))
    tasks.lock()
    row = found(items, item_id)
    check_group(row["kind"], fields.get("content_md", ""))
    if "parent_id" in fields:
        check_parent(items, row["project_id"], row["kind"], fields["parent_id"])
        if fields["parent_id"] != row["parent_id"] and "position" not in fields:
            fields["position"] = items.next_position(row["project_id"], fields["parent_id"])
    items.update(item_id, fields)
    if "content_md" in fields:
        check_total(items, row["project_id"])
    return item_out(items.get(item_id))


def delete(items: ContextItemsRepo, item_id: int) -> None:
    if not items.delete(item_id):
        raise NotFound(f"Context item #{item_id} not found")


def reload(items: ContextItemsRepo, tasks: TasksRepo, item_id: int) -> ContextItemOut:
    """Q2: content_md read again from source_path; the title and description stay, since both may be edited."""
    tasks.lock()
    row = found(items, item_id)
    if row["kind"] == "group" or row["source_path"] is None:
        raise Invalid("only a card read from a path can be reloaded")
    path = Path(row["source_path"])
    with os_errors(path):
        if not path.is_file():
            raise NotFound(f"no file at {path}")
        text = read_text(path)
    items.update(item_id, {"content_md": text})
    check_total(items, row["project_id"])
    return item_out(items.get(item_id))
