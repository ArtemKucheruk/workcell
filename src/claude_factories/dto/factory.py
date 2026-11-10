from pydantic import BaseModel


class FactoryBody(BaseModel):
    overwrite: bool = False


class FactoryOut(BaseModel):
    written: list[str]
    skipped: list[str]
    commit_hint: str


class ImportBody(BaseModel):
    job: str | None = None  # None imports every job on factory/board.json


class ImportedJob(BaseModel):
    job: str
    task_id: int
    created: bool
    rounds: int  # round folders imported this time
    transcripts: int  # transcript copies this time


class ImportOut(BaseModel):
    imported: list[ImportedJob]
    skipped: int  # 058 Q1: backlog.md lines skipped; 0 for {"job": …}
