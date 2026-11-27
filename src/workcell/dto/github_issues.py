from pydantic import BaseModel


class IssuesSynced(BaseModel):
    """108 AC14, Q4: `skipped` is every listed issue that is neither new nor updated."""
    new: int
    updated: int
    skipped: int
