from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings

settings = get_settings()
app = FastAPI(title="CargoOne API", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=[settings.web_origin], allow_methods=["*"], allow_headers=["*"]
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
