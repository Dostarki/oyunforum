import logging
import os
import httpx
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(Path(__file__).parent / '.env')
from registry import router
from settings import public_config
from campaign import seed_campaign, get_campaign
from admin import router as admin_router
from admin_security import seed_admin
from x_avatar import router as x_avatar_router
from avatar_provider import TIMEOUT, UA

logging.basicConfig(level=logging.INFO)
client = AsyncIOMotorClient(os.environ['MONGO_URL'])
db = client[os.environ['DB_NAME']]


@asynccontextmanager
async def lifespan(app):
    await seed_campaign(db)
    public_config((await get_campaign(db)).settings)
    await seed_admin(db)
    await db.agents.create_index('handle_key', unique=True)
    await db.agents.create_index('ref_code', unique=True)
    await db.agents.create_index('request_id', unique=True)
    await db.agents.create_index('created_at')
    await db.counters.create_index('name', unique=True)
    await db.counters.update_one({'name': 'agent_number'}, {'$setOnInsert': {'value': 0}}, upsert=True)
    app.state.db = db
    await db.x_avatar_metadata.create_index('handle', unique=True)
    await db.x_avatar_metadata.create_index('expires_at', expireAfterSeconds=0)
    app.state.x_http = httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False, headers={'User-Agent': UA})
    yield
    await app.state.x_http.aclose()
    client.close()


app = FastAPI(title='LastZhood Survivor Registry', lifespan=lifespan)
cors_origins = [origin.strip().rstrip('/') for origin in os.environ['CORS_ORIGINS'].split(',')]
# Reflect concrete HTTP(S) origins when wildcard mode is configured. Sending
# ACAO '*' with credentials would still block cookie login in browsers.
cors_any_origin = '*' in cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[] if cors_any_origin else cors_origins,
    allow_origin_regex=r'^https?://[^/\s]+$' if cors_any_origin else None,
    allow_credentials=True,
    allow_methods=['GET', 'POST', 'PUT'],
    allow_headers=['Content-Type', 'X-Admin-Client', 'X-CSRF-Token'],
)
app.include_router(router, prefix='/api')
app.include_router(x_avatar_router, prefix='/api')
app.include_router(admin_router, prefix='/api')


@app.middleware('http')
async def private_settings_cache(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith('/api/admin') or request.url.path == '/api/config':
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.get('/api/')
async def root():
    return {'service': 'LastZhood Survivor Registry', 'status': 'online'}