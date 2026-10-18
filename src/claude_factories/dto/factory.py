from pydantic import BaseModel


class FactoryBody(BaseModel):
    overwrite: bool = False


class FactoryOut(BaseModel):
    written: list[str]
    skipped: list[str]
    commit_hint: str
