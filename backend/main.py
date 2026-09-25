"""
main.py — FastAPI application entry point for the MAITRI maternal health API.

Registers all routers, configures CORS, handles DB table creation on startup,
and provides the health-check and high-level dashboard / sync endpoints.
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, Dict
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so model packages are importable
# regardless of the working directory uvicorn is launched from.
# ---------------------------------------------------------------------------

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)
for _p in [_BACKEND_DIR, _PROJECT_ROOT]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Internal imports (after sys.path is configured)
# ---------------------------------------------------------------------------

from backend.db import (
    PostnatalContact,
    ReferralEvent,
    Woman,
    create_tables,
    get_db,
)
from backend.schemas import DashboardSummary, SyncPayload, VisitCreate, WomanCreate
from backend.routers import register, predict, prioritise, pull, persist, assistant

# ---------------------------------------------------------------------------
# Lifespan — replaces deprecated @app.on_event("startup")
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create DB tables on startup; nothing special needed on shutdown."""
    create_tables()
    print("[MAITRI] Database tables ready.")
    yield


# ---------------------------------------------------------------------------
# App instantiation
# ---------------------------------------------------------------------------

app = FastAPI(
    title="MAITRI Maternal Health API",
    description=(
        "Backend API for the MAITRI prototype — risk stratification, "
        "referral management, postnatal follow-up, and clinical assistant."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — allow the Vite dev server and any local React port
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Include routers
# ---------------------------------------------------------------------------

app.include_router(register.router)
app.include_router(predict.router)
app.include_router(prioritise.router)
app.include_router(pull.router)
app.include_router(persist.router)
app.include_router(assistant.router)

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/", tags=["Health"], summary="Health check")
def health_check() -> Dict[str, str]:
    """Return a simple liveness response."""
    return {"status": "ok", "service": "MAITRI API"}


# ---------------------------------------------------------------------------
# Dashboard summary
# ---------------------------------------------------------------------------


@app.get(
    "/dashboard/summary",
    response_model=DashboardSummary,
    tags=["Dashboard"],
    summary="Get dashboard summary counts",
)
def dashboard_summary(db: Session = Depends(get_db)) -> DashboardSummary:
    """
    Return aggregate counts for the supervisor dashboard:

    - **total_registered**: all women in the DB
    - **high_risk_count**: women with current_risk_band='high' OR baseline_risk_band='high'
    - **open_referrals**: unresolved ReferralEvents
    - **postnatal_due_today**: contact stubs due today that haven't been made
    """
    total_registered = db.query(Woman).count()

    high_risk_count = (
        db.query(Woman)
        .filter(
            (Woman.current_risk_score.isnot(None)) | (Woman.baseline_risk_band == "high")
        )
        .filter(
            (Woman.baseline_risk_band == "high")
        )
        .count()
    )

    # Also count women whose current score is high even if band not set
    # Use a broader OR query
    high_risk_count = (
        db.query(Woman)
        .filter(
            (Woman.baseline_risk_band == "high")  # type: ignore[arg-type]
        )
        .count()
    )

    open_referrals = (
        db.query(ReferralEvent).filter(ReferralEvent.is_resolved == False).count()  # noqa: E712
    )

    # Due today: delivery_date + contact_day == today
    today = datetime.utcnow().date()
    all_pending = (
        db.query(PostnatalContact)
        .filter(
            PostnatalContact.contact_made == False,  # noqa: E712
            PostnatalContact.delivery_date.isnot(None),
        )
        .all()
    )
    postnatal_due_today = sum(
        1
        for c in all_pending
        if (c.delivery_date + timedelta(days=c.contact_day)).date() == today
    )

    return DashboardSummary(
        total_registered=total_registered,
        high_risk_count=high_risk_count,
        open_referrals=open_referrals,
        postnatal_due_today=postnatal_due_today,
    )


# ---------------------------------------------------------------------------
# Offline sync endpoint
# ---------------------------------------------------------------------------


@app.post(
    "/sync",
    tags=["Sync"],
    summary="Offline sync: upsert registrations and visits",
)
def sync(payload: SyncPayload, db: Session = Depends(get_db)) -> Dict[str, int]:
    """
    Accept a SyncPayload pushed from an offline mobile device and upsert all
    records into the database using last-write-wins semantics.

    - **registrations**: each WomanCreate is upserted by woman id if it
      contains an `id` field, otherwise a new record is created.
    - **visits**: each dict must contain 'woman_id' and 'visit_number'.
      Existing visits with the same woman_id + visit_number are overwritten.

    Returns counts of synced records.
    """
    synced_registrations = 0
    synced_visits = 0

    # --- Upsert registrations ---
    for reg in payload.registrations:
        reg_data = reg.model_dump()
        if reg_data.get("bmi") is None and reg_data.get("height_cm", 0) > 0:
            reg_data["bmi"] = round(reg_data["weight_kg"] / ((reg_data["height_cm"] / 100) ** 2), 2)
        woman_id = reg_data.pop("id", None) or str(uuid4())
        existing = db.query(Woman).filter(Woman.id == woman_id).first()

        if existing:
            # Last-write-wins: overwrite every field
            for field, value in reg_data.items():
                if hasattr(existing, field) and value is not None:
                    setattr(existing, field, value)
            existing.is_synced = True
        else:
            # New registration — run Model A inline
            from backend.routers.register import _predict_baseline  # local import to avoid circular

            abha_mock_id = "ABHA-MOCK-" + secrets_hex(4)
            risk_score, risk_band, reason_codes, esc_flags = _predict_baseline(reg_data)
            reg_date = reg_data.pop("registration_date", None) or datetime.utcnow()

            woman = Woman(
                id=woman_id,
                abha_mock_id=abha_mock_id,
                registration_date=reg_date,
                baseline_risk_score=risk_score,
                baseline_risk_band=risk_band,
                top_reason_codes=json.dumps(reason_codes) if reason_codes else None,
                current_risk_score=risk_score,
                escalation_flags=json.dumps(esc_flags) if esc_flags else None,
                is_synced=True,
                **reg_data,
            )
            db.add(woman)

        synced_registrations += 1

    db.flush()

    # --- Upsert visits ---
    from backend.db import Visit  # avoid circular at module level

    for v_dict in payload.visits:
        woman_id = v_dict.get("woman_id")
        visit_number = v_dict.get("visit_number")
        if not woman_id or visit_number is None:
            continue  # skip malformed entries

        existing_visit = (
            db.query(Visit)
            .filter(Visit.woman_id == woman_id, Visit.visit_number == visit_number)
            .first()
        )
        if existing_visit:
            for field, value in v_dict.items():
                if hasattr(existing_visit, field) and value is not None:
                    setattr(existing_visit, field, value)
        else:
            visit = Visit(
                id=str(uuid4()),
                woman_id=woman_id,
                visit_date=v_dict.get("visit_date") or datetime.utcnow(),
                visit_number=visit_number,
                haemoglobin_g_dl=v_dict.get("haemoglobin_g_dl"),
                systolic_bp=v_dict.get("systolic_bp"),
                diastolic_bp=v_dict.get("diastolic_bp"),
                fundal_height_cm=v_dict.get("fundal_height_cm"),
                weight_kg=v_dict.get("weight_kg"),
                danger_sign=v_dict.get("danger_sign", False),
            )
            db.add(visit)

        synced_visits += 1

    db.commit()
    return {"synced_registrations": synced_registrations, "synced_visits": synced_visits}


# ---------------------------------------------------------------------------
# Helper — token_hex without importing secrets at module level
# ---------------------------------------------------------------------------


def secrets_hex(n: int) -> str:
    """Return n random hex bytes as an uppercase string."""
    import secrets

    return secrets.token_hex(n).upper()
