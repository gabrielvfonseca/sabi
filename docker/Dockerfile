# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH=/root/.local/bin:$PATH

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip

FROM base AS deps
COPY requirements.txt pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -e .[dev]

FROM base AS runtime
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin
COPY src ./src

ENV SABI_USERNAME="" \
    SABI_PASSWORD="" \
    SABI_OUTPUT=/data/sabi_records.csv \
    SABI_DB=/data/sabi_records.sqlite

VOLUME ["/data"]
WORKDIR /app

ENTRYPOINT ["python", "-m", "src.cli"]
CMD ["--help"]

FROM runtime AS dev
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -e .[dev]
ENTRYPOINT ["python", "-m", "src.cli"]
