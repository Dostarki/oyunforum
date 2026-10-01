"""Core public registry API tests: config, stats/recent, participation, validation, idempotency."""

import os
import uuid
from urllib.parse import parse_qs, urlparse

import pytest
import requests
from pymongo import MongoClient


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")


@pytest.fixture(scope="session")
def api_client():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="session")
def mongo_db():
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    yield db
    client.close()


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_data(mongo_db):
    # Clean old data before and after to keep public counts honest.
    mongo_db.agents.delete_many({"handle_key": {"$regex": r"^test_"}})
    yield
    mongo_db.agents.delete_many({"handle_key": {"$regex": r"^test_"}})


def make_payload(handle: str, request_id: str | None = None, referred_by=None):
    return {
        "request_id": request_id or str(uuid.uuid4()),
        "handle": handle,
        "wallet": "0x1111111111111111111111111111111111111111",
        "completed_tasks": ["follow", "like", "repost", "comment"],
        "consent": True,
        "referred_by": referred_by,
    }


# Module: public configuration and read APIs
def test_config_returns_allowlisted_public_fields(api_client, mongo_db):
    response = api_client.get(f"{BASE_URL}/api/config")
    assert response.status_code == 200
    data = response.json()

    assert set(data.keys()) == {"tasks", "share_text", "share_url", "public_url", "verification", "x_profile_url", "comment_message"}
    assert data["verification"] == "self_declared"
    assert len(data["tasks"]) == 4

    task_ids = {task["id"] for task in data["tasks"]}
    assert task_ids == {"follow", "like", "repost", "comment"}

    like_task = next(task for task in data["tasks"] if task["id"] == "like")
    repost_task = next(task for task in data["tasks"] if task["id"] == "repost")
    # Each editable field is sourced exclusively from the saved admin campaign.
    saved = mongo_db.campaign_settings.find_one({'_id': 'x-campaign'})['settings']
    assert like_task['url'] == saved['like_url']
    assert repost_task['url'] == saved['repost_url']

    comment_task = next(task for task in data["tasks"] if task["id"] == "comment")
    parsed = urlparse(comment_task["url"])
    query = parse_qs(parsed.query)
    # VOICE/Reply has its own admin-controlled text and link.
    assert '/intent/post' in parsed.path
    assert query["text"][0] == data["comment_message"]
    assert query["url"][0] == saved['reply_url']
    assert data['comment_message'] == saved['reply_text']
    assert data['share_text'] == saved['claim_text']
    assert len(data['comment_message']) > 0
    assert data['x_profile_url'] == 'https://x.com/LastZhood'

    # POST ON X composer carries the share text with the like link below it;
    # the referral link is appended by the frontend as the url param.
    share_parsed = urlparse(data["share_url"])
    share_query = parse_qs(share_parsed.query)
    assert '/intent/post' in share_parsed.path
    assert share_query["text"][0] == f'{data["share_text"]}\n\n{like_task["url"]}'
    assert "url" not in share_query

    response_text = response.text.lower()
    assert "mongo_url" not in response_text
    assert "db_name" not in response_text
    assert "cors_origins" not in response_text


def test_unknown_public_agent_returns_404(api_client):
    unknown_ref = f"{uuid.uuid4().hex[:8].upper()}"
    response = api_client.get(f"{BASE_URL}/api/agents/{unknown_ref}")
    assert response.status_code == 404
    assert "detail" in response.json()


# Module: participation create/persistence/privacy/idempotency
def test_participation_persists_but_returns_public_fields_only(api_client, mongo_db):
    handle = f"test_{uuid.uuid4().hex[:6]}"[:15]
    payload = make_payload(handle=handle)

    create_response = api_client.post(f"{BASE_URL}/api/participations", json=payload)
    assert create_response.status_code == 201
    created = create_response.json()

    assert created["handle"].lower() == handle.lower()
    assert isinstance(created["number"], int)
    assert len(created["ref_code"]) == 8
    assert created["verification"] == "self_declared"

    for private_key in ["wallet", "_id", "request_id", "consent", "completed_tasks", "referred_by", "handle_key"]:
        assert private_key not in created

    persisted = mongo_db.agents.find_one({"handle_key": handle.lower()})
    assert persisted is not None
    assert persisted["wallet"] == payload["wallet"]
    assert persisted["request_id"] == payload["request_id"]
    assert persisted["consent"] is True
    assert set(persisted["completed_tasks"]) == {"follow", "like", "repost", "comment"}


