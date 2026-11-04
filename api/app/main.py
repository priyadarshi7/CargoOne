from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import auth, billing, client_view, dashboard, imports, links, pods, review, trips

settings = get_settings()
app = FastAPI(title="CargoOne API", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=[settings.web_origin], allow_methods=["*"], allow_headers=["*"],
    expose_headers=["Content-Disposition"]  # lets the web app read the download file name
)
app.include_router(auth.router)
app.include_router(trips.router)
app.include_router(pods.router)
app.include_router(review.router)
app.include_router(billing.router)
app.include_router(dashboard.router)
app.include_router(links.router)
app.include_router(imports.router)
app.include_router(client_view.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
