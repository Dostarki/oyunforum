"""Admin auth/CORS/session regression tests for wildcard-origin synchronizer-token contract."""

import os
import sys
from pathlib import Path

import pytest
import requests
import jwt
from dotenv import load_dotenv
from pymongo import MongoClient


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
load_dotenv(ROOT / 'frontend' / '.env')
load_dotenv(ROOT / 'backend' / '.env')

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
MONGO_URL = os.environ.get('MONGO_URL')
DB_NAME = os.environ.get('DB_NAME')
ADMIN_PASSWORD = os.environ['ADMIN_PASSWORD']
ROOT_ORIGIN = os.environ['PUBLIC_APP_URL'].rstrip('/')
from urllib.parse import urlsplit, urlunsplit
root_parts = urlsplit(ROOT_ORIGIN)
WWW_ORIGIN = urlunsplit((root_parts.scheme, 'www.' + root_parts.netloc, '', '', ''))
ARBITRARY_ORIGIN = 'https://example.org'


def admin_headers(origin=None, csrf=None):
    headers = {
        'Content-Type': 'application/json',
        'X-Admin-Client': 'lastzhood-admin',
    }
    if origin is not None:
        headers['Origin'] = origin
    if csrf is not None:
        headers['X-CSRF-Token'] = csrf
    return headers


@pytest.fixture(scope='session')
def mongo_db():
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    yield db
    client.close()


@pytest.fixture
def anon_client():
    return requests.Session()


@pytest.fixture
def admin_session():
    session = requests.Session()
    response = session.post(
        f'{BASE_URL}/api/admin/login',
        json={'password': ADMIN_PASSWORD},
        headers=admin_headers(ROOT_ORIGIN),
        timeout=20,
    )
    assert response.status_code == 200, f'Admin login failed: {response.status_code} {response.text}'
    body = response.json()
    assert body.get('authenticated') is True
    assert isinstance(body.get('csrf_token'), str) and len(body['csrf_token']) > 10
    return session, body['csrf_token']


# Module: CORS and login contract
def test_admin_password_hash_is_bcrypt_2b(mongo_db):
    admin = mongo_db.admin_users.find_one({'_id': 'admin'})
    assert admin is not None
    assert isinstance(admin.get('password_hash'), str)
    assert admin['password_hash'].startswith('$2b$')


def test_login_requires_admin_header_and_json_content_type(anon_client):
    missing_header = anon_client.post(
        f'{BASE_URL}/api/admin/login',
        json={'password': ADMIN_PASSWORD},
        headers={'Content-Type': 'application/json', 'Origin': ROOT_ORIGIN},
        timeout=20,
    )
    non_json = anon_client.post(
        f'{BASE_URL}/api/admin/login',
        data={'password': ADMIN_PASSWORD},
        headers={'Content-Type': 'application/x-www-form-urlencoded', 'X-Admin-Client': 'lastzhood-admin', 'Origin': ROOT_ORIGIN},
        timeout=20,
    )
    assert missing_header.status_code == 400
    assert non_json.status_code == 400


def test_login_accepts_root_www_arbitrary_and_missing_origin(anon_client):
    responses = [
        anon_client.post(f'{BASE_URL}/api/admin/login', json={'password': ADMIN_PASSWORD}, headers=admin_headers(ROOT_ORIGIN), timeout=20),
        anon_client.post(f'{BASE_URL}/api/admin/login', json={'password': ADMIN_PASSWORD}, headers=admin_headers(WWW_ORIGIN), timeout=20),
        anon_client.post(f'{BASE_URL}/api/admin/login', json={'password': ADMIN_PASSWORD}, headers=admin_headers(ARBITRARY_ORIGIN), timeout=20),
        anon_client.post(f'{BASE_URL}/api/admin/login', json={'password': ADMIN_PASSWORD}, headers=admin_headers(), timeout=20),
    ]
    for response in responses:
        assert response.status_code == 200
        payload = response.json()
        assert payload.get('authenticated') is True
        assert isinstance(payload.get('csrf_token'), str)

    cookie_header = responses[0].headers.get('set-cookie', '').lower()
    assert 'access_token=' in cookie_header
    assert 'refresh_token=' in cookie_header
    assert 'httponly' in cookie_header
    assert 'secure' in cookie_header
    assert 'path=/api/admin' in cookie_header


