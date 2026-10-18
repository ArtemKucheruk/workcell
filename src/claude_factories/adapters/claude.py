"""The `claude` CLI, run as a subprocess with an argument list (docs/MVP.md §4.3, §4.4)."""

import json
import os
import signal
import subprocess
from typing import Protocol


def stripped_env() -> dict:
    """§4.3: no API key or provider variables, so claude bills to the subscription."""
    return {k: v for k, v in os.environ.items()
            if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN") and not k.startswith("CLAUDE_CODE_USE_")}


class Claude(Protocol):
    def auth_status(self, cwd: str, env: dict) -> dict | None: ...
    def spawn(self, args: list[str], cwd: str, env: dict, log_path: str) -> subprocess.Popen: ...
    def stop(self, pid: int) -> None: ...


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
