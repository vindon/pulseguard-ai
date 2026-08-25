FROM python:3.12-slim

# ARM64 / amd64 universal image
ARG TARGETPLATFORM
RUN echo "Building for $TARGETPLATFORM"

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.4 /uv /uvx /bin/

# Copy dependency files first (layer cache)
COPY pyproject.toml uv.lock* ./
COPY pulseguard/__init__.py pulseguard/

# Install dependencies
RUN uv sync --no-dev

# Copy full source
COPY . .

# Re-install in case local code was updated
RUN uv sync --no-dev

RUN mkdir -p logs chroma_db

EXPOSE 8000

# Shell form (not exec-array) so $PORT is substituted at container start —
# Railway injects its own PORT; local docker-compose falls back to 8000.
CMD uv run uvicorn pulseguard.gateway.main:app --host 0.0.0.0 --port ${PORT:-8000}
