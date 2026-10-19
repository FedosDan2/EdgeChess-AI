# Optional Ubuntu environment; dependencies come only from the uv project.
FROM ghcr.io/astral-sh/uv:0.12.10 AS uv
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 python3.10-venv ca-certificates libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /uvx /bin/
# Keep the environment outside the source mount; never mount a host .venv.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON_DOWNLOADS=never
WORKDIR /work/convert
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev && uv pip check --python /opt/venv/bin/python
ENTRYPOINT ["uv", "run", "--no-sync"]
