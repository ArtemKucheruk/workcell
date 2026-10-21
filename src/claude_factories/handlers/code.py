"""The code page (docs/ui.md §8 item 6, docs/MVP.md §4.5): the main checkout's tracked files, or a listed
branch's (054), and one shown."""

import os
import re
from pathlib import Path

from ..adapters.git import Git
from ..config import MAX_VIEW
from ..domain.errors import NotFound
from ..lib.diff import file_tree
from ..repositories.projects import ProjectsRepo


def read_tracked(root: str, path: str) -> dict:
    """Q3–Q5, Q9: a tracked file's text and line count, or the note shown instead. Nothing outside the
    root and nothing but a regular file is ever opened."""
    real = os.path.realpath(os.path.join(root, path))
    if not Path(real).is_relative_to(os.path.realpath(root)):
        return {"note": "Not shown: points outside the project."}
    if not os.path.isfile(real):  # a directory, a submodule, a FIFO, gone from disk
        return {"note": "Not shown: not a regular file."}
    try:
        if os.stat(real).st_size > MAX_VIEW:
            return {"note": "File over 1 MB not shown."}
        with open(real, "rb") as f:
            data = f.read(MAX_VIEW)
    except OSError as e:
        return {"note": f"Not shown: {e.strerror or e}."}
    return view_of(data)


def read_blob(git: Git, root: str, ref: str, path: str) -> dict:
    """054 Q5, Q6: a listed path's blob on the full refname `ref`, by read_tracked's rules. Nothing on disk is
    read; a symlink's blob is its target path."""
    oid, error = git.object_id(root, ref, path)
    if error is None:
        oid = oid.decode().strip()
        size, error = git.object_size(root, oid)
    if error is None:
        if int(size) > MAX_VIEW:
            return {"note": "File over 1 MB not shown."}
        data, error = git.blob(root, oid)
    if error:  # a gitlink's commit (in this repo or not), a timeout
        return {"note": "Not shown: not a regular file."}
    return view_of(data)


def view_of(data: bytes) -> dict:
    """A file's bytes as text and a line count, or the note shown instead."""
    if b"\0" in data[:8000]:  # git's binary heuristic
        return {"note": "Binary file not shown."}
    if not data:
        return {"note": "Empty file."}
    text = data.decode(errors="replace")
    # Q9: lines end at \n, \r\n, or a lone \r, as HTML breaks them; a final line ending adds none
    return {"text": text, "lines": len(re.findall(r"\r\n?|\n", text)) + (text[-1] not in "\r\n")}


def branch_names(refs: bytes) -> dict[str, str]:
    """054 Q4: {name: full refname}, locals then origin's in refname order. origin/HEAD and an origin branch with
    a local twin are left out, and no name is listed twice."""
    names: dict[str, str] = {}
    for ref in refs.decode(errors="replace").splitlines():
        local, origin = ref.removeprefix("refs/heads/"), ref.removeprefix("refs/remotes/origin/")
        if local != ref:
            names[local] = ref
        elif origin not in names and origin != "HEAD":
            names.setdefault(f"origin/{origin}", ref)
    return names


def code(projects: ProjectsRepo, git: Git, project_id: int, path: str, branch: str = "") -> dict:
    """§8 item 6: the main checkout's `git ls-files` tree, or a listed branch's `git ls-tree` (054), beside
    README.md (no `path`) or one file."""
    project = projects.for_code(project_id)
    if project is None:
        raise NotFound(f"Project #{project_id} not found")
    root, context = project["path"], {"project": project, "path": path}
    refs, error = git.branch_refs(root)
    if error:  # Q10
        return context | {"error": error}
    branches = branch_names(refs)
    out, _ = git.current_branch(root)
    checked_out = None if out is None else out.decode(errors="replace").strip()  # "" on a detached HEAD
    browsed = branch if branch and branch != checked_out else ""  # 054 Q2: the checkout is the working tree
    if browsed and browsed not in branches:  # 054 Q1: before git sees it
        raise NotFound(f"{branch} is not a branch in {project['name']}")
    ref = branches.get(browsed)
    listed, error = git.ls_tree(root, ref) if ref else git.ls_files(root)
    if error:
        return context | {"error": error}
    raw = listed.split(b"\0")[:-1]
    names = [n.decode(errors="replace") for n in raw]
    tracked = {n for n, b in zip(names, raw) if n.encode() == b}  # Q4: a name that didn't decode is listed, not viewable
    if path and path not in tracked:  # Q2: before any filesystem or blob read
        raise NotFound(f"{path} is not a tracked file in {project['name']}")
    shown = path or ("README.md" if "README.md" in tracked else "")  # Q6
    if not shown:
        view = {"note": "No README.md in this project."}
    else:
        view = read_blob(git, root, ref, shown) if ref else read_tracked(root, shown)
    name = path.rpartition("/")[2]
    return context | {
        "tree": file_tree([{"path": n} for n in names]), "shown": shown, "view": view,
        "branch": None if checked_out is None else checked_out or "detached HEAD", "branches": list(branches),  # Q7
        "lang": name.rpartition(".")[2].lower() if "." in name else None,  # Q9, same rule as review_files
    }
