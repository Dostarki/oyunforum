"""Public X-avatar API tests: live smoke checks + local unit guards for safety/rate-limit/cache behavior."""

import asyncio
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
from dotenv import load_dotenv
from PIL import Image
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
load_dotenv(ROOT / 'frontend' / '.env')
load_dotenv(ROOT / 'backend' / '.env')

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
MONGO_URL = os.environ.get('MONGO_URL')
DB_NAME = os.environ.get('DB_NAME')


@pytest.fixture(scope='session')
def api_client():
    session = requests.Session()
    session.headers.update({'Content-Type': 'application/json'})
    return session


@pytest.fixture(scope='session')
def mongo_db():
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    yield db
    client.close()


# Module: live provider smoke checks through public backend endpoints
def test_nasa_profile_available_and_normalization_consistent(api_client, mongo_db):
    first = api_client.get(f'{BASE_URL}/api/x/profile/NASA', timeout=20)
    second = api_client.get(f'{BASE_URL}/api/x/profile/%40NASA', timeout=20)

    assert first.status_code == 200
    assert second.status_code == 200

    p1 = first.json()
    p2 = second.json()

    assert p1['handle'] == 'nasa'
    assert p2['handle'] == 'nasa'
    assert p1['status'] == 'available'
    assert p2['status'] == 'available'
    assert p1['ownership_verified'] is False
    assert p2['ownership_verified'] is False
    assert p1['source'] == 'fxtwitter'
    assert p2['source'] == 'fxtwitter'
    assert p1['avatar_path'] == '/api/x/avatar/nasa'
    assert p2['avatar_path'] == '/api/x/avatar/nasa'

    doc = mongo_db.x_avatar_metadata.find_one({'handle': 'nasa'})
    assert doc is not None
    assert set(doc.keys()).issubset({'_id', 'handle', 'avatar_url', 'source', 'expires_at'})
    assert isinstance(doc.get('expires_at'), datetime)


def test_nasa_avatar_proxy_headers_and_png_dimensions(api_client):
    response = api_client.get(f'{BASE_URL}/api/x/avatar/NASA', timeout=20)
    assert response.status_code == 200
    assert response.headers.get('content-type') == 'image/png'
    assert response.headers.get('x-content-type-options') == 'nosniff'
    assert response.headers.get('access-control-allow-origin') == '*'
    # The public edge can enforce no-store, even though the origin offers max-age.
    # The provider-protection contract is actual server caching, not CDN storage.
    policy = response.headers.get('cache-control', '')
    assert 'max-age=3600' in policy or 'no-store' in policy
    assert response.headers.get('x-avatar-cache') in {'HIT', 'MISS'}
    repeated = api_client.get(f'{BASE_URL}/api/x/avatar/NASA', timeout=20)
    assert repeated.status_code == 200
    assert repeated.headers.get('x-avatar-cache') == 'HIT'
    assert repeated.content == response.content

    image = Image.open(io.BytesIO(response.content))
    assert image.format == 'PNG'
    assert image.size == (400, 400)


def test_lastzhood_avatar_state_and_missing_account_fallback(api_client):
    # Live account: response shape stays valid whether or not a custom photo exists.
    response = api_client.get(f'{BASE_URL}/api/x/profile/LastZhood', timeout=20)
    assert response.status_code == 200
    data = response.json()
    assert data['handle'] == 'lastzhood'
    assert data['status'] in ('available', 'unavailable')
    assert data['ownership_verified'] is False
    if data['status'] == 'available':
        assert data['avatar_path'] == '/api/x/avatar/lastzhood'
        assert data['source'] == 'fxtwitter'
    else:
        assert data['avatar_path'] is None
        assert data['source'] is None

    # A handle that cannot exist still falls back to unavailable.
    missing = api_client.get(f'{BASE_URL}/api/x/profile/zz_noacct_99x', timeout=20)
    assert missing.status_code == 200
    unavailable = missing.json()
    assert unavailable['status'] == 'unavailable'
    assert unavailable['avatar_path'] is None
    assert unavailable['source'] is None
    assert unavailable['ownership_verified'] is False


def test_invalid_handle_rejected_on_profile_and_avatar(api_client):
    profile = api_client.get(f'{BASE_URL}/api/x/profile/bad-handle!', timeout=20)
    avatar = api_client.get(f'{BASE_URL}/api/x/avatar/bad-handle!', timeout=20)
    assert profile.status_code == 422
    assert avatar.status_code == 422


# Module: local unit checks (no live-provider flooding)
def test_rate_limiter_returns_429_without_flooding(monkeypatch):
    import x_avatar as xa

    xa._requests.clear()
    monkeypatch.setattr(xa, 'RATE_LIMIT', 1)
    request = SimpleNamespace(client=SimpleNamespace(host='test-host'))

    xa.check_rate(request)
    with pytest.raises(Exception) as exc_info:
        xa.check_rate(request)
    assert getattr(exc_info.value, 'status_code', None) == 429


def test_safe_avatar_url_blocks_malicious_or_non_cdn_urls():
    import avatar_provider as ap

    assert ap.safe_avatar_url('https://pbs.twimg.com/profile_images/demo_normal.jpg') is not None
    assert ap.safe_avatar_url('http://pbs.twimg.com/profile_images/demo.jpg') is None
    assert ap.safe_avatar_url('https://evil.example.com/profile_images/demo.jpg') is None
    assert ap.safe_avatar_url('https://pbs.twimg.com/profile_images/demo.jpg?x=1') is None


def test_negative_cache_write_is_tz_aware_and_minimal(monkeypatch):
    import avatar_provider as ap

    class FakeCollection:
        def __init__(self):
            self.find_projection = None
            self.update_query = None
            self.update_doc = None

        async def find_one(self, query, projection):
            self.find_projection = projection
            return None

        async def update_one(self, query, update, upsert=False):
            self.update_query = query
            self.update_doc = update['$set']

    class FakeDB:
        def __init__(self):
            self.x_avatar_metadata = FakeCollection()

    async def fake_limited_body(client, url, limit, accept):
        payload = {'code': 200, 'user': {'protected': True, 'screen_name': 'nasa', 'avatar_url': 'https://pbs.twimg.com/profile_images/demo.jpg'}}
        return json.dumps(payload).encode('utf-8'), 'application/json'

    db = FakeDB()
    monkeypatch.setattr(ap, 'limited_body', fake_limited_body)

    result = asyncio.run(ap._resolve('nasa', db, client=None))
    assert result is None
    assert db.x_avatar_metadata.find_projection == {'_id': 0}
    assert db.x_avatar_metadata.update_query == {'handle': 'nasa'}

    written = db.x_avatar_metadata.update_doc
    assert set(written.keys()) == {'handle', 'avatar_url', 'source', 'expires_at'}
    assert written['handle'] == 'nasa'
    assert written['avatar_url'] is None
    assert written['source'] is None
    assert written['expires_at'].tzinfo is timezone.utc
    assert written['expires_at'] > datetime.now(timezone.utc)