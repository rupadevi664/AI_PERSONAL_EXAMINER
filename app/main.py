import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.database import init_db
from app.routes.exam import router as exam_router
from app.routes.progress import router as progress_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database and tables
    init_db()
    yield


app = FastAPI(
    title="AI Personal Examiner",
    description="An LLM-powered technical examiner that remembers what you know, adapts difficulty, and prevents repetition.",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for local development and web clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(exam_router)
app.include_router(progress_router)

# Locate Frontend directory
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

if os.path.exists(FRONTEND_DIR):
    # Mount frontend directory for CSS and JS assets
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    # Serve HTML views directly
    @app.get("/")
    def serve_index():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

    @app.get("/exam")
    def serve_exam():
        return FileResponse(os.path.join(FRONTEND_DIR, "exam.html"))

    @app.get("/dashboard")
    def serve_dashboard():
        return FileResponse(os.path.join(FRONTEND_DIR, "dashboard.html"))

    @app.get("/result")
    def serve_result():
        return FileResponse(os.path.join(FRONTEND_DIR, "result.html"))


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "AI Personal Examiner"}


# uvicorn app.main:app --reload --port 8000 to run