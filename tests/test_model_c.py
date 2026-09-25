"""
test_model_c.py — Unit tests for Model C prioritisation queue.

Tests verify sorting, capacity cap, urgency upweighting, distance upweighting,
and handling of never-contacted women.
"""

import os
import sys
import pytest
from datetime import date, timedelta

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from models.model_c_prioritisation import compute_priority_queue  # noqa: E402


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _woman(woman_id, risk_score, last_contact_days_ago=None, travel_time_minutes=30):
    """Build a woman dict suitable for compute_priority_queue input."""
    if last_contact_days_ago is None:
        last_contact_date = None
    else:
        last_contact_date = (date.today() - timedelta(days=last_contact_days_ago)).isoformat()
    return {
        "woman_id": woman_id,
        "current_risk_score": risk_score,
        "last_contact_date": last_contact_date,
        "travel_time_minutes": travel_time_minutes,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_sorted_descending():
    """Output must be sorted descending by priority_score."""
    women = [
        _woman("W1", 0.3, last_contact_days_ago=2),
        _woman("W2", 0.7, last_contact_days_ago=10),
        _woman("W3", 0.5, last_contact_days_ago=5),
        _woman("W4", 0.9, last_contact_days_ago=1),
        _woman("W5", 0.2, last_contact_days_ago=20),
    ]
    result = compute_priority_queue(women, weekly_visit_capacity=len(women))
    scores = [item["priority_score"] for item in result]
    assert scores == sorted(scores, reverse=True), f"Not sorted descending: {scores}"


def test_capacity_respected():
    """Queue must be truncated to weekly_visit_capacity."""
    women = [_woman(f"W{i}", round(0.1 * i, 1), last_contact_days_ago=i) for i in range(1, 11)]
    result = compute_priority_queue(women, weekly_visit_capacity=3)
    assert len(result) == 3, f"Expected 3 results, got {len(result)}"


def test_high_risk_tops_queue():
    """A high-risk woman (0.9) unseen for 20 days beats medium-risk (0.5) seen yesterday."""
    women = [
        _woman("HIGH", 0.9, last_contact_days_ago=20),
        _woman("MED", 0.5, last_contact_days_ago=1),
    ]
    result = compute_priority_queue(women, weekly_visit_capacity=2)
    assert result[0]["woman_id"] == "HIGH", (
        f"Expected HIGH at top, got {result[0]['woman_id']}"
    )


def test_long_unseen_upweighted():
    """Same risk score — woman unseen for 30 days outscores woman seen 2 days ago."""
    women = [
        _woman("LONG", 0.6, last_contact_days_ago=30),
        _woman("RECENT", 0.6, last_contact_days_ago=2),
    ]
    result = compute_priority_queue(women, weekly_visit_capacity=2)
    scores = {item["woman_id"]: item["priority_score"] for item in result}
    assert scores["LONG"] > scores["RECENT"], (
        f"LONG ({scores['LONG']:.3f}) should beat RECENT ({scores['RECENT']:.3f})"
    )


def test_distant_woman_slightly_upweighted():
    """Same risk + same last contact — woman 200 min away >= woman 10 min away."""
    women = [
        _woman("FAR", 0.5, last_contact_days_ago=7, travel_time_minutes=200),
        _woman("NEAR", 0.5, last_contact_days_ago=7, travel_time_minutes=10),
    ]
    result = compute_priority_queue(women, weekly_visit_capacity=2)
    scores = {item["woman_id"]: item["priority_score"] for item in result}
    assert scores["FAR"] >= scores["NEAR"], (
        f"FAR ({scores['FAR']:.3f}) should be >= NEAR ({scores['NEAR']:.3f})"
    )


def test_none_last_contact():
    """Woman with last_contact_date=None should have priority >= woman last seen 30 days ago."""
    women = [
        _woman("NEVER", 0.5, last_contact_days_ago=None),
        _woman("THIRTY", 0.5, last_contact_days_ago=30),
    ]
    result = compute_priority_queue(women, weekly_visit_capacity=2)
    scores = {item["woman_id"]: item["priority_score"] for item in result}
    assert scores["NEVER"] >= scores["THIRTY"], (
        f"NEVER ({scores['NEVER']:.3f}) should be >= THIRTY ({scores['THIRTY']:.3f})"
    )
