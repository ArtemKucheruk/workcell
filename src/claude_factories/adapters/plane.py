"""109: Plane's REST API v1 (developers.plane.so) over stdlib urllib, only to the API URL saved in project Settings
and only on Sync now and approve (docs/MVP.md §4.5). The key travels as `X-API-Key` alone; it is never logged and
no detail raised here names it. Redirects aren't followed, so the key can't be forwarded to another host."""

import http.client
import json
import urllib.error
import urllib.request
from urllib.parse import quote, urlencode, urlsplit

from ..domain.errors import Conflict, Failed

TIMEOUT = 30
PAGES = 50  # ponytail (Q4): 50 pages of 100 items; past that a sync counts only what it read
REFUSED = "Plane refused the API key: check it in project Settings"
RATE = "Plane's rate limit was hit: try again in a minute"


class Missing(Exception):
    """A 404, which each caller words (or falls back on) itself."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None  # a 3xx becomes an HTTPError: "Plane answered 302 to …"


OPENER = urllib.request.build_opener(NoRedirect)


class Plane:
    """Every method takes the saved API URL (no trailing `/`) and key."""

    def request(self, url: str, key: str, method: str, path: str, query: dict | None = None, body=None):
        """The JSON answer to `method path`; AC12's refusals as domain errors, a 404 as Missing."""
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(url + path + (f"?{urlencode(query)}" if query else ""), data=data, method=method,
                                     headers={"X-API-Key": key, "Accept": "application/json"})
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with OPENER.open(req, timeout=TIMEOUT) as r:
                status, raw = r.status, r.read()
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise Conflict(REFUSED)
            if e.code == 404:
                raise Missing()
            if e.code == 429:
                raise Conflict(RATE)
            raise Failed(f"Plane answered {e.code} to {urlsplit(req.full_url).path}")
        except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError):  # unreachable, timeout, reset, a bad URL
            raise Conflict(f"can't reach {url}: check the API URL in project Settings")
        try:
            return json.loads(raw)
        except ValueError:
            raise Failed(f"Plane answered {status} to {urlsplit(req.full_url).path}")

    def base(self, slug: str, project_id: str) -> str:
        return f"/api/v1/workspaces/{quote(slug, safe='')}/projects/{quote(project_id, safe='')}/"

    def listed(self, url: str, key: str, path: str) -> list:
        """AC6: every page of a cursor-paginated list, following next_cursor while next_page_results is true. A bare
        list answer is the whole list."""
        found, query = [], {"per_page": 100}
        for _ in range(PAGES):
            page = self.request(url, key, "GET", path, query)
            if isinstance(page, list):
                return page
            results = page.get("results") if isinstance(page, dict) else None
            if not isinstance(results, list):
                raise Failed(f"Plane answered no results list to {path}")
            found += results
            if not (page.get("next_page_results") and page.get("next_cursor")):
                break
            query = {"per_page": 100, "cursor": page["next_cursor"]}
        return found

    def project(self, url: str, key: str, slug: str, project_id: str) -> dict:
        """AC12: a 404 here means the workspace or project doesn't exist."""
        try:
            found = self.request(url, key, "GET", self.base(slug, project_id))
        except Missing:
            raise Conflict(f"Plane has no workspace {slug} or project {project_id}: check them in project Settings")
        if not isinstance(found, dict) or not isinstance(found.get("identifier"), str):
            raise Failed(f"Plane answered no project identifier to {self.base(slug, project_id)}")
        return found

    def states(self, url: str, key: str, slug: str, project_id: str) -> list:
        path = self.base(slug, project_id) + "states/"
        try:
            return self.listed(url, key, path)
        except Missing:
            raise Failed(f"Plane answered 404 to {path}")

    def items(self, url: str, key: str, slug: str, project_id: str) -> list:
        """AC6, AC7: `work-items/`, else `issues/` on servers older than the rename."""
        path = self.base(slug, project_id)
        try:
            return self.listed(url, key, path + "work-items/")
        except Missing:
            pass
        try:
            return self.listed(url, key, path + "issues/")
        except Missing:
            raise Failed(f"Plane answered 404 to {path}issues/")

    def set_state(self, url: str, key: str, slug: str, project_id: str, item_id: str, state_id: str) -> None:
        """AC13: PATCH the item's state, falling back to `issues/` the AC7 way."""
        path = self.base(slug, project_id)
        item = quote(item_id, safe="")
        try:
            self.request(url, key, "PATCH", f"{path}work-items/{item}/", body={"state": state_id})
            return
        except Missing:
            pass
        try:
            self.request(url, key, "PATCH", f"{path}issues/{item}/", body={"state": state_id})
        except Missing:
            raise Failed(f"Plane answered 404 to {path}issues/{item}/")
