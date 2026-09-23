import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import applications, auth, dashboards, risks

app = FastAPI(
    title="MAHACLEAR-AI API",
    description="Faster, Smarter Industrial Approvals",
    version="0.1.0",
)

frontend_origins = os.getenv("FRONTEND_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in frontend_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(dashboards.router, prefix="/api")
app.include_router(applications.router, prefix="/api")
app.include_router(risks.router, prefix="/api")


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Report that the API process is running."""
    return {"status": "ok", "service": "mahaclear-ai-api"}


app.add_api_route("/api/health", health, methods=["GET"], tags=["health"])