def test_request_id_is_idempotent_no_extra_record(api_client):
    handle = f"test_{uuid.uuid4().hex[:6]}"[:15]
    req_id = str(uuid.uuid4())
    payload = make_payload(handle=handle, request_id=req_id)

    before = api_client.get(f"{BASE_URL}/api/agents/stats").json()["count"]
    first = api_client.post(f"{BASE_URL}/api/participations", json=payload)
    second = api_client.post(f"{BASE_URL}/api/participations", json=payload)
    after = api_client.get(f"{BASE_URL}/api/agents/stats").json()["count"]

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["ref_code"] == first.json()["ref_code"]
    assert after == before + 1


def test_duplicate_handle_case_insensitive_returns_409(api_client):
    base = f"test_{uuid.uuid4().hex[:6]}"[:15]
    first_payload = make_payload(handle=base)
    second_payload = make_payload(handle=base.upper())

    first = api_client.post(f"{BASE_URL}/api/participations", json=first_payload)
    second = api_client.post(f"{BASE_URL}/api/participations", json=second_payload)

    assert first.status_code == 201
    assert second.status_code == 409
    assert "detail" in second.json()


# Module: validation and rejection
def test_rejects_invalid_handle(api_client):
    payload = make_payload(handle="bad-handle")
    response = api_client.post(f"{BASE_URL}/api/participations", json=payload)
    assert response.status_code == 422
    assert "detail" in response.json()


def test_rejects_zero_wallet(api_client):
    payload = make_payload(handle=f"test_{uuid.uuid4().hex[:6]}"[:15])
    payload["wallet"] = "0x0000000000000000000000000000000000000000"
    response = api_client.post(f"{BASE_URL}/api/participations", json=payload)
    assert response.status_code == 422
    assert "detail" in response.json()


def test_rejects_invalid_wallet_format(api_client):
    payload = make_payload(handle=f"test_{uuid.uuid4().hex[:6]}"[:15])
    payload["wallet"] = "0x123"
    response = api_client.post(f"{BASE_URL}/api/participations", json=payload)
    assert response.status_code == 422
    assert "detail" in response.json()


def test_rejects_missing_or_duplicate_tasks(api_client):
    payload = make_payload(handle=f"test_{uuid.uuid4().hex[:6]}"[:15])
    payload["completed_tasks"] = ["follow", "like", "repost", "repost"]
    response = api_client.post(f"{BASE_URL}/api/participations", json=payload)
    assert response.status_code == 422
    assert "detail" in response.json()


def test_rejects_consent_false(api_client):
    payload = make_payload(handle=f"test_{uuid.uuid4().hex[:6]}"[:15])
    payload["consent"] = False
    response = api_client.post(f"{BASE_URL}/api/participations", json=payload)
    assert response.status_code == 422
    assert "detail" in response.json()


def test_rejects_invalid_referral_format(api_client):
    payload = make_payload(handle=f"test_{uuid.uuid4().hex[:6]}"[:15], referred_by="BAD")
    response = api_client.post(f"{BASE_URL}/api/participations", json=payload)
    assert response.status_code == 422
    assert "detail" in response.json()


def test_rejects_unknown_referral(api_client):
    payload = make_payload(handle=f"test_{uuid.uuid4().hex[:6]}"[:15], referred_by="ABCDEFGH")
    response = api_client.post(f"{BASE_URL}/api/participations", json=payload)
    assert response.status_code == 422
    assert "detail" in response.json()


def test_valid_referral_persists_on_new_registration(api_client, mongo_db):
    inviter_handle = f"test_{uuid.uuid4().hex[:6]}"[:15]
    invitee_handle = f"test_{uuid.uuid4().hex[:6]}"[:15]

    inviter_payload = make_payload(handle=inviter_handle)
    inviter_response = api_client.post(f"{BASE_URL}/api/participations", json=inviter_payload)
    assert inviter_response.status_code == 201
    inviter_ref = inviter_response.json()["ref_code"]

    invitee_payload = make_payload(handle=invitee_handle, referred_by=inviter_ref)
    invitee_response = api_client.post(f"{BASE_URL}/api/participations", json=invitee_payload)
    assert invitee_response.status_code == 201
    assert invitee_response.json()["handle"].lower() == invitee_handle.lower()

    invitee_doc = mongo_db.agents.find_one({"handle_key": invitee_handle.lower()})
    assert invitee_doc is not None
    assert invitee_doc["referred_by"] == inviter_ref
