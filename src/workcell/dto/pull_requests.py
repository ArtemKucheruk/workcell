"""093: Create PR, the PR's state, and Merge PR (docs/data-model-and-api.md §6.3)."""

from pydantic import BaseModel


class PrCreated(BaseModel):
    number: int
    url: str
    reused: bool  # AC21: an open PR for the branch was there already


class Checks(BaseModel):
    passed: int
    failed: int
    pending: int


class PrState(BaseModel):
    number: int
    url: str
    state: str  # gh's OPEN, MERGED, or CLOSED
    checks: Checks


class PrMerged(BaseModel):
    number: int
    state: str  # MERGED
    notes: list[str]  # AC31–AC35: one per step after the merge
