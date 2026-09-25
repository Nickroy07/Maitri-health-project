"""
routers/register.py — Woman registration endpoint.

POST /register/
  Accepts WomanCreate body, runs Model A (baseline risk), persists to DB,
  returns WomanOut.  Gracefully degrades if the model pickle is not yet
  available (models need to be trained first).
"""

from __future__ import annotations

import json
import os
import secrets
import sys
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

# Ensure the project root (parent of backend/) is on sys.path so model
# modules can be imported regardless of how uvicorn is launched.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)
for _p in [_BACKEND_DIR, _PROJECT_ROOT]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from backend.db import Woman, get_db
from backend.schemas import WomanCreate, WomanOut

router = APIRouter(prefix="/register", tags=["Registration"])

# ---------------------------------------------------------------------------
# Lazy model import — try to load at request time so startup never fails
# ---------------------------------------------------------------------------


def _predict_baseline(woman_data: dict):
    """
    Attempt to call Model A's predict_with_reasons function.

    Returns (risk_score, risk_band, top_reason_codes, escalation_flags)
    or (None, None, [], []) if the model is unavailable.
    """
    try:
        from models.train_model_a_baseline_risk import predict_with_reasons  # type: ignore

        result = predict_with_reasons(woman_data)
        return (
            result.get("risk_score"),
            result.get("risk_band"),
            result.get("top_reason_codes", []),
            result.get("escalation_flags", []),
        )
    except ModuleNotFoundError:
        # Model module doesn't exist yet
        return None, None, [], []
    except FileNotFoundError:
        # Module exists but .pkl file not trained yet
        return None, None, [], []
    except Exception as exc:  # noqa: BLE001 — broad catch to keep API alive
        # Any other inference error (shape mismatch, etc.) — log and continue
        print(f"[register] Model A inference failed: {exc}")
        return None, None, [], []


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/", response_model=WomanOut, summary="Register a new woman")
def register_woman(payload: WomanCreate, db: Session = Depends(get_db)):
    """
    Register a pregnant woman and run Model A baseline risk scoring.

    - Generates a UUID woman_id and a mock ABHA identifier.
    - Calls Model A (train_model_a_baseline_risk.predict_with_reasons).
    - Stores all fields in the Woman table.
    - Returns the full WomanOut record.

    If Model A has not been trained yet the risk columns will be null —
    they can be back-filled once the model is available.
    """
    woman_id = str(uuid4())
    abha_mock_id = "ABHA-MOCK-" + secrets.token_hex(4).upper()

    # Compute BMI if omitted
    computed_bmi = payload.bmi
    if computed_bmi is None and payload.height_cm > 0:
        computed_bmi = round(payload.weight_kg / ((payload.height_cm / 100) ** 2), 2)

    # Build a flat dict for the model (matches expected feature names)
    woman_dict = payload.model_dump(exclude={"registration_date"})
    woman_dict["bmi"] = computed_bmi

    risk_score, risk_band, reason_codes, esc_flags = _predict_baseline(woman_dict)

    reg_date = payload.registration_date or datetime.utcnow()

    woman = Woman(
        id=woman_id,
        abha_mock_id=abha_mock_id,
        full_name=payload.full_name,
        age=payload.age,
        district=payload.district,
        village=payload.village,
        phone=payload.phone,
        parity=payload.parity,
        gravida=payload.gravida,
        height_cm=payload.height_cm,
        weight_kg=payload.weight_kg,
        bmi=computed_bmi,
        haemoglobin_g_dl=payload.haemoglobin_g_dl,
        systolic_bp=payload.systolic_bp,
        diastolic_bp=payload.diastolic_bp,
        obstetric_history_flag=payload.obstetric_history_flag,
        interpregnancy_interval_months=payload.interpregnancy_interval_months,
        travel_time_to_frtu_minutes=payload.travel_time_to_frtu_minutes,
        gestational_age_weeks_at_registration=payload.gestational_age_weeks_at_registration,
        fundal_height_cm=payload.fundal_height_cm,
        danger_sign_reported=payload.danger_sign_reported,
        registration_date=reg_date,
        baseline_risk_score=risk_score,
        baseline_risk_band=risk_band,
        top_reason_codes=json.dumps(reason_codes) if reason_codes else None,
        current_risk_score=risk_score,       # initialise current == baseline
        escalation_flags=json.dumps(esc_flags) if esc_flags else None,
        is_synced=True,
    )

    db.add(woman)
    db.commit()
    db.refresh(woman)
    return woman
