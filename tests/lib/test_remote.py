"""090: lib.remote, a project's remote as a browser URL for the code page."""

import re

import pytest

from workcell.lib.remote import blob_url, web_url

REPO = "https://github.com/owner/repo"
NONE = ["/home/me/repo", "../repo", "C:\\repo", "file:///srv/repo.git", None, "", "javascript:alert(1)",
        "javascript://github.com/%0aalert(1)", "data:text/html,x", "ftp://host/o/r", "https://github.com"]
CASES = {
    "git@github.com:owner/repo.git": REPO,
    "ssh://git@github.com/owner/repo.git": REPO,
    "ssh://git@host:2222/o/r.git": "https://host/o/r",
    "https://github.com/owner/repo.git": REPO,
    "https://github.com/owner/repo": REPO,
    "https://github.com/owner/repo/": REPO,
    "https://user:token@github.com/owner/repo.git": REPO,
    "https://token@github.com/owner/repo": REPO,
    "http://git.local:8080/o/r.git": "http://git.local:8080/o/r",
} | dict.fromkeys(NONE)


def test_scp_like():  # AC1
    assert web_url("git@github.com:owner/repo.git") == REPO


def test_ssh():  # AC2
    assert web_url("ssh://git@github.com/owner/repo.git") == REPO
    assert web_url("ssh://git@host:2222/o/r.git") == "https://host/o/r"


@pytest.mark.parametrize("remote", ["https://github.com/owner/repo.git", "https://github.com/owner/repo",
                                    "https://github.com/owner/repo/", "https://github.com/owner/repo.git/"])
def test_https(remote):  # AC3
    assert web_url(remote) == REPO


@pytest.mark.parametrize("remote", ["https://user:token@github.com/owner/repo.git", "https://token@github.com/owner/repo",
                                    "ssh://user:pw@github.com/owner/repo.git"])
def test_credentials_stripped(remote):  # AC4
    assert web_url(remote) == REPO
    assert "@" not in web_url(remote)


def test_http_keeps_scheme_and_port():  # AC5
    assert web_url("http://git.local:8080/o/r.git") == "http://git.local:8080/o/r"


@pytest.mark.parametrize("remote", NONE + ["git://github.com/o/r.git", "host:o/r", "https://github.com/",
                                           "https://github.com/o/r\n", "https://bad host/o/r"])
def test_no_link(remote):  # AC6
    assert web_url(remote) is None


@pytest.mark.parametrize("remote", list(CASES))
def test_results_are_http_and_clean(remote):  # AC7
    url = web_url(remote)
    assert url == CASES[remote]
    if url is not None:
        assert url.startswith(("https://", "http://"))
        assert not re.search(r"[\s\x00-\x1f\x7f]", url)
        assert "@" not in url


def test_blob_url():  # AC9, AC10 (Q5): github.com only, each segment encoded
    assert blob_url(REPO, "main", "src/a.py") == f"{REPO}/blob/main/src/a.py"
    assert blob_url(REPO, "main", "a b#c.txt") == f"{REPO}/blob/main/a%20b%23c.txt"
    assert blob_url(REPO, "release/1.0", "a?.py") == f"{REPO}/blob/release/1.0/a%3F.py"
    assert blob_url("https://gitlab.com/o/r", "main", "a.py") is None
    assert blob_url(None, "main", "a.py") is None
