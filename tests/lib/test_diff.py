from workcell.lib.diff import diff_rows


def test_diff_rows_without_the_app():  # 036 AC8
    assert diff_rows("@@ -1,2 +1,2 @@\n a\n-b\n+c\n\\ No newline at end of file\n") == [
        {"kind": "hunk", "old": None, "new": None, "text": "@@ -1,2 +1,2 @@"},
        {"kind": "ctx", "old": 1, "new": 1, "text": "a"},
        {"kind": "del", "old": 2, "new": None, "text": "b"},
        {"kind": "add", "old": None, "new": 2, "text": "c"},
        {"kind": "note", "old": None, "new": None, "text": "\\ No newline at end of file"},
    ]
