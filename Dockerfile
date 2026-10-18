# docs/MVP.md §4.6: the backend image. git, uv, Node 22 with npm, and a pinned claude CLI, which is
# what runs get. Anything else goes in a custom image FROM this one (compose.override.example.yaml).
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.8.20 /uv /bin/uv
# 028 Q3: Debian's nodejs isn't 22, so node comes from frontend/Dockerfile's tag
COPY --from=node:22-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
# Q2: the global install sits in world-readable /usr/local; a new pin is how it updates
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && npm install -g @anthropic-ai/claude-code@2.1.302 && rm -rf /root/.npm
WORKDIR /app
# .pyc built now, since the runtime uid can't write here
ENV UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock ./
COPY src ./src
# Q9: the app on the base image's Python 3.12; a run's uv may fetch another into ~/.local/share/uv
RUN UV_PYTHON_DOWNLOADS=never uv sync --frozen --no-dev --no-editable
# 777: Docker copies it into a new named volume, so the override's uid can create factory.db (Q4)
RUN mkdir -m 777 /data
# Q4: HOME on the backend-home volume holds ~/.claude, ~/.claude.json, and the uv and npm caches.
# Sticky like /tmp: the uid isn't known at build time, and only the uid that made a file may replace it.
RUN mkdir -m 1777 /home/fctl
ENV PATH=/app/.venv/bin:$PATH FCTL_HOME=/data
# Q6: the takeover command becomes `docker compose exec`; Q2: the runtime uid can't update claude
ENV HOME=/home/fctl FCTL_IN_DOCKER=1 DISABLE_AUTOUPDATER=1
CMD ["fctl", "serve", "--host", "0.0.0.0"]
