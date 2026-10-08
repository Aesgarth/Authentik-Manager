import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
# Suppress noisy HTTP client polling logs that leak query parameters
logging.getLogger("httpx").setLevel(logging.WARNING)

from app.database import init_db
from app.worker import worker
from app.services.settings_service import settings_service
from app.routers import auth, matrix, apps, users, invites, audit, health, whatsapp, templates, settings as settings_router, webhooks

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    await settings_service.load_settings_into_runtime()
    await worker.start()
    yield
    # Shutdown
    await worker.stop()
    from app.services.telegram_service import telegram_service
    await telegram_service.stop_polling()

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Home Services Access Management Tool for Authentik",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEMO_MODE else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.DEMO_MODE else None
)

# Security Headers Middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response

# CORS configuration: only allow explicitly configured origins
cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
if not cors_origins and settings.DEMO_MODE:
    cors_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]

if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Include API Routers
app.include_router(auth.router)
app.include_router(matrix.router)
app.include_router(apps.router)
app.include_router(users.router)
app.include_router(invites.router)
app.include_router(webhooks.router)
app.include_router(audit.router)
app.include_router(health.router)
app.include_router(whatsapp.router)
app.include_router(templates.router)
app.include_router(settings_router.router)

# Mount frontend static files if built
frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../frontend/dist"))
if os.path.exists(frontend_dist):
    dist = os.path.realpath(frontend_dist)
    app.mount("/assets", StaticFiles(directory=os.path.join(dist, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        candidate = os.path.realpath(os.path.join(dist, full_path))
        # Ensure path stays strictly within dist folder to prevent directory traversal
        if full_path and os.path.commonpath([dist, candidate]) == dist and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(dist, "index.html"))
