"""The code page (docs/ui.md §8 item 6, docs/MVP.md §4.5): the main checkout's tracked files, and one shown."""

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
    if b"\0" in data[:8000]:  # git's binary heuristic
        return {"note": "Binary file not shown."}
    if not data:
        return {"note": "Empty file."}
    text = data.decode(errors="replace")
    # Q9: lines end at \n, \r\n, or a lone \r, as HTML breaks them; a final line ending adds none
    return {"text": text, "lines": len(re.findall(r"\r\n?|\n", text)) + (text[-1] not in "\r\n")}


def code(projects: ProjectsRepo, git: Git, project_id: int, path: str) -> dict:
    """§8 item 6: the main checkout's `git ls-files` tree beside README.md (no `path`) or one file."""
    project = projects.for_code(project_id)
    if project is None:
        raise NotFound(f"Project #{project_id} not found")
    root, context = project["path"], {"project": project, "path": path}
    listed, error = git.ls_files(root)
    if error:  # Q10
        return context | {"error": error}
    raw = listed.split(b"\0")[:-1]
    names = [n.decode(errors="replace") for n in raw]
    tracked = {n for n, b in zip(names, raw) if n.encode() == b}  # Q4: a name that didn't decode is listed, not viewable
    if path and path not in tracked:  # Q2: before any filesystem call
        raise NotFound(f"{path} is not a tracked file in {project['name']}")
    shown = path or ("README.md" if "README.md" in tracked else "")  # Q6
    out, _ = git.current_branch(root)
    name = path.rpartition("/")[2]
    return context | {
        "tree": file_tree([{"path": n} for n in names]), "shown": shown,
        "view": read_tracked(root, shown) if shown else {"note": "No README.md in this project."},
        "branch": None if out is None else out.decode(errors="replace").strip() or "detached HEAD",  # Q7
        "lang": name.rpartition(".")[2].lower() if "." in name else None,  # Q9, same rule as review_files
    }
