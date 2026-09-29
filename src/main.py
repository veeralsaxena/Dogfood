from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from src.config import BASE_DIR
from src.database import init_db
from src.routes import web, projects, judging, export, voting, auth_admin, competitions

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title="Veritas — Deterministic Competitive Evaluation Platform",
    description="Enterprise-grade, self-hostable competition management, submission, and judging engine with verifiable Ed25519 cryptographic scoring.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Static Assets (100% offline self-contained)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "src" / "static")), name="static")

# Include Routers
app.include_router(web.router)
app.include_router(projects.router)
app.include_router(projects.team_router)
app.include_router(projects.event_router)
app.include_router(judging.router)
app.include_router(export.router)
app.include_router(voting.router)
app.include_router(auth_admin.router)
app.include_router(competitions.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8080, reload=True)
