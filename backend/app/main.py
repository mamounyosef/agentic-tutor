"""Agentic Tutor FastAPI application."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .core.config import settings
from .observability.langsmith import initialize_langsmith
from .api import auth, constructor, tutor
from .db.constructor.compat import ensure_constructor_schema_compatibility


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context for startup and shutdown events."""
    # Startup
    print(f"{settings.APP_NAME} starting up...")
    initialize_langsmith(settings)
    try:
        await ensure_constructor_schema_compatibility()
    except Exception as exc:  # pragma: no cover - fail-open for local startup
        print(f"WARNING: constructor DB compatibility migration skipped: {exc}")
    yield
    # Shutdown
    print(f"{settings.APP_NAME} shutting down...")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.APP_NAME,
        description="Agent-based learning system with adaptive AI tutors",
        version="0.1.0",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    # CORS middleware
    cors_origins = settings.cors_origins_list
    cors_headers = settings.cors_allow_headers_list
    print(f"DEBUG: CORS origins: {cors_origins}")
    print(f"DEBUG: CORS headers: {cors_headers}")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=["*"],
        allow_headers=cors_headers,
    )

    # Include routers
    app.include_router(auth.router, prefix=settings.API_V1_PREFIX, tags=["Authentication"])
    app.include_router(constructor.router, prefix=settings.API_V1_PREFIX, tags=["Constructor"])
    app.include_router(tutor.router, prefix=settings.API_V1_PREFIX, tags=["Tutor"])

    # Health check
    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "app": settings.APP_NAME}

    # Root endpoint
    @app.get("/")
    async def root():
        return {
            "app": settings.APP_NAME,
            "version": "0.1.0",
            "docs": "/docs",
            "health": "/health"
        }

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "error": str(exc) if settings.DEBUG else "An error occurred"
            }
        )

    return app


# Create the app instance
app = create_app()
