from pydantic import BaseModel


class BundleOut(BaseModel):
    task_id: int
    title: str
    import_key: str
    created: bool
    status: str  # where it landed (§5.2, 032 Q5)
    rounds: int  # round folders in the bundle
    transcripts: int  # transcript copies this time
