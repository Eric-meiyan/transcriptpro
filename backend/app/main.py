"""TranscriptPro Backend — FastAPI server (Web service mode)."""

import logging
import sys

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.api.routes import router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


class APISecretMiddleware(BaseHTTPMiddleware):
    """Validate X-API-Secret header on all requests (except /health and /docs)."""

    async def dispatch(self, request: Request, call_next):
        # Skip auth for health check and docs
        if request.url.path in ("/health", "/docs", "/openapi.json"):
            return await call_next(request)

        # If no API_SECRET configured, allow all (dev mode)
        if not settings.api_secret:
            return await call_next(request)

        secret = request.headers.get("X-API-Secret", "")
        if secret != settings.api_secret:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid API secret"},
            )

        return await call_next(request)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title="TranscriptPro",
        description="YouTube AI transcription backend service",
        version="0.2.0",
        docs_url="/docs" if __debug__ else None,
    )

    # API Secret middleware
    app.add_middleware(APISecretMiddleware)

    # CORS — allow Vercel frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API routes
    app.include_router(router, prefix="/api")

    # Health check at root level
    @app.get("/health")
    async def health():
        return {"status": "ok", "version": "0.2.0"}

    @app.on_event("startup")
    async def startup():
        settings.ensure_dirs()
        logger.info(f"TranscriptPro backend started on {settings.host}:{settings.port}")
        logger.info(f"API Secret: {'configured' if settings.api_secret else 'NOT SET (dev mode)'}")
        logger.info(f"Redis: {settings.redis_url}")
        logger.info(f"Whisper model: {settings.default_model}")
        logger.info(f"Proxy: {settings.ytdlp_proxy or 'none'}")

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
