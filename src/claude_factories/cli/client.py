import json
import os
import urllib.error
import urllib.request

from .output import fail

DEFAULT_URL = "http://127.0.0.1:4545"


def base_url() -> str:
    return (os.environ.get("FCTL_URL") or DEFAULT_URL).rstrip("/")


def api(method: str, path: str, body=None, data: bytes | None = None, content_type: str | None = None):
    """Call the app with a JSON `body`, or raw `data` sent as `content_type`. Returns parsed JSON, the bytes of
    an application/zip reply (032), or text; on any failure prints to stderr and exits 1."""
    base = base_url()
    headers = {"X-Requested-By": "fctl"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    elif data is not None and content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            if resp.headers.get_content_type() == "application/json":
                return json.loads(raw)
            if resp.headers.get_content_type() == "application/zip":
                return raw
            return raw.decode()
    except urllib.error.HTTPError as e:
        text = e.read().decode(errors="replace")
        try:
            detail = json.loads(text)["detail"]
        except (ValueError, KeyError, TypeError):
            detail = text or e.reason
        if not isinstance(detail, str):
            detail = json.dumps(detail)
        fail(f"{e.code} {detail}")
    except OSError:  # URLError (refused, DNS) and resets mid-response
        fail(f'can\'t reach {base} — is "fctl serve" running?')
