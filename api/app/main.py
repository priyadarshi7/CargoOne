from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import (
    attention,
    auth,
    billing,
    client_view,
    dashboard,
    documents,
    drivers,
    expenses,
    imports,
    links,
    notifications,
    onboard,
    planning,
    pods,
    requests,
    review,
    setup,
    tracking,
    trips,
)

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
app.include_router(drivers.router)
app.include_router(planning.router)
app.include_router(tracking.router)
app.include_router(expenses.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
app.include_router(setup.router)
app.include_router(attention.router)
app.include_router(documents.router)
app.include_router(notifications.router)
app.include_router(onboard.router)
app.include_router(requests.public)
app.include_router(requests.office)
