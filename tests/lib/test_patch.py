"""lib/patch.py with no app and no database (035 AC5, AC6)."""

import pytest

from claude_factories.domain.errors import Invalid
from claude_factories.lib.patch import split_patch

PATCH = (
    "diff --git a/a.py b/a.py\n"
    "index 1111111..2222222 100644\n"
    "--- a/a.py\n"
    "+++ b/a.py\n"
    "@@ -1,2 +1,2 @@\n"
    " keep\n"
    "-old\n"
    "+new\n"
    "diff --git a/b.py b/b.py\n"
    "deleted file mode 100644\n"
    "index 3333333..0000000\n"
    "--- a/b.py\n"
    "+++ /dev/null\n"
    "@@ -1,4 +0,0 @@\n"
    "-one\n"
    "-two\n"
    "-three\n"
    "-four\n"
    "diff --git a/c.py b/c.py\n"
    "new file mode 100644\n"
    "index 0000000..4444444\n"
    "--- /dev/null\n"
    "+++ b/c.py\n"
    "@@ -0,0 +1,2 @@\n"
    "+one\n"
    "+two\n"
)
ROWS = [  # 005 AC1's rows: path, old_path, change, binary, additions, deletions
    ("a.py", None, "modified", 0, 1, 1),
    ("b.py", None, "deleted", 0, 0, 4),
    ("c.py", None, "added", 0, 2, 0),
]
KEYS = ("path", "old_path", "change", "binary", "additions", "deletions")


def test_split_in_patch_order():  # 035 AC5
    rows = split_patch(PATCH)
    assert [tuple(r[k] for k in KEYS) for r in rows] == ROWS
    assert "".join(r["patch"] for r in rows) == PATCH


def test_not_a_patch():  # 035 AC6
    with pytest.raises(Invalid) as e:
        split_patch("hello\n")
    assert e.value.detail == 'patch must start with "diff --git"'


def test_unsafe_path():  # 035 AC6
    patch = ("diff --git a/x b/x\nnew file mode 100644\n--- /dev/null\n+++ b/../etc/passwd\n"
             "@@ -0,0 +1 @@\n+root\n")
    with pytest.raises(Invalid) as e:
        split_patch(patch)
    assert e.value.detail.startswith("can't read a safe file path in:")
