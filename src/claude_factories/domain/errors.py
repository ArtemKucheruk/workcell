"""What a handler raises to refuse. server/ maps each kind to an HTTP status, `detail` to the body's."""


class DomainError(Exception):
    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class NotFound(DomainError):
    def __init__(self, detail: str = "Not Found"):  # HTTPException(404)'s detail
        super().__init__(detail)


class Conflict(DomainError):
    pass


class TooLarge(DomainError):
    pass


class Invalid(DomainError):
    """A request the handler refuses as unprocessable: 422 (035 Q1)."""


class Failed(DomainError):
    """Something the request needed couldn't be done, e.g. claude wouldn't start: 500 (036 Q2)."""
