FROM python:3.11-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock* ./

# Install dependencies (production only, no dev extras)
RUN uv sync --frozen --no-dev

# Copy application code
COPY runtime/      ./runtime/
COPY agy/          ./agy/
COPY mcp_servers/  ./mcp_servers/
COPY frontend/     ./frontend/
COPY specs/        ./specs/

# Cloud Run expects PORT env var; default 8080
ENV PORT=8080
ENV PYTHONPATH=/app

EXPOSE 8080

# Use entrypoint so we can pass Cloud Run PORT env var through
CMD ["uv", "run", "python", "deployment/cloudrun/entrypoint.py"]
