"""
routers/persist.py — Postnatal contact scheduling and tracking endpoints.

POST /postnatal/{woman_id}/delivery     — record delivery date, create stubs
POST /postnatal/contact/{contact_id}   — mark contact as made
GET  /postnatal/{woman_id}             — list all contacts for a woman
GET  /postnatal/due/today              — contacts due today not yet made
GET  /postnatal/overdue                — contacts overdue (>1 day) and not made
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db import PostnatalContact, Woman, get_db
from backend.schemas import PostnatalContactOut

router = APIRouter(prefix="/postnatal", tags=["Postnatal Contacts"])

# Standard WHO / national protocol contact schedule (days post-delivery)
_CONTACT_DAYS = [1, 3, 7, 14, 28, 42]


def _due_date(delivery_date: datetime, contact_day: int) -> datetime:
    """Return the calendar date on which a postnatal contact is due."""
    return delivery_date + timedelta(days=contact_day)


# ---------------------------------------------------------------------------
# POST /postnatal/{woman_id}/delivery — record delivery and create stubs
# ---------------------------------------------------------------------------


@router.post(
    "/{woman_id}/delivery",
    response_model=List[PostnatalContactOut],
    summary="Record delivery date",
)
def record_delivery(
    woman_id: str,
    delivery_date: datetime = Body(..., embed=True, description="Actual delivery date (UTC)"),
    db: Session = Depends(get_db),
):
    """
    Record the delivery date for a woman and create 6 postnatal contact stubs
    at days 1, 3, 7, 14, 28, 42.

    If stubs already exist for this woman they are deleted and recreated so
    re-recording a delivery (e.g. correcting the date) stays consistent.
    Returns the newly created stubs.
    """
    woman = db.query(Woman).filter(Woman.id == woman_id).first()
    if not woman:
        raise HTTPException(status_code=404, detail=f"Woman '{woman_id}' not found")

    # Remove any existing stubs for this woman (idempotent re-recording)
    db.query(PostnatalContact).filter(PostnatalContact.woman_id == woman_id).delete()

    stubs = []
    for day in _CONTACT_DAYS:
        stub = PostnatalContact(
            id=str(uuid4()),
            woman_id=woman_id,
            contact_day=day,
            contact_date=None,         # actual contact date — filled in later
            contact_made=False,
            delivery_date=delivery_date,
        )
        db.add(stub)
        stubs.append(stub)

    db.commit()
    for s in stubs:
        db.refresh(s)
    return stubs


# ---------------------------------------------------------------------------
# POST /postnatal/contact/{contact_id} — mark contact as made
# NOTE: this route must appear BEFORE /{woman_id} to avoid path shadowing
# ---------------------------------------------------------------------------


@router.post(
    "/contact/{contact_id}",
    response_model=PostnatalContactOut,
    summary="Mark contact as made",
)
def mark_contact_made(
    contact_id: str,
    notes: str = Body(None, embed=True, description="Optional notes from contact"),
    db: Session = Depends(get_db),
):
    """
    Mark a postnatal contact stub as completed.

    Sets contact_made=True and contact_date=now (UTC).
    """
    contact = db.query(PostnatalContact).filter(PostnatalContact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail=f"Contact '{contact_id}' not found")

    contact.contact_made = True
    contact.contact_date = datetime.utcnow()
    if notes:
        contact.notes = notes

    db.commit()
    db.refresh(contact)
    return contact


# ---------------------------------------------------------------------------
# GET /postnatal/due/today — contacts due today, not yet made
# ---------------------------------------------------------------------------


@router.get(
    "/due/today",
    response_model=List[PostnatalContactOut],
    summary="Contacts due today",
)
def due_today(db: Session = Depends(get_db)):
    """
    Return all postnatal contact stubs whose scheduled due date is today
    (based on delivery_date + contact_day) and have not been completed yet.
    """
    today = datetime.utcnow().date()
    contacts = (
        db.query(PostnatalContact)
        .filter(
            PostnatalContact.contact_made == False,  # noqa: E712
            PostnatalContact.delivery_date.isnot(None),
        )
        .all()
    )
    due = [
        c for c in contacts
        if _due_date(c.delivery_date, c.contact_day).date() == today
    ]
    return due


# ---------------------------------------------------------------------------
# GET /postnatal/overdue — contacts overdue (> 1 day) and not made
# ---------------------------------------------------------------------------


@router.get(
    "/overdue",
    response_model=List[PostnatalContactOut],
    summary="Overdue contacts",
)
def overdue(db: Session = Depends(get_db)):
    """
    Return all postnatal contact stubs whose scheduled due date was more than
    1 day ago and have not been completed yet.
    """
    cutoff = datetime.utcnow() - timedelta(days=1)
    contacts = (
        db.query(PostnatalContact)
        .filter(
            PostnatalContact.contact_made == False,  # noqa: E712
            PostnatalContact.delivery_date.isnot(None),
        )
        .all()
    )
    overdue_list = [
        c for c in contacts
        if _due_date(c.delivery_date, c.contact_day) < cutoff
    ]
    return overdue_list


# ---------------------------------------------------------------------------
# GET /postnatal/{woman_id} — all contacts for a woman
# ---------------------------------------------------------------------------


@router.get(
    "/{woman_id}",
    response_model=List[PostnatalContactOut],
    summary="Get all postnatal contacts for a woman",
)
def get_contacts(woman_id: str, db: Session = Depends(get_db)):
    """Return all postnatal contact stubs for a woman, ordered by contact_day."""
    woman = db.query(Woman).filter(Woman.id == woman_id).first()
    if not woman:
        raise HTTPException(status_code=404, detail=f"Woman '{woman_id}' not found")

    contacts = (
        db.query(PostnatalContact)
        .filter(PostnatalContact.woman_id == woman_id)
        .order_by(PostnatalContact.contact_day)
        .all()
    )
    return contacts
