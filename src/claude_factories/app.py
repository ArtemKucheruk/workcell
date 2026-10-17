"""The FastAPI app behind `fctl serve`."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db

HERE = Path(__file__).parent
ALLOWED_HOSTS = {"127.0.0.1", "localhost"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    yield


app = FastAPI(title="Claude Factories", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")


@app.middleware("http")
async def local_safety(request: Request, call_next):
    """docs/MVP.md §4.5: block DNS rebinding (Host) and CSRF (X-Requested-By)."""
    hostname = request.headers.get("host", "").partition(":")[0].lower()
    if hostname not in ALLOWED_HOSTS:
        return JSONResponse({"detail": "Host must be 127.0.0.1 or localhost"}, status_code=403)
    if request.method not in SAFE_METHODS and request.headers.get("x-requested-by") != "fctl":
        return JSONResponse({"detail": "X-Requested-By: fctl header required"}, status_code=403)
    return await call_next(request)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    # ponytail: placeholder page; the dashboard (job 017) replaces it
    return templates.TemplateResponse(request, "index.html")
