from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()  # Load .env into os.environ before any SDK clients are instantiated

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.responses import Response

from pulseguard.gateway.dashboard import router as dashboard_router
from pulseguard.gateway.routes import router
from pulseguard.logging_config import configure_logging, get_logger
from pulseguard.redis_client import close_redis

configure_logging()
logger = get_logger(__name__)

limiter = Limiter(key_func=get_remote_address)


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
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(dashboard_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "pulseguard-ai"}


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
