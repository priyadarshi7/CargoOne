import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.ai.registry import warm_up
from app.config import get_settings
from app.routers import (
    attention,
    auth,
    billing,
    client_view,
    dashboard,
    devtools,
    documents,
    drivers,
    expenses,
    home,
    imports,
    journey,
    links,
    notifications,
    onboard,
    places,
    planning,
    pods,
    portal,
    push,
    requests,
    review,
    setup,
    shipments,
    tracking,
    trips,
    webhooks,
)

settings = get_settings()
@asynccontextmanager
async def lifespan(_: FastAPI):
    if "local" in {settings.ai_provider, *settings.ai_fallbacks.split(",")}:
        warming = asyncio.create_task(warm_up())  # in the background: the API answers at once, the first photo is quicker
        warming.add_done_callback(lambda t: t.exception())
    yield


app = FastAPI(title="CargoOne API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=[settings.web_origin], allow_methods=["*"], allow_headers=["*"],
    expose_headers=["Content-Disposition"]  # lets the web app read the download file name
)
app.include_router(auth.router)
app.include_router(trips.router)
app.include_router(journey.router)
app.include_router(portal.router)
app.include_router(shipments.public)
app.include_router(shipments.office)
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
app.include_router(home.router)
app.include_router(documents.router)
app.include_router(devtools.router)
app.include_router(notifications.router)
app.include_router(places.router)
app.include_router(push.router)
app.include_router(onboard.router)
app.include_router(requests.public)
app.include_router(requests.office)
app.include_router(webhooks.router)
