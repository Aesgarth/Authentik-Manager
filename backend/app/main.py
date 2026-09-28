import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.database import init_db
from app.worker import worker
from app.routers import auth, matrix, apps, users, invites, audit, health, whatsapp, templates

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    await worker.start()
    yield
    # Shutdown
    await worker.stop()

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Home Services Access Management Tool for Authentik",
    lifespan=lifespan
)

# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
app.include_router(audit.router)
app.include_router(health.router)
app.include_router(whatsapp.router)
app.include_router(templates.router)

# Mount frontend static files if built
frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../frontend/dist"))
if os.path.exists(frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = os.path.join(frontend_dist, full_path)
        if full_path and os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_dist, "index.html"))
