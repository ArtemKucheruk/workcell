"""The `claude` CLI, run as a subprocess with an argument list (docs/MVP.md §4.3, §4.4)."""

import json
import os
import re
import select
import signal
import subprocess
from time import monotonic
from typing import Protocol

LOGIN_URL_TIMEOUT = 30  # 039 Q4: seconds for `claude auth login` to print its sign-in URL
URL = re.compile(r"https://[^\s\x1b\x07]+")  # 039 Q2: ends at whitespace, ESC, or BEL (OSC 8 hyperlinks)
PROMPT = "Paste code here if prompted > "  # 039 Q1: printed with no newline, so its own line in last_line()


def stripped_env() -> dict:
    """§4.3: no API key or provider variables, so claude bills to the subscription."""
    return {k: v for k, v in os.environ.items()
            if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN") and not k.startswith("CLAUDE_CODE_USE_")}


class Claude(Protocol):
    def auth_status(self, cwd: str, env: dict) -> dict | None: ...
    def spawn(self, args: list[str], cwd: str, env: dict, log_path: str) -> subprocess.Popen: ...
    def stop(self, pid: int) -> None: ...
    def login(self, cwd: str, env: dict) -> tuple[subprocess.Popen, str | None, str]: ...


def read(pipe, timeout: float, done=lambda text: False) -> str:
    """What `pipe` yields within `timeout` s, up to EOF or until `done(text so far)`. Read off its fd with
    select, so a silent claude can't block past the timeout."""
    out, deadline = b"", monotonic() + timeout
    while not done(out.decode(errors="replace")):
        left = deadline - monotonic()
        if left <= 0 or not select.select([pipe], [], [], left)[0]:
            break
        chunk = os.read(pipe.fileno(), 65536)
        if not chunk:  # EOF: claude exited
            break
        out += chunk
    return out.decode(errors="replace")


def last_line(out: str) -> str:
    """039 Q4: claude's last non-empty output line, without the code prompt glued to its front."""
    return next((line.strip() for line in reversed(out.replace(PROMPT, "\n").splitlines()) if line.strip()), "")


class SubprocessClaude:
    def auth_status(self, cwd: str, env: dict) -> dict | None:
        """§4.3, 012 Q6: `claude auth status`'s parsed answer if it exits 0 and reports claude.ai, else
        None. Run in `cwd` with `env` exactly as given."""
        try:
            r = subprocess.run(["claude", "auth", "status"], cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                               capture_output=True, text=True, timeout=30)
            info = json.loads(r.stdout)
        except (OSError, ValueError, subprocess.TimeoutExpired):  # no binary, not JSON, hung
            return None
        return info if r.returncode == 0 and isinstance(info, dict) and info.get("authMethod") == "claude.ai" else None

    def spawn(self, args: list[str], cwd: str, env: dict, log_path: str) -> subprocess.Popen:
        """§4.4: `claude *args` in its own session (so Stop can signal its group), stdin from /dev/null,
        stdout and stderr to the log. OSError propagates."""
        with open(log_path, "wb") as log:
            return subprocess.Popen(["claude", *args], cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=log,
                                    stderr=subprocess.STDOUT, start_new_session=True)

    def stop(self, pid: int) -> None:
        """013 Q2: SIGTERM the run's process group."""
        try:
            os.killpg(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):  # the group exited; or its id is now another user's
            pass

    def login(self, cwd: str, env: dict) -> tuple[subprocess.Popen, str | None, str]:
        """039 Q1: `claude auth login --claudeai` in its own session (so stop() ends it), stdin piped for the
        code, stderr into stdout. Its output up to the first sign-in URL (Q2), or up to exit or
        LOGIN_URL_TIMEOUT: (process, URL or None, output). OSError propagates."""
        proc = subprocess.Popen(["claude", "auth", "login", "--claudeai"], cwd=cwd, env=env, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
        # a URL counts once something follows it, so a chunk ending mid-URL isn't taken
        out = read(proc.stdout, LOGIN_URL_TIMEOUT, lambda text: bool((m := URL.search(text)) and m.end() < len(text)))
        found = URL.search(out)
        return proc, found and found.group(), out
