FROM python:3.12-slim

# ARM64 / amd64 universal image
ARG TARGETPLATFORM
RUN echo "Building for $TARGETPLATFORM"

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.4 /uv /uvx /bin/

# Copy dependency files first (layer cache). README.md is required too —
# pyproject.toml points hatchling's build backend at it, and `uv sync`
# fails validation without it even before the rest of the source lands.
COPY pyproject.toml uv.lock* README.md ./
COPY pulseguard/__init__.py pulseguard/

# Install dependencies
RUN uv sync --no-dev

# Copy full source
COPY . .

# Re-install in case local code was updated
RUN uv sync --no-dev

RUN mkdir -p logs chroma_db

# Don't run the process as root — a container escape or dependency RCE
# would otherwise hand an attacker root inside the image for free.
RUN useradd --create-home --uid 1000 pulseguard \
    && chown -R pulseguard:pulseguard /app
USER pulseguard

EXPOSE 8000

# Shell form (not exec-array) so $PORT is substituted at container start —
# the host (Render, etc.) injects its own PORT; local docker-compose,
# which doesn't set one, falls back to 8000.
CMD uv run uvicorn pulseguard.gateway.main:app --host 0.0.0.0 --port ${PORT:-8000}
