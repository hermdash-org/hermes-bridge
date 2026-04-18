# ─────────────────────────────────────────────────────────────────────
# HemUI Bridge — Self-contained Docker image
#
# Multi-stage build:
#   Stage 1 (builder): Compile bridge .py → .so with Cython (obfuscated)
#   Stage 2 (production): hermes-agent + compiled bridge (no source code)
#
# Build:  docker build -t hermes-dashboard .
# Run:    docker run -d --restart=always -p 8420:8420 -v ~/.hermes:/opt/data hermes-dashboard
# ─────────────────────────────────────────────────────────────────────

# Pin the hermes-agent version we've tested against.
ARG HERMES_VERSION=main


# ── Stage 1: Compile bridge to .so (source code dies here) ──────────

FROM python:3.11-slim AS builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential gcc python3-dev && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir cython setuptools

WORKDIR /build
COPY bridge/ ./bridge/
COPY setup.py ./

# Compile all .py → .so
RUN python setup.py build_ext --inplace

# Delete ALL .py source files (keep only __init__.py and .so)
RUN find bridge/ -name "*.py" ! -name "__init__.py" -delete && \
    find bridge/ -name "*.c" -delete && \
    find bridge/ -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# Strip __init__.py files to minimum (just enough for Python to find packages)
RUN find bridge/ -name "__init__.py" -exec sh -c 'echo "" > "$1"' _ {} \;


# ── Stage 2: Production image ──────────────────────────────────────

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV HERMES_HOME=/opt/data

# System deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git curl build-essential gcc \
        nodejs npm \
        ripgrep ffmpeg \
        python3-dev libffi-dev procps && \
    rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    ln -s /root/.local/bin/uv /usr/local/bin/uv

# Clone hermes-agent at pinned version
ARG HERMES_VERSION
RUN git clone --recurse-submodules --depth 1 \
    --branch ${HERMES_VERSION} \
    https://github.com/NousResearch/hermes-agent.git /opt/hermes || \
    git clone --recurse-submodules --depth 1 \
    https://github.com/NousResearch/hermes-agent.git /opt/hermes

WORKDIR /opt/hermes

# Install hermes deps
RUN uv venv venv --python 3.11 && \
    VIRTUAL_ENV=/opt/hermes/venv uv pip install --no-cache-dir -e ".[all]"

# Node deps
RUN npm install --prefer-offline --no-audit 2>/dev/null || true

# Install bridge deps into hermes venv
RUN VIRTUAL_ENV=/opt/hermes/venv uv pip install --no-cache-dir \
    fastapi uvicorn[standard] pyyaml httpx

# Copy ONLY compiled bridge (.so files + empty __init__.py) — NO SOURCE CODE
COPY --from=builder /build/bridge/ /opt/bridge/bridge/

# Python path
ENV PYTHONPATH="/opt/hermes:/opt/bridge"
ENV PATH="/opt/hermes/venv/bin:${PATH}"

# Entrypoint
COPY docker/entrypoint.sh /opt/entrypoint.sh
RUN chmod +x /opt/entrypoint.sh

VOLUME ["/opt/data"]
EXPOSE 8420

ENTRYPOINT ["/opt/entrypoint.sh"]
