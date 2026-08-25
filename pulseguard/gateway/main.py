from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv

load_dotenv()  # Load .env into os.environ before any SDK clients are instantiated

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.responses import Response

from pulseguard.config import settings
from pulseguard.gateway.dashboard import router as dashboard_router
from pulseguard.gateway.limiter import limiter
from pulseguard.gateway.routes import router
from pulseguard.logging_config import configure_logging, get_logger
from pulseguard.redis_client import close_redis

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("pulseguard_gateway_starting")
    from pulseguard.orchestrator.graph import orchestrator

    await orchestrator.start()
    yield
    logger.info("pulseguard_gateway_stopping")
    await orchestrator.stop()
    await close_redis()


app = FastAPI(
    title="PulseGuard AI",
    description="Autonomous social feed triage system for telecom CX",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

app.add_middleware(
    CORSMiddleware,
    # No browser is meant to call this API directly — the frontend's
    # server-side proxy holds the API key and isn't subject to CORS at all.
    # This only matters as defense-in-depth against a browser context that
    # somehow obtained a key; keep it scoped to known frontend origins
    # instead of "*".
    allow_origins=settings.allowed_origins_list,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(dashboard_router)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "pulseguard-ai"}


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