@pytest.mark.parametrize('origin', [ROOT_ORIGIN, WWW_ORIGIN, ARBITRARY_ORIGIN])
def test_preflight_reflects_origin_and_allows_required_headers(origin):
    preflight = requests.options(
        f'{BASE_URL}/api/admin/login',
        headers={
            'Origin': origin,
            'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'content-type,x-admin-client,x-csrf-token',
        },
        timeout=20,
    )
    assert preflight.status_code in (200, 204)
    assert preflight.headers.get('access-control-allow-origin') == origin
    assert preflight.headers.get('access-control-allow-credentials') == 'true'
    allow_headers = preflight.headers.get('access-control-allow-headers', '').lower()
    assert 'content-type' in allow_headers
    assert 'x-admin-client' in allow_headers
    assert 'x-csrf-token' in allow_headers


def test_origin_null_not_cors_allowed():
    preflight = requests.options(
        f'{BASE_URL}/api/admin/login',
        headers={
            'Origin': 'null',
            'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'content-type,x-admin-client',
        },
        timeout=20,
    )
    assert preflight.status_code == 400
    assert preflight.headers.get('access-control-allow-origin') is None


def test_wrong_password_401_and_throttle_6th_429_then_cleanup(anon_client, mongo_db):
    attempt_ids_before = {doc['_id'] for doc in mongo_db.admin_login_attempts.find({}, {'_id': 1})}
    try:
        statuses = []
        for _ in range(6):
            response = anon_client.post(
                f'{BASE_URL}/api/admin/login',
                json={'password': 'WrongPassword!'},
                headers=admin_headers(ROOT_ORIGIN),
                timeout=20,
            )
            statuses.append(response.status_code)
        assert statuses[:5] == [401, 401, 401, 401, 401]
        assert statuses[5] == 429
    finally:
        attempt_ids_after = {doc['_id'] for doc in mongo_db.admin_login_attempts.find({}, {'_id': 1})}
        created_ids = list(attempt_ids_after - attempt_ids_before)
        if created_ids:
            mongo_db.admin_login_attempts.delete_many({'_id': {'$in': created_ids}})


# Module: proof + cookie requirements and session revocation
def test_cookie_only_requests_fail_without_csrf_proof(admin_session):
    session, _ = admin_session
    no_proof_me = session.get(f'{BASE_URL}/api/admin/me', headers={'Origin': ROOT_ORIGIN}, timeout=20)
    no_proof_settings = session.get(f'{BASE_URL}/api/admin/settings', headers={'Origin': ROOT_ORIGIN}, timeout=20)
    no_proof_refresh = session.post(f'{BASE_URL}/api/admin/refresh', headers={'Origin': ROOT_ORIGIN}, timeout=20)
    no_proof_logout = session.post(f'{BASE_URL}/api/admin/logout', headers={'Origin': ROOT_ORIGIN}, timeout=20)
    assert no_proof_me.status_code == 401
    assert no_proof_settings.status_code == 401
    assert no_proof_refresh.status_code == 401
    assert no_proof_logout.status_code == 401


def test_wrong_csrf_proof_rejected_with_403(admin_session):
    session, _ = admin_session
    wrong = session.get(
        f'{BASE_URL}/api/admin/me',
        headers={'Origin': ROOT_ORIGIN, 'X-CSRF-Token': 'wrong-proof-token'},
        timeout=20,
    )
    assert wrong.status_code == 403


def test_protected_calls_succeed_with_cookie_plus_proof_and_origin_can_change(admin_session):
    session, proof = admin_session
    ok_me = session.get(
        f'{BASE_URL}/api/admin/me',
        headers={'Origin': ROOT_ORIGIN, 'X-CSRF-Token': proof},
        timeout=20,
    )
    assert ok_me.status_code == 200
    assert ok_me.json() == {'authenticated': True}

    settings = session.get(
        f'{BASE_URL}/api/admin/settings',
        headers={'Origin': ROOT_ORIGIN, 'X-CSRF-Token': proof},
        timeout=20,
    )
    assert settings.status_code == 200
    body = settings.json()
    assert 'settings' in body and 'revision' in body

    same_values_put = session.put(
        f'{BASE_URL}/api/admin/settings',
        json={**body['settings'], 'revision': body['revision']},
        headers={'Origin': ARBITRARY_ORIGIN, 'X-CSRF-Token': proof},
        timeout=20,
    )
    assert same_values_put.status_code == 200

    cross_origin_get = session.get(
        f'{BASE_URL}/api/admin/me',
        headers={'Origin': WWW_ORIGIN, 'X-CSRF-Token': proof},
        timeout=20,
    )
    assert cross_origin_get.status_code == 200


