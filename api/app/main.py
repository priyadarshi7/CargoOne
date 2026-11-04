from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import auth, trips

settings = get_settings()
app = FastAPI(title="CargoOne API", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=[settings.web_origin], allow_methods=["*"], allow_headers=["*"]
)
app.include_router(auth.router)
app.include_router(trips.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
