"""TranscriptPro Backend — FastAPI server."""

import logging
import sys

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.routes import router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title="TranscriptPro",
        description="YouTube long video transcription backend",
        version="0.1.0",
        docs_url="/docs" if __debug__ else None,
    )

    # CORS — allow Tauri frontend (localhost)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Tauri uses custom protocol
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API routes
    app.include_router(router, prefix="/api")

    @app.on_event("startup")
    async def startup():
        settings.ensure_dirs()
        logger.info(f"TranscriptPro backend started on {settings.host}:{settings.port}")
        logger.info(f"Data directory: {settings.app_data_dir}")

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
