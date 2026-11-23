"""The app behind `fctl serve`: lifespan, the §4.5 middleware, error handlers, and the routers
(docs/MVP.md §4.7). JSON only, every 404 included: the pages are SPA routes on the frontend server
(docs/data-model-and-api.md §6.4)."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .. import db
from ..controllers import (bundles, context_items, factories, factory, pages_api, projects, pull_requests, reviews,
                           rounds, runs, schedules, tasks, transcripts, usage, workspaces)
from ..domain.errors import Conflict, DomainError, Failed, Invalid, NotFound, TooLarge

ALLOWED_HOSTS = {"127.0.0.1", "localhost"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
STATUS = {NotFound: 404, Conflict: 409, TooLarge: 413, Invalid: 422, Failed: 500}


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    yield


async def local_safety(request: Request, call_next):
    """docs/MVP.md §4.5: block DNS rebinding (Host) and CSRF (X-Requested-By)."""
    hostname = request.headers.get("host", "").partition(":")[0].lower()
    if hostname not in ALLOWED_HOSTS:
        return JSONResponse({"detail": "Host must be 127.0.0.1 or localhost"}, status_code=403)
    if request.method not in SAFE_METHODS and request.headers.get("x-requested-by") != "fctl":
        return JSONResponse({"detail": "X-Requested-By: fctl header required"}, status_code=403)
    return await call_next(request)


async def validation_error(request: Request, exc: RequestValidationError):
    """FastAPI's default 422 without each error's echoed `input`: json.loads lets NaN and Infinity
    in, and echoing them back would fail to encode as JSON and turn the 422 into a 500."""
    errors = [{k: v for k, v in e.items() if k != "input"} for e in exc.errors()]
    return JSONResponse({"detail": jsonable_encoder(errors)}, status_code=422)


async def unencodable(request: Request, exc: UnicodeEncodeError):
    """A JSON `\\ud800` escape decodes to a lone surrogate, which UTF-8 and SQLite reject: a 422, not
    a 500. Raised inside a transaction, so it rolls back."""
    return JSONResponse({"detail": "text must not contain lone surrogates"}, status_code=422)


async def domain_error(request: Request, exc: DomainError):
    """A handler's refusal, answered exactly as the same HTTPException would be (Q9)."""
    return await http_exception_handler(request, HTTPException(STATUS[type(exc)], exc.detail))


def create_app(port: int = 4545) -> FastAPI:
    """104 Q4: `port` is the one `fctl serve` listens on, kept for the scheduler's FCTL_URL, which has no request to
    read it from. 104 AC21, AC22: schedules after runs, so its lifespan starts after the runs sweep and stops first."""
    app = FastAPI(title="Claude Factories", lifespan=lifespan)
    app.state.port = port
    app.middleware("http")(local_safety)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(UnicodeEncodeError, unencodable)
    app.add_exception_handler(DomainError, domain_error)
    for module in (workspaces, projects, context_items, factory, factories, tasks, rounds, reviews, pull_requests, runs,
                   schedules, transcripts, bundles, usage, pages_api):
        app.include_router(module.router)
    return app
