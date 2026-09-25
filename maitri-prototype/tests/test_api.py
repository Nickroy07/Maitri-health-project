"""
test_api.py — Integration tests for the MAITRI FastAPI backend.

Uses the `client`, `sample_woman_data`, and `sample_visit_data` fixtures
from conftest.py. Each test runs against a fresh in-memory test database.
"""

import os
import sys
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _register(client, woman_data):
    """Register a woman and return her woman_id."""
    resp = client.post("/register", json=woman_data)
    assert resp.status_code in (200, 201), (
        f"Registration failed ({resp.status_code}): {resp.text}"
    )
    data = resp.json()
    assert "id" in data or "woman_id" in data, f"No ID in response: {data}"
    return str(data.get("id") or data.get("woman_id"))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_health_check(client):
    """GET / should return 200 with status=ok."""
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("status") == "ok", f"Unexpected body: {body}"


def test_register_woman(client, sample_woman_data):
    """POST /register should create a woman and return her ID."""
    resp = client.post("/register", json=sample_woman_data)
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert "id" in data or "woman_id" in data, f"No ID field in: {data}"


def test_register_and_get_dashboard(client, sample_woman_data):
    """After registering a woman, dashboard summary should show >= 1 total_registered."""
    _register(client, sample_woman_data)
    resp = client.get("/dashboard/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("total_registered", 0) >= 1, f"Dashboard: {body}"


def test_add_visit(client, sample_woman_data, sample_visit_data):
    """POST /visits/{id} should accept a new visit and return updated_risk_score."""
    woman_id = _register(client, sample_woman_data)
    resp = client.post(f"/visits/{woman_id}", json=sample_visit_data)
    assert resp.status_code == 200, f"Visit failed ({resp.status_code}): {resp.text}"
    data = resp.json()
    assert "updated_risk_score" in data, f"No updated_risk_score in: {data}"


def test_priority_queue(client, sample_woman_data):
    """GET /prioritise/queue should return a list of women each with priority_score."""
    for i in range(3):
        _register(client, {**sample_woman_data, "full_name": f"Test Woman {i}"})
    resp = client.get("/prioritise/queue")
    assert resp.status_code == 200
    queue = resp.json()
    assert isinstance(queue, list), f"Expected list, got: {type(queue)}"
    assert len(queue) >= 1
    for item in queue:
        assert "priority_score" in item, f"Item missing priority_score: {item}"


def test_referral_lifecycle(client, sample_woman_data):
    """Full referral lifecycle: raise → bed_booked, visible in /referral/open."""
    woman_id = _register(client, sample_woman_data)

    # Raise referral
    raise_resp = client.post(f"/referral/{woman_id}/raise")
    assert raise_resp.status_code == 200, f"Raise failed: {raise_resp.text}"
    raise_data = raise_resp.json()

    # Confirm it appears in open referrals
    open_resp = client.get("/referral/open")
    assert open_resp.status_code == 200
    assert len(open_resp.json()) >= 1

    # Advance status to bed_booked
    event_id = (
        raise_data.get("id")
        or raise_data.get("event_id")
        or raise_data.get("referral_id")
    )
    assert event_id, f"No referral ID in raise response: {raise_data}"
    status_resp = client.post(
        f"/referral/{event_id}/status",
        json={"new_status": "bed_booked"}
    )
    assert status_resp.status_code == 200, f"Status update failed: {status_resp.text}"


def test_sync_endpoint(client, sample_woman_data):
    """POST /sync should accept a batch and return synced_registrations count."""
    batch = [
        {**sample_woman_data, "full_name": "Sync Woman 1"},
        {**sample_woman_data, "full_name": "Sync Woman 2"},
    ]
    resp = client.post("/sync", json={"registrations": batch, "visits": []})
    assert resp.status_code == 200, f"Sync failed: {resp.text}"
    body = resp.json()
    assert body.get("synced_registrations") == 2, f"Expected 2, got: {body}"


def test_postnatal_delivery(client, sample_woman_data):
    """POST /postnatal/{id}/delivery should create postnatal contact stubs."""
    woman_id = _register(client, sample_woman_data)
    delivery_resp = client.post(
        f"/postnatal/{woman_id}/delivery",
        json={"delivery_date": "2026-09-01"}
    )
    assert delivery_resp.status_code == 200, f"Delivery failed: {delivery_resp.text}"

    pnc_resp = client.get(f"/postnatal/{woman_id}")
    assert pnc_resp.status_code == 200
    contacts = pnc_resp.json()
    assert isinstance(contacts, list), f"Expected list of contacts, got: {type(contacts)}"
    # Should have created stubs for days 1, 3, 7, 14, 28, 42
    assert len(contacts) >= 1, "No postnatal contact stubs created"
