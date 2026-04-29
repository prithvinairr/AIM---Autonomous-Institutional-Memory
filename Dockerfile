# ── Build stage ───────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build deps only (not in final image)
RUN pip install --no-cache-dir hatchling

COPY pyproject.toml ./
COPY aim/ aim/

RUN pip install --no-cache-dir --prefix=/install .


# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL maintainer="AIM Team"
LABEL description="AIM – Autonomous Institutional Memory"

# Security: run as non-root
RUN groupadd --gid 1000 aim && \
    useradd --uid 1000 --gid aim --shell /bin/bash --create-home aim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local
COPY aim/ aim/

# Ensure Python can find the package
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    WEB_CONCURRENCY=1

USER aim

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://localhost:8000/health', timeout=4)"

ENTRYPOINT ["uvicorn", "aim.main:app", \
    "--host", "0.0.0.0", \
    "--port", "8000", \
    "--workers", "1", \
    "--log-config", "/dev/null"]