def test_logout_revokes_server_session_and_replayed_cookie_plus_proof_fails(admin_session):
    session, proof = admin_session
    pre_logout_me = session.get(
        f'{BASE_URL}/api/admin/me',
        headers={'Origin': ROOT_ORIGIN, 'X-CSRF-Token': proof},
        timeout=20,
    )
    assert pre_logout_me.status_code == 200

    cookie_snapshot = requests.cookies.RequestsCookieJar()
    for cookie in session.cookies:
        cookie_snapshot.set_cookie(cookie)

    logout = session.post(
        f'{BASE_URL}/api/admin/logout',
        headers={'Origin': ROOT_ORIGIN, 'X-CSRF-Token': proof},
        timeout=20,
    )
    assert logout.status_code == 200
    assert logout.json() == {'authenticated': False}

    replay = requests.Session()
    replay.cookies = cookie_snapshot
    replay_me = replay.get(
        f'{BASE_URL}/api/admin/me',
        headers={'Origin': ROOT_ORIGIN, 'X-CSRF-Token': proof},
        timeout=20,
    )
    assert replay_me.status_code == 401


def test_legacy_session_without_csrf_hash_is_invalid(admin_session, mongo_db):
    session, proof = admin_session
    refresh_cookie = session.cookies.get('refresh_token')
    assert isinstance(refresh_cookie, str) and len(refresh_cookie) > 20

    # Force legacy-like document by removing hash from live server session.
    auth_ok = session.get(
        f'{BASE_URL}/api/admin/me',
        headers={'Origin': ROOT_ORIGIN, 'X-CSRF-Token': proof},
        timeout=20,
    )
    assert auth_ok.status_code == 200

    access_payload = requests.get(
        f'{BASE_URL}/api/admin/me',
        headers={'Origin': ROOT_ORIGIN, 'X-CSRF-Token': proof},
        cookies=session.cookies,
        timeout=20,
    )
    assert access_payload.status_code == 200

    # Only touch this test's own session, never the newest administrator session.
    claims = jwt.decode(refresh_cookie, os.environ['JWT_SECRET'], algorithms=['HS256'])
    session_doc = mongo_db.admin_sessions.find_one({'session_id': claims['sid']})
    assert session_doc is not None
    mongo_db.admin_sessions.update_one({'_id': session_doc['_id']}, {'$unset': {'csrf_hash': ''}})

    legacy_fail = session.get(
        f'{BASE_URL}/api/admin/me',
        headers={'Origin': ROOT_ORIGIN, 'X-CSRF-Token': proof},
        timeout=20,
    )
    assert legacy_fail.status_code == 401


def test_no_sensitive_leaks_from_me_settings_config_refresh_logout(admin_session):
    session, proof = admin_session

    me = session.get(f'{BASE_URL}/api/admin/me', headers={'Origin': ROOT_ORIGIN, 'X-CSRF-Token': proof}, timeout=20)
    settings = session.get(f'{BASE_URL}/api/admin/settings', headers={'Origin': ROOT_ORIGIN, 'X-CSRF-Token': proof}, timeout=20)
    refresh = session.post(f'{BASE_URL}/api/admin/refresh', headers={'Origin': ROOT_ORIGIN, 'X-CSRF-Token': proof}, timeout=20)
    config = session.get(f'{BASE_URL}/api/config', timeout=20)
    logout = session.post(f'{BASE_URL}/api/admin/logout', headers={'Origin': ROOT_ORIGIN, 'X-CSRF-Token': proof}, timeout=20)

    assert me.status_code == 200
    assert settings.status_code == 200
    assert refresh.status_code == 200
    assert config.status_code == 200
    assert logout.status_code == 200

    combined = '\n'.join([me.text, settings.text, refresh.text, config.text, logout.text]).lower()
    for forbidden in ('password_hash', 'csrf_hash', 'jwt_secret', 'mongo_url', 'csrf_token'):
        assert forbidden not in combined
