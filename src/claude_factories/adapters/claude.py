"""The `claude` CLI, run as a subprocess with an argument list (docs/MVP.md §4.3)."""

import json
import subprocess
from typing import Protocol


class Claude(Protocol):
    def auth_status(self, cwd: str, env: dict) -> dict | None: ...


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
