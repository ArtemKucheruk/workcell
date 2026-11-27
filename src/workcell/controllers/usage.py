"""095, docs/data-model-and-api.md §6.4: GET /api/usage, the Usage page's data."""

from fastapi import APIRouter

from ..dto.usage import UsageOut
from ..handlers import usage as handler
from ..server.deps import ClaudeAccounts, Usage

router = APIRouter()


@router.get("/api/usage")
def usage(accounts: ClaudeAccounts, usage: Usage, days: int = 7) -> UsageOut:
    """AC14: `days` 7 (the default) or 30; anything else is a 422. Loaded once per period, never polled."""
    return handler.usage(accounts, usage, days)
