"""
test_model_b.py — Unit tests for Model B trajectory re-scoring (rule engine).

Tests verify that each escalation flag triggers correctly and that the
updated risk score is always bounded and directionally correct.
"""

import os
import sys
import pytest
from datetime import date, timedelta

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from models.model_b_trajectory import recompute_trajectory_risk  # noqa: E402


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _visit(hb=10.5, systolic=115, diastolic=75, danger_sign=0,
           fundal_height_cm=20.0, weight_kg=55.0, days_ago=0):
    """Create a single visit dict for testing."""
    visit_date = (date.today() - timedelta(days=days_ago)).isoformat()
    return {
        "haemoglobin_g_dl": hb,
        "systolic_bp": systolic,
        "diastolic_bp": diastolic,
        "fundal_height_cm": fundal_height_cm,
        "weight_kg": weight_kg,
        "danger_sign": danger_sign,
        "visit_date": visit_date,
    }


# ---------------------------------------------------------------------------
# Flag detection tests
# ---------------------------------------------------------------------------
def test_hb_falling_flag():
    """Hb drop of > 1.0 g/dL between visits triggers HB_FALLING."""
    visits = [_visit(hb=10.0, days_ago=14), _visit(hb=8.5, days_ago=0)]
    result = recompute_trajectory_risk(visits, baseline_score=0.4)
    assert "HB_FALLING" in result["escalation_flags"], result["escalation_flags"]


def test_severe_anaemia_flag():
    """Any visit with Hb < 7.0 triggers SEVERE_ANAEMIA."""
    visits = [_visit(hb=10.0, days_ago=14), _visit(hb=6.2, days_ago=0)]
    result = recompute_trajectory_risk(visits, baseline_score=0.4)
    assert "SEVERE_ANAEMIA" in result["escalation_flags"], result["escalation_flags"]


def test_bp_rising_flag():
    """Systolic rise of > 20 mmHg from first visit triggers BP_RISING."""
    visits = [_visit(systolic=110, days_ago=14), _visit(systolic=135, days_ago=0)]
    result = recompute_trajectory_risk(visits, baseline_score=0.35)
    assert "BP_RISING" in result["escalation_flags"], result["escalation_flags"]


def test_hypertension_flag():
    """Any reading >= 140 systolic triggers HYPERTENSION."""
    visits = [_visit(systolic=145, diastolic=90)]
    result = recompute_trajectory_risk(visits, baseline_score=0.5)
    assert "HYPERTENSION" in result["escalation_flags"], result["escalation_flags"]


def test_danger_sign_flag():
    """Any visit with danger_sign=1 triggers DANGER_SIGN."""
    visits = [_visit(danger_sign=0, days_ago=14), _visit(danger_sign=1, days_ago=0)]
    result = recompute_trajectory_risk(visits, baseline_score=0.4)
    assert "DANGER_SIGN" in result["escalation_flags"], result["escalation_flags"]


def test_escalated_risk_higher_than_baseline():
    """Severe Hb + danger sign should push updated score above the baseline."""
    baseline = 0.45
    visits = [_visit(hb=6.0, danger_sign=1)]
    result = recompute_trajectory_risk(visits, baseline_score=baseline)
    assert result["updated_risk_score"] > baseline, (
        f"Expected updated score > {baseline}, got {result['updated_risk_score']}"
    )


def test_risk_capped_at_1():
    """Even with all flags active, updated_risk_score must not exceed 1.0."""
    visits = [_visit(hb=5.0, systolic=160, diastolic=100, danger_sign=1)]
    result = recompute_trajectory_risk(visits, baseline_score=0.95)
    assert result["updated_risk_score"] <= 1.0, (
        f"Risk score exceeded 1.0: {result['updated_risk_score']}"
    )


def test_no_flags_stable():
    """Stable vitals across two visits should produce no escalation flags."""
    visits = [
        _visit(hb=10.2, systolic=115, diastolic=75, danger_sign=0, fundal_height_cm=20.0, days_ago=14),
        _visit(hb=10.0, systolic=114, diastolic=74, danger_sign=0, fundal_height_cm=22.0, days_ago=0),
    ]
    result = recompute_trajectory_risk(visits, baseline_score=0.3)
    assert result["escalation_flags"] == [], (
        f"Expected no flags, got {result['escalation_flags']}"
    )
