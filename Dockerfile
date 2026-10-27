FROM node:24.14.1-bookworm-slim AS frontend
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.14.3-slim-bookworm AS controller
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml ./
COPY src/ src/
RUN pip install --no-cache-dir .
COPY migrations/ migrations/
COPY alembic.ini ./
COPY --from=frontend /web/dist web/dist/
RUN useradd --uid 10001 --create-home leroy && mkdir /data && chown leroy:leroy /data
USER leroy
EXPOSE 8088
CMD ["sh", "-c", "alembic upgrade head && exec python -m leroy.server"]

FROM docker:29.8.1-cli AS docker-cli
FROM python:3.14.3-slim-bookworm AS runner
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker-cli /usr/local/libexec/docker/cli-plugins /usr/local/libexec/docker/cli-plugins
WORKDIR /app
COPY pyproject.toml ./
COPY src/ src/
RUN pip install --no-cache-dir .
CMD ["python", "-m", "leroy.runner"]

FROM runner AS job
COPY --from=frontend /usr/local/bin/node /usr/local/bin/node
COPY --from=frontend /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && apt-get update && apt-get install -y --no-install-recommends git ca-certificates openssh-client rsync bash jq curl \
    && rm -rf /var/lib/apt/lists/* && mkdir /job /work \
    && pip install --no-cache-dir ansible-core==2.21.4
ENV GIT_TERMINAL_PROMPT=0 PYTHONUNBUFFERED=1
CMD ["python", "-m", "leroy.worker"]
