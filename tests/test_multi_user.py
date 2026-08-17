"""Two accounts must not be able to see or touch each other's data.

The interesting cases are not the list endpoints — those always filtered by
user_id — but the by-ID ones. `PATCH /api/profile/experience/{id}` took an
opaque UUID and no notion of who was asking, so knowing an id was the same as
owning the row. These tests pin that shut.
"""

import pytest
from fastapi.testclient import TestClient

import loom.api as api
from loom.storage.repository import InMemoryDataStorage

KEY = "test-key"
ALICE = "alice@example.com"
BOB = "bob@example.com"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(api, "LOOM_API_KEY", KEY)
    monkeypatch.setattr(api, "_storage", InMemoryDataStorage())
    # The translator would reach for an API key and a network.
    async def _noop(*args, **kwargs):
        return None
    monkeypatch.setattr(api, "_auto_translate_experience", _noop)
    with TestClient(api.app) as c:
        yield c


def headers(user: str | None) -> dict[str, str]:
    h = {"Authorization": f"Bearer {KEY}"}
    if user:
        h["X-Loom-User"] = user
    return h


def add_experience(client, user: str, company: str) -> str:
    r = client.post(
        "/api/profile/experience",
        json={"company_en": company, "title_en": "Engineer"},
        headers=headers(user),
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ── Reads ────────────────────────────────────────────────────


def test_profiles_are_separate(client):
    add_experience(client, ALICE, "Acme")
    add_experience(client, BOB, "Globex")

    alice = client.get("/api/profile", headers=headers(ALICE)).json()
    bob = client.get("/api/profile", headers=headers(BOB)).json()

    assert [e["company"] for e in alice["experiences"]] == ["Acme"]
    assert [e["company"] for e in bob["experiences"]] == ["Globex"]


def test_no_header_falls_back_to_the_unattended_default(client, monkeypatch):
    """The CLI and cron send no identity and must keep working."""
    monkeypatch.setenv("LOOM_DEFAULT_USER_ID", "local")
    add_experience(client, None, "Cron Co")

    anonymous = client.get("/api/profile", headers=headers(None)).json()
    alice = client.get("/api/profile", headers=headers(ALICE)).json()

    assert [e["company"] for e in anonymous["experiences"]] == ["Cron Co"]
    assert alice["experiences"] == []


# ── Writes by ID ─────────────────────────────────────────────


def test_cannot_patch_another_users_experience(client):
    exp_id = add_experience(client, ALICE, "Acme")

    r = client.patch(
        f"/api/profile/experience/{exp_id}",
        json={"data": {"company_en": "Owned"}},
        headers=headers(BOB),
    )
    assert r.status_code == 404

    alice = client.get("/api/profile", headers=headers(ALICE)).json()
    assert alice["experiences"][0]["company"] == "Acme"


def test_cannot_delete_another_users_experience(client):
    exp_id = add_experience(client, ALICE, "Acme")

    assert client.delete(
        f"/api/profile/experience/{exp_id}", headers=headers(BOB)
    ).status_code == 404
    assert client.delete(
        f"/api/profile/experience/{exp_id}", headers=headers(ALICE)
    ).status_code == 200


def test_cannot_hang_a_bullet_off_another_users_experience(client):
    exp_id = add_experience(client, ALICE, "Acme")

    r = client.post(
        "/api/profile/bullet",
        json={
            "experience_id": exp_id,
            "content_en": "Injected",
            "auto_translate": False,
        },
        headers=headers(BOB),
    )
    assert r.status_code == 404


def test_bullets_are_stamped_with_their_author(client):
    exp_id = add_experience(client, ALICE, "Acme")
    r = client.post(
        "/api/profile/bullet",
        json={
            "experience_id": exp_id,
            "content_en": "Shipped the thing",
            "auto_translate": False,
        },
        headers=headers(ALICE),
    )
    assert r.status_code == 200, r.text
    bullet_id = r.json()["id"]

    # Owned by Alice, so Bob's edit finds nothing to edit.
    assert client.patch(
        f"/api/profile/bullet/{bullet_id}",
        json={"data": {"content_en": "Owned"}},
        headers=headers(BOB),
    ).status_code == 404
    assert client.patch(
        f"/api/profile/bullet/{bullet_id}",
        json={"data": {"content_en": "Reworded"}},
        headers=headers(ALICE),
    ).status_code == 200


# ── Auth ─────────────────────────────────────────────────────


def test_api_still_requires_the_bearer_key(client):
    r = client.get("/api/profile", headers={"X-Loom-User": ALICE})
    assert r.status_code == 401
