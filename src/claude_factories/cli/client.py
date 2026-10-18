import json
import os
import urllib.error
import urllib.request

from .output import fail

DEFAULT_URL = "http://127.0.0.1:4545"


def base_url() -> str:
    return (os.environ.get("FCTL_URL") or DEFAULT_URL).rstrip("/")


def api(method: str, path: str, body=None):
    """Call the app. Returns parsed JSON or text; on any failure prints to stderr and exits 1."""
    base = base_url()
    headers = {"X-Requested-By": "fctl"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            if resp.headers.get_content_type() == "application/json":
                return json.loads(raw)
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
