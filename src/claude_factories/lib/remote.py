"""090: a project's `remote_url` (`git remote get-url origin`, docs/MVP.md §3.1) as a browser URL for the code page
(docs/ui.md §8 item 6). Pure; the SPA only ever renders what `web_url` returns, never the raw remote."""

import re
from urllib.parse import quote, urlsplit

# Q2: scp-like `user@host:path`; the `user@` is required, so `C:\repo` and `host:path` don't match
SCP = re.compile(r"([^@/:\s]+)@([^@/:\s]+):(?!//)(.+)")
HOST = re.compile(r"[A-Za-z0-9.-]+")  # ponytail: no IPv6 literal hosts; such a remote gets no link
UNSAFE = re.compile(r"[\x00-\x20\x7f]")
# RFC 3986 pchar minus `@` (AC4: never in a result) and `:`; everything else is percent-encoded
PATH_SAFE = "/-._~!$&'()*+,;=%"


def web_url(remote: str | None) -> str | None:
    """AC1–AC7: `https://host/owner/repo` for an scp-like or ssh:// remote, the same scheme and port for an http(s)
    one, credentials and `.git` dropped; None for anything else (a local path, file://, git://, javascript:)."""
    if not remote or UNSAFE.search(remote):
        return None
    if scp := SCP.fullmatch(remote):
        scheme, host, port, path = "https", scp[2], None, scp[3]
    else:
        try:
            parts = urlsplit(remote)
            port = parts.port
        except ValueError:  # a bad port or bracketed host
            return None
        scheme, host, path = parts.scheme.lower(), parts.hostname or "", parts.path
        if scheme == "ssh":  # Q2: always https, and the ssh port means nothing to the web host (AC2)
            scheme, port = "https", None
        elif scheme not in ("http", "https"):
            return None
    path = path.strip("/").removesuffix(".git").strip("/")
    if not HOST.fullmatch(host) or not path:
        return None
    return f"{scheme}://{host.lower()}{'' if port is None else f':{port}'}/{quote(path, safe=PATH_SAFE)}"


def blob_url(web: str | None, branch: str, path: str) -> str | None:
    """AC9, Q5: `<web>/blob/<branch>/<path>` on github.com alone, each segment percent-encoded; None elsewhere."""
    if not web or urlsplit(web).hostname != "github.com":
        return None
    return f"{web}/blob/{quote(branch, safe='/')}/{quote(path, safe='/')}"
