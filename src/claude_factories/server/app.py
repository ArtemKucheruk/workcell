"""The app behind `fctl serve`: lifespan, the §4.5 middleware, error handlers, static files, and the
routers (docs/MVP.md §4.7)."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .. import db
from ..controllers import factory, pages_api, projects, reviews, rounds, runs, tasks, workspaces
from ..controllers.pages import code, dashboard, templates
from ..controllers.pages import projects as project_pages
from ..controllers.pages import tasks as task_pages
from ..controllers.pages import workspaces as workspace_pages
from ..domain.errors import Conflict, DomainError, Failed, Invalid, NotFound, TooLarge

PKG = Path(__file__).parent.parent
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


async def page_not_found(request: Request, exc: StarletteHTTPException):
    """A browser GET of a missing page, task, or round gets a page, not JSON. /api and every other
    status keep FastAPI's JSON."""
    if exc.status_code == 404 and request.method == "GET" and not request.url.path.startswith("/api/"):
        return templates.TemplateResponse(request, "error.html", {"detail": exc.detail}, status_code=404)
    return await http_exception_handler(request, exc)


async def unencodable(request: Request, exc: UnicodeEncodeError):
    """A JSON `\\ud800` escape decodes to a lone surrogate, which UTF-8 and SQLite reject: a 422, not
    a 500. Raised inside a transaction, so it rolls back."""
    return JSONResponse({"detail": "text must not contain lone surrogates"}, status_code=422)


async def domain_error(request: Request, exc: DomainError):
    """A handler's refusal, answered exactly as the same HTTPException would be (Q9)."""
    return await page_not_found(request, HTTPException(STATUS[type(exc)], exc.detail))


def create_app() -> FastAPI:
    app = FastAPI(title="Claude Factories", lifespan=lifespan)
    app.middleware("http")(local_safety)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(StarletteHTTPException, page_not_found)
    app.add_exception_handler(UnicodeEncodeError, unencodable)
    app.add_exception_handler(DomainError, domain_error)
    app.mount("/static", StaticFiles(directory=PKG / "static"), name="static")
    for module in (workspaces, projects, factory, tasks, rounds, reviews, runs, pages_api,
                   dashboard, workspace_pages, project_pages, code, task_pages):
        app.include_router(module.router)
    return app
