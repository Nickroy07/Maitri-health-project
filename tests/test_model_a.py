"""
test_model_a.py — Unit tests for Model A baseline risk prediction.

Tests verify that predict_with_reasons() returns structurally correct output
and that high-risk inputs score higher than low-risk inputs.

All tests are skipped automatically if the trained model artefact does not
exist (i.e. train_model_a_baseline_risk.py has not been run yet).
"""

import os
import sys
import pytest

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path for `models.*` imports
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

MODEL_A_PKL = os.path.join(PROJECT_ROOT, "models", "saved", "model_a.pkl")
MODEL_A_JSON = os.path.join(PROJECT_ROOT, "models", "saved", "model_a_features.json")

# Skip ALL tests in this module if the model has not been trained yet
pytestmark = pytest.mark.skipif(
    not (os.path.exists(MODEL_A_PKL) and os.path.exists(MODEL_A_JSON)),
    reason=(
        f"Model A artefacts not found at models/saved/. "
        "Run `python models/train_model_a_baseline_risk.py` first."
    ),
)

from models.train_model_a_baseline_risk import predict_with_reasons  # noqa: E402

# ---------------------------------------------------------------------------
# Test inputs
# ---------------------------------------------------------------------------
LOW_RISK_INPUT = {
    "age": 25,
    "parity": 1,
    "gravida": 2,
    "height_cm": 155.0,
    "weight_kg": 53.0,
    "bmi": 22.0,
    "haemoglobin_g_dl": 11.5,
    "systolic_bp": 110,
    "diastolic_bp": 70,
    "obstetric_history_flag": 0,
    "travel_time_to_frtu_minutes": 30,
    "gestational_age_weeks_at_registration": 12,
    "danger_sign_reported": 0,
}

HIGH_RISK_INPUT = {
    "age": 17,
    "parity": 5,
    "gravida": 6,
    "height_cm": 148.0,
    "weight_kg": 35.0,
    "bmi": 16.0,
    "haemoglobin_g_dl": 5.5,
    "systolic_bp": 150,
    "diastolic_bp": 95,
    "obstetric_history_flag": 1,
    "travel_time_to_frtu_minutes": 180,
    "gestational_age_weeks_at_registration": 8,
    "danger_sign_reported": 1,
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_low_risk_returns_valid_structure():
    """predict_with_reasons must return required keys with correct types."""
    result = predict_with_reasons(LOW_RISK_INPUT)
    assert "risk_score" in result
    assert "risk_band" in result
    assert "top_reason_codes" in result
    assert 0.0 <= result["risk_score"] <= 1.0
    assert result["risk_band"] in ("low", "medium", "high")
    assert isinstance(result["top_reason_codes"], list)
    assert len(result["top_reason_codes"]) > 0


def test_high_risk_woman_scores_above_threshold():
    """A clearly high-risk woman should score > 0.5 and be in medium or high band."""
    result = predict_with_reasons(HIGH_RISK_INPUT)
    assert result["risk_score"] > 0.5, (
        f"Expected high-risk score > 0.5, got {result['risk_score']}"
    )
    assert result["risk_band"] in ("medium", "high")


def test_high_risk_outscores_low_risk():
    """The high-risk woman must always score higher than the low-risk woman."""
    low = predict_with_reasons(LOW_RISK_INPUT)
    high = predict_with_reasons(HIGH_RISK_INPUT)
    assert high["risk_score"] > low["risk_score"], (
        f"Expected high ({high['risk_score']:.3f}) > low ({low['risk_score']:.3f})"
    )


def test_reason_codes_are_strings():
    """All top_reason_codes must be non-empty strings."""
    result = predict_with_reasons(HIGH_RISK_INPUT)
    for code in result["top_reason_codes"]:
        assert isinstance(code, str), f"Reason code is not a string: {code!r}"
        assert len(code) > 0, "Reason code is an empty string"
