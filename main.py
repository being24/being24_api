from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.internal.ayame_update import ayame_update
from app.routers import change, data, json_download, search, system, tags_metadata


# 3時間ごとにデータベース更新
async def periodic_update():
    print("Start periodic update")
    await ayame_update.update_database()
    print("Update finished")


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(periodic_update, "interval", hours=3, max_instances=1)
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(openapi_tags=tags_metadata.tags_metadata, lifespan=lifespan)
app.include_router(search.router)
app.include_router(data.router)
app.include_router(change.router)
app.include_router(system.router)
app.include_router(json_download.router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# プロキシヘッダー読み取り
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")


@app.get("/")
async def root():
    return {"message": "Hello Bigger Applications!"}
