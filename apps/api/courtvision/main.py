from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from courtvision.api import api_router, health, internal_router, websocket_game
from courtvision.broadcast import event_bus
from courtvision.config import settings
from courtvision.rate_limit import RateLimiter

logger = structlog.get_logger()
rate_limiter = RateLimiter(
    general_limit=settings.public_rate_limit_requests,
    shot_quality_limit=settings.shot_quality_rate_limit_requests,
    window_seconds=settings.rate_limit_window_seconds,
)
BASE_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "accelerometer=(), camera=(), geolocation=(), microphone=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}
HSTS_HEADER = "max-age=63072000; includeSubDomains; preload"
RATE_LIMIT_HEADERS = [
    "X-RateLimit-Limit",
    "X-RateLimit-Remaining",
    "X-RateLimit-Reset",
    "Retry-After",
]


def security_headers() -> dict[str, str]:
    headers = dict(BASE_SECURITY_HEADERS)
    if settings.environment == "production":
        headers["Strict-Transport-Security"] = HSTS_HEADER
    return headers


def response_headers() -> dict[str, str]:
    headers = security_headers()
    headers["Cache-Control"] = "no-store"
    return headers


@asynccontextmanager
async def lifespan(app: FastAPI):
    await event_bus.start(subscribe=True)
    logger.info("courtvision_started", environment=settings.environment)
    try:
        yield
    finally:
        await event_bus.stop()


app = FastAPI(
    title="CourtVision AI API",
    version="1.0.0",
    description=(
        "Replay-first basketball analytics. Public demo data is synthetic or curated and "
        "must not be represented as a licensed real-time feed."
    ),
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
    expose_headers=RATE_LIMIT_HEADERS,
)


@app.middleware("http")
async def enforce_public_rate_limit(request: Request, call_next):
    if request.method == "OPTIONS" or not request.url.path.startswith("/api/v1/"):
        return await call_next(request)

    forwarded_for = request.headers.get("x-forwarded-for")
    if settings.trust_proxy_headers and forwarded_for:
        client_identifier = forwarded_for.split(",", 1)[0].strip()
    else:
        client_identifier = request.client.host if request.client else "unknown"

    bucket_name = (
        "shot-quality"
        if request.url.path == "/api/v1/shot-quality"
        else "public-read"
    )
    decision = await rate_limiter.check(
        client_identifier=client_identifier,
        bucket_name=bucket_name,
        redis=event_bus.redis,
    )
    headers = {
        "X-RateLimit-Limit": str(decision.limit),
        "X-RateLimit-Remaining": str(decision.remaining),
        "X-RateLimit-Reset": str(decision.reset_epoch_seconds),
        "Retry-After": str(decision.retry_after_seconds),
    }
    if not decision.allowed:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers=headers,
        )

    response = await call_next(request)
    response.headers.update(headers)
    return response


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.update(response_headers())
    return response


app.include_router(api_router)
app.include_router(internal_router)
app.add_api_route("/health", health, methods=["GET"], tags=["operations"])


@app.websocket("/ws/v1/games/{game_id}")
async def game_websocket(websocket: WebSocket, game_id: str, after_sequence: int = -1) -> None:
    await websocket_game(websocket, game_id, after_sequence)
