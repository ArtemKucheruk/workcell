# docs/MVP.md §4.6: the backend image. Node and the claude CLI arrive with 028.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.8.20 /uv /bin/uv
WORKDIR /app
# the base image's Python 3.12, never a download; .pyc built now, since the runtime uid can't write here
ENV UV_PYTHON_DOWNLOADS=never UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable
# 777: Docker copies it into a new named volume, so the override's uid can create factory.db (Q4)
RUN mkdir -m 777 /data
ENV PATH=/app/.venv/bin:$PATH FCTL_HOME=/data
CMD ["fctl", "serve", "--host", "0.0.0.0"]
