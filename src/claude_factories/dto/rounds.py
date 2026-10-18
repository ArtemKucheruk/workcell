from pydantic import BaseModel, Field


class RoundBody(BaseModel):
    """§6.3's rounds body, and §6.2's `submit` (005 Q4). base_sha may later become a git argument."""
    base_sha: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    patch: str
    build_md: str | None = None


class RoundSubmitted(BaseModel):
    round: int
    files_changed: int
    additions: int
    deletions: int
    url: str


class RoundSummary(BaseModel):
    n: int
    trigger: str
    files: int
    additions: int
    deletions: int
    verdicts: dict[str, str]  # all 4 reviewers in REVIEWERS order, "pending" if missing
