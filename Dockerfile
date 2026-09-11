# syntax=docker/dockerfile:1.7

FROM python:3.12.12-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --gid 10001 app && \
    useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

COPY pyproject.toml constraints.txt README.md ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

RUN PIP_CONSTRAINT=/app/constraints.txt python -m pip install . && \
    mkdir -p /tmp/enterprise-ai && \
    chown -R app:app /tmp/enterprise-ai

FROM base AS test

USER root
COPY tests ./tests
RUN PIP_CONSTRAINT=/app/constraints.txt python -m pip install ".[dev]"
USER app

CMD ["pytest", "-m", "postgres"]

FROM base AS runtime

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).read()"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
