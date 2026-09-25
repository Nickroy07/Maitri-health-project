"""
routers/prioritise.py — CHW outreach priority queue endpoint.

GET /prioritise/queue?capacity=<N>
  Returns women sorted by priority score (descending), optionally capped
  at capacity.  Priority score is computed by Model C.
"""

from __future__ import annotations

import json
import os
import sys
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

# Ensure project root is importable
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)
for _p in [_BACKEND_DIR, _PROJECT_ROOT]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from backend.db import Woman, get_db
from backend.schemas import PriorityWoman

router = APIRouter(prefix="/prioritise", tags=["Prioritisation"])


# ---------------------------------------------------------------------------
# Lazy model import — graceful degradation if Model C not trained yet
# ---------------------------------------------------------------------------


def _compute_priority_queue(women_input: list) -> list:
    """
    Call Model C's compute_priority_queue with a list of woman feature dicts.

    Each dict in the returned list must contain at minimum:
        woman_id, priority_score

    Returns the input list unchanged (sorted by current_risk_score desc) if
    Model C is unavailable, so the endpoint always returns something useful.
    """
    try:
        from models.model_c_prioritisation import compute_priority_queue  # type: ignore

        return compute_priority_queue(women_input)
    except ModuleNotFoundError:
        pass
    except FileNotFoundError:
        pass
    except Exception as exc:  # noqa: BLE001
        print(f"[prioritise] Model C failed: {exc}")

    # Fallback: use current_risk_score as a naive priority proxy
    for w in women_input:
        w["priority_score"] = w.get("current_risk_score") or 0.0
    return sorted(women_input, key=lambda x: x["priority_score"], reverse=True)


# ---------------------------------------------------------------------------
# GET /prioritise/queue
# ---------------------------------------------------------------------------


@router.get("/queue", response_model=List[PriorityWoman], summary="Get priority queue")
def get_priority_queue(
    capacity: Optional[int] = Query(
        None, ge=1, description="Max number of women to return"
    ),
    db: Session = Depends(get_db),
):
    """
    Fetch all women from the DB, build a feature dict for each, run Model C,
    and return the sorted priority queue.

    Query parameter:
    - **capacity**: maximum number of results (default: all women)

    The priority score combines risk score, time since last contact, travel
    time, and danger-sign flags — details are encapsulated inside Model C.
    """
    women = db.query(Woman).all()

    if not women:
        return []

    # Build feature dicts for Model C
    women_input = [
        {
            "woman_id": w.id,
            "full_name": w.full_name,
            "current_risk_score": w.current_risk_score,
            "baseline_risk_score": w.baseline_risk_score,
            "risk_band": w.baseline_risk_band,
            "last_contact_date": w.last_contact_date.isoformat() if w.last_contact_date else None,
            "travel_time_minutes": w.travel_time_to_frtu_minutes,
            "danger_sign_reported": w.danger_sign_reported,
            "escalation_flags": w.escalation_flags,  # JSON string
        }
        for w in women
    ]

    prioritised = _compute_priority_queue(women_input)

    # Truncate to capacity if requested
    if capacity:
        prioritised = prioritised[:capacity]

    # Build PriorityWoman response objects
    results: List[PriorityWoman] = []
    for entry in prioritised:
        results.append(
            PriorityWoman(
                woman_id=entry["woman_id"],
                full_name=entry["full_name"],
                current_risk_score=entry.get("current_risk_score"),
                priority_score=entry.get("priority_score", 0.0),
                risk_band=entry.get("risk_band"),
                last_contact_date=entry.get("last_contact_date"),
                travel_time_minutes=entry.get("travel_time_minutes", 0),
                escalation_flags=entry.get("escalation_flags"),
            )
        )

    return results
