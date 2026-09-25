"""
routers/predict.py — Visit recording and trajectory risk update endpoints.

POST /visits/{woman_id}   — record a visit, run Model B, update woman risk
GET  /visits/{woman_id}/visits — return full visit history sorted by date
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from typing import List
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

# Ensure project root is importable
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)
for _p in [_BACKEND_DIR, _PROJECT_ROOT]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from backend.db import Visit, Woman, get_db
from backend.schemas import VisitCreate, VisitOut

router = APIRouter(prefix="/visits", tags=["Visits & Trajectory Risk"])


# ---------------------------------------------------------------------------
# Lazy model import — graceful degradation if Model B not trained yet
# ---------------------------------------------------------------------------


def _recompute_trajectory(visit_history: list, baseline_risk_score: float | None):
    """
    Call Model B's recompute_trajectory_risk with visit history.

    Returns (updated_risk_score, escalation_flags_list) or (None, []).
    """
    try:
        from models.model_b_trajectory import recompute_trajectory_risk  # type: ignore

        result = recompute_trajectory_risk(
            visit_history=visit_history,
            baseline_risk_score=baseline_risk_score,
        )
        return result.get("updated_risk_score"), result.get("escalation_flags", [])
    except ModuleNotFoundError:
        return None, []
    except FileNotFoundError:
        return None, []
    except Exception as exc:  # noqa: BLE001
        print(f"[predict] Model B inference failed: {exc}")
        return None, []


# ---------------------------------------------------------------------------
# POST /visits/{woman_id} — record a visit and recompute risk
# ---------------------------------------------------------------------------


@router.post("/{woman_id}", response_model=VisitOut, summary="Record a visit")
def record_visit(
    woman_id: str,
    payload: VisitCreate,
    db: Session = Depends(get_db),
):
    """
    Persist a new ANC visit, run Model B trajectory risk recomputation,
    and update the woman's current_risk_score and escalation_flags.

    Steps:
    1. Fetch woman record (404 if not found).
    2. Insert Visit row.
    3. Load all visits for this woman (ordered by visit_date).
    4. Call Model B to get updated trajectory risk.
    5. Write risk back to Woman and last_contact_date = now.
    6. Return VisitOut.
    """
    # 1. Fetch woman
    woman = db.query(Woman).filter(Woman.id == woman_id).first()
    if not woman:
        raise HTTPException(status_code=404, detail=f"Woman '{woman_id}' not found")

    visit_date = payload.visit_date or datetime.utcnow()
    visit_number = payload.visit_number
    if visit_number is None:
        count = db.query(Visit).filter(Visit.woman_id == woman_id).count()
        visit_number = count + 1

    # 2. Insert new visit (risk fields are blank until Model B runs)
    visit = Visit(
        id=str(uuid4()),
        woman_id=woman_id,
        visit_date=visit_date,
        visit_number=visit_number,
        haemoglobin_g_dl=payload.haemoglobin_g_dl,
        systolic_bp=payload.systolic_bp,
        diastolic_bp=payload.diastolic_bp,
        fundal_height_cm=payload.fundal_height_cm,
        weight_kg=payload.weight_kg,
        danger_sign=payload.danger_sign,
    )
    db.add(visit)
    db.flush()  # assign id without committing so we can include it in history

    # 3. Build visit history list for Model B (include the new visit)
    all_visits = (
        db.query(Visit)
        .filter(Visit.woman_id == woman_id)
        .order_by(Visit.visit_date)
        .all()
    )
    visit_history = [
        {
            "visit_number": v.visit_number,
            "visit_date": v.visit_date.isoformat() if v.visit_date else None,
            "haemoglobin_g_dl": v.haemoglobin_g_dl,
            "systolic_bp": v.systolic_bp,
            "diastolic_bp": v.diastolic_bp,
            "fundal_height_cm": v.fundal_height_cm,
            "weight_kg": v.weight_kg,
            "danger_sign": v.danger_sign,
        }
        for v in all_visits
    ]

    # 4. Run Model B
    updated_score, esc_flags = _recompute_trajectory(
        visit_history=visit_history,
        baseline_risk_score=woman.baseline_risk_score,
    )

    # 5. Write risk back to the visit row and the woman record
    visit.updated_risk_score = updated_score
    visit.escalation_flags = json.dumps(esc_flags) if esc_flags else None

    woman.current_risk_score = updated_score if updated_score is not None else woman.current_risk_score
    woman.escalation_flags = json.dumps(esc_flags) if esc_flags else woman.escalation_flags
    woman.last_contact_date = visit_date

    db.commit()
    db.refresh(visit)
    return visit


# ---------------------------------------------------------------------------
# GET /visits/{woman_id}/visits — return full visit history
# ---------------------------------------------------------------------------


@router.get("/{woman_id}/visits", response_model=List[VisitOut], summary="Get visit history")
def get_visits(woman_id: str, db: Session = Depends(get_db)):
    """
    Return all visits for a woman sorted by visit_date ascending.
    404 if the woman is not registered.
    """
    woman = db.query(Woman).filter(Woman.id == woman_id).first()
    if not woman:
        raise HTTPException(status_code=404, detail=f"Woman '{woman_id}' not found")

    visits = (
        db.query(Visit)
        .filter(Visit.woman_id == woman_id)
        .order_by(Visit.visit_date)
        .all()
    )
    return visits
