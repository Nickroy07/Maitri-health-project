"""
routers/pull.py — Referral lifecycle management endpoints.

POST /referral/{woman_id}/raise         — create a new referral event
POST /referral/{event_id}/status        — advance state machine
GET  /referral/open                     — list all unresolved referrals
GET  /referral/{event_id}               — single referral detail
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db import ReferralEvent, Woman, get_db
from backend.schemas import ReferralEventOut

router = APIRouter(prefix="/referral", tags=["Referrals"])

# Valid state-machine transitions
# Each key is the current status; value is the set of allowed next statuses.
_TRANSITIONS: Dict[str, list] = {
    "raised": ["bed_booked", "lost"],
    "bed_booked": ["ambulance_dispatched", "lost"],
    "ambulance_dispatched": ["arrived", "lost"],
    "arrived": [],   # terminal resolved state
    "lost": [],      # terminal unresolved state
}

# Statuses considered resolved (no further action needed)
_RESOLVED_STATUSES = {"arrived", "lost"}


# ---------------------------------------------------------------------------
# POST /referral/{woman_id}/raise
# ---------------------------------------------------------------------------


@router.post("/{woman_id}/raise", response_model=ReferralEventOut, summary="Raise a referral")
def raise_referral(
    woman_id: str,
    notes: Optional[str] = Body(None, embed=True, description="Optional initial notes"),
    db: Session = Depends(get_db),
):
    """
    Raise a new referral for a registered woman.

    Creates a ReferralEvent with status='raised' and stamps raised_at=now.
    Returns the new event record.
    """
    woman = db.query(Woman).filter(Woman.id == woman_id).first()
    if not woman:
        raise HTTPException(status_code=404, detail=f"Woman '{woman_id}' not found")

    event = ReferralEvent(
        id=str(uuid4()),
        woman_id=woman_id,
        status="raised",
        raised_at=datetime.utcnow(),
        notes=notes,
        is_resolved=False,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


# ---------------------------------------------------------------------------
# POST /referral/{event_id}/status
# ---------------------------------------------------------------------------


class _StatusUpdate:
    """Request body for status advancement."""
    pass


@router.post("/{event_id}/status", response_model=ReferralEventOut, summary="Advance referral status")
def update_referral_status(
    event_id: str,
    new_status: str = Body(..., embed=True, description="Target status"),
    notes: Optional[str] = Body(None, embed=True, description="Optional notes"),
    db: Session = Depends(get_db),
):
    """
    Advance the referral state machine to the requested status.

    Allowed transitions:
    - raised          → bed_booked | lost
    - bed_booked      → ambulance_dispatched | lost
    - ambulance_dispatched → arrived | lost

    Timestamps for the entered state are automatically recorded.
    The referral is marked is_resolved=True once it reaches 'arrived' or 'lost'.
    """
    event = db.query(ReferralEvent).filter(ReferralEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail=f"Referral event '{event_id}' not found")

    allowed = _TRANSITIONS.get(event.status, [])
    if new_status not in allowed:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Cannot transition from '{event.status}' to '{new_status}'. "
                f"Allowed: {allowed}"
            ),
        )

    # Stamp the appropriate timestamp column
    now = datetime.utcnow()
    if new_status == "bed_booked":
        event.bed_booked_at = now
    elif new_status == "ambulance_dispatched":
        event.ambulance_dispatched_at = now
    elif new_status == "arrived":
        event.arrived_at = now
    elif new_status == "lost":
        event.lost_at = now

    event.status = new_status
    if notes:
        event.notes = notes
    event.is_resolved = new_status in _RESOLVED_STATUSES

    db.commit()
    db.refresh(event)
    return event


# ---------------------------------------------------------------------------
# GET /referral/open — must be defined BEFORE /{event_id} to avoid shadowing
# ---------------------------------------------------------------------------


@router.get("/open", response_model=List[Dict[str, Any]], summary="List open referrals")
def list_open_referrals(db: Session = Depends(get_db)):
    """
    Return all unresolved referral events enriched with woman name and district.

    Results are ordered by raised_at ascending (oldest first) so the most
    urgent cases appear at the top.
    """
    events = (
        db.query(ReferralEvent)
        .filter(ReferralEvent.is_resolved == False)  # noqa: E712
        .order_by(ReferralEvent.raised_at)
        .all()
    )

    results = []
    for ev in events:
        woman = db.query(Woman).filter(Woman.id == ev.woman_id).first()
        results.append(
            {
                "id": ev.id,
                "woman_id": ev.woman_id,
                "woman_name": woman.full_name if woman else "Unknown",
                "district": woman.district if woman else "Unknown",
                "status": ev.status,
                "raised_at": ev.raised_at.isoformat() if ev.raised_at else None,
                "notes": ev.notes,
            }
        )
    return results


# ---------------------------------------------------------------------------
# GET /referral/{event_id} — single referral detail
# ---------------------------------------------------------------------------


@router.get("/{event_id}", response_model=ReferralEventOut, summary="Get referral detail")
def get_referral(event_id: str, db: Session = Depends(get_db)):
    """Return a single referral event by its ID."""
    event = db.query(ReferralEvent).filter(ReferralEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail=f"Referral event '{event_id}' not found")
    return event
