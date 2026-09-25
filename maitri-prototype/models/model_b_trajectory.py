"""
model_b_trajectory.py
=====================
Longitudinal trajectory risk re-scorer for MAITRI.

This module exposes a single public function:

    recompute_trajectory_risk(woman_history, baseline_score) -> dict

It scans a woman's sequence of ANC visit records, detects clinical
escalation patterns, and returns an updated risk score.

Design note
-----------
This is a **rule-based stand-in** for a longitudinal time-to-event model.
A production system would:
  - Fit a survival model (e.g., cause-specific Cox / DeepHit) on
    historical visit data to predict probability of adverse outcome
    (haemorrhage, eclampsia, stillbirth) within the next N weeks.
  - Feed raw time-series through an LSTM / GRU encoder to capture
    trajectory shape beyond pairwise differences.
  - The escalation multiplier approach here is interpretable and safe for
    the prototype but will under- and over-flag in ways a trained model
    would not.

Usage
-----
    from models.model_b_trajectory import recompute_trajectory_risk
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Constants: escalation multiplier increments
# ---------------------------------------------------------------------------
_MULTIPLIER_INCREMENTS: dict[str, float] = {
    "DANGER_SIGN":        0.4,
    "SEVERE_ANAEMIA":     0.3,
    "HYPERTENSION":       0.3,
    "BP_RISING":          0.2,
    "HB_FALLING":         0.2,
    "GROWTH_RESTRICTED":  0.2,
    "LOW_WEIGHT_GAIN":    0.1,
}


# ===========================================================================
# Internal detection helpers
# ===========================================================================

def _parse_date(date_str: str) -> datetime:
    """Parse an ISO-format date string to a datetime object."""
    return datetime.fromisoformat(date_str)


def _detect_hb_falling(visits: list[dict]) -> bool:
    """
    Detect if haemoglobin drops > 1.0 g/dL between any two consecutive visits.

    Returns True if the condition is met, False otherwise.
    """
    for i in range(1, len(visits)):
        prev_hb = visits[i - 1].get("haemoglobin_g_dl")
        curr_hb = visits[i].get("haemoglobin_g_dl")
        if prev_hb is not None and curr_hb is not None:
            if (prev_hb - curr_hb) > 1.0:
                return True
    return False


def _detect_severe_anaemia(visits: list[dict]) -> bool:
    """Return True if any visit has Hb < 7.0 g/dL."""
    return any(
        v.get("haemoglobin_g_dl") is not None and v["haemoglobin_g_dl"] < 7.0
        for v in visits
    )


def _detect_bp_rising(visits: list[dict]) -> bool:
    """
    Return True if systolic rises > 20 mmHg from first visit, OR if any
    single reading meets the hypertension threshold (140/90).
    """
    first_sys = visits[0].get("systolic_bp") if visits else None
    for v in visits:
        sys = v.get("systolic_bp")
        dia = v.get("diastolic_bp")
        # Hypertension threshold criterion
        if sys is not None and dia is not None:
            if sys >= 140 or dia >= 90:
                return True
        # Relative rise from first visit
        if first_sys is not None and sys is not None:
            if (sys - first_sys) > 20:
                return True
    return False


def _detect_hypertension(visits: list[dict]) -> bool:
    """Return True if any visit has systolic >= 140 or diastolic >= 90."""
    return any(
        (v.get("systolic_bp") is not None and v["systolic_bp"] >= 140) or
        (v.get("diastolic_bp") is not None and v["diastolic_bp"] >= 90)
        for v in visits
    )


def _detect_growth_restricted(visits: list[dict]) -> bool:
    """
    Return True if fundal height is flat or decreasing across two consecutive
    visits where both fundal height values are non-null.

    Flat is defined as <= 0 cm change (no growth).
    """
    for i in range(1, len(visits)):
        prev_fh = visits[i - 1].get("fundal_height_cm")
        curr_fh = visits[i].get("fundal_height_cm")
        if prev_fh is not None and curr_fh is not None:
            if (curr_fh - prev_fh) <= 0:
                return True
    return False


def _detect_low_weight_gain(visits: list[dict]) -> bool:
    """
    Return True if total weight gain is < 2 kg across visits spanning >= 8 weeks.

    Uses first and last visits with a non-null weight and a parseable date.
    """
    weight_date_pairs: list[tuple[datetime, float]] = []
    for v in visits:
        w  = v.get("weight_kg")
        dt = v.get("visit_date")
        if w is not None and dt is not None:
            try:
                weight_date_pairs.append((_parse_date(dt), float(w)))
            except ValueError:
                pass  # skip unparseable dates gracefully

    if len(weight_date_pairs) < 2:
        return False

    weight_date_pairs.sort(key=lambda x: x[0])  # sort chronologically
    first_dt, first_w = weight_date_pairs[0]
    last_dt,  last_w  = weight_date_pairs[-1]

    span_weeks = (last_dt - first_dt).days / 7.0
    weight_gain = last_w - first_w

    return span_weeks >= 8 and weight_gain < 2.0


def _detect_danger_sign(visits: list[dict]) -> bool:
    """Return True if any visit has danger_sign == 1."""
    return any(v.get("danger_sign") == 1 for v in visits)


# ===========================================================================
# Public API
# ===========================================================================

def recompute_trajectory_risk(
    woman_history: list[dict],
    baseline_score: float,
) -> dict:
    """
    Re-score maternal risk using longitudinal ANC visit trajectory.

    This is a **rule-based stand-in** for a longitudinal time-to-event model.
    A production MAITRI system would replace the multiplier logic here with:
      - A survival model predicting probability of adverse outcome
        within the next N weeks, conditioned on the trajectory.
      - Per-visit SHAP attribution to explain which visits drove the change.

    Parameters
    ----------
    woman_history : list[dict]
        Ordered list of ANC visit records. Each dict may contain:
          - haemoglobin_g_dl : float | None
          - systolic_bp      : int | None
          - diastolic_bp     : int | None
          - fundal_height_cm : float | None
          - weight_kg        : float | None
          - danger_sign      : int   (0 or 1)
          - visit_date       : str   (ISO-8601 date, e.g. '2024-03-15')

    baseline_score : float
        The Model A risk score for this woman [0, 1].

    Returns
    -------
    dict:
        updated_risk_score : float -- baseline_score x multiplier, capped at 1.0
        escalation_flags   : list[str] -- active escalation condition codes
        baseline_score     : float -- the original score passed in

    Raises
    ------
    ValueError
        If woman_history is empty or baseline_score is outside [0, 1].
    """
    if not woman_history:
        raise ValueError("woman_history must contain at least one visit record.")
    if not (0.0 <= baseline_score <= 1.0):
        raise ValueError(f"baseline_score must be in [0, 1]; got {baseline_score}")

    # Sort visits chronologically (defensive; caller may not guarantee order)
    def _sort_key(v: dict) -> datetime:
        try:
            return _parse_date(v["visit_date"])
        except (KeyError, ValueError):
            return datetime.min

    visits = sorted(woman_history, key=_sort_key)

    # --- Detect escalation conditions --------------------------------------
    flags: list[str] = []

    if _detect_hb_falling(visits):
        flags.append("HB_FALLING")
    if _detect_severe_anaemia(visits):
        flags.append("SEVERE_ANAEMIA")
    if _detect_bp_rising(visits):
        flags.append("BP_RISING")
    if _detect_hypertension(visits):
        flags.append("HYPERTENSION")
    if _detect_growth_restricted(visits):
        flags.append("GROWTH_RESTRICTED")
    if _detect_low_weight_gain(visits):
        flags.append("LOW_WEIGHT_GAIN")
    if _detect_danger_sign(visits):
        flags.append("DANGER_SIGN")

    # --- Compute escalation multiplier ------------------------------------
    multiplier = 1.0
    for flag in flags:
        multiplier += _MULTIPLIER_INCREMENTS.get(flag, 0.0)

    # Cap the updated score at 1.0
    updated_score = min(baseline_score * multiplier, 1.0)

    return {
        "updated_risk_score": round(updated_score, 4),
        "escalation_flags":   flags,
        "baseline_score":     round(baseline_score, 4),
    }


# ===========================================================================
# Example usage
# ===========================================================================

if __name__ == "__main__":
    import json

    print("=== Model B -- Trajectory Risk Re-Scorer ===\n")

    # Scenario: woman with deteriorating Hb and elevated BP
    example_history = [
        {
            "visit_date":        "2024-02-01",
            "haemoglobin_g_dl":  9.2,
            "systolic_bp":       118,
            "diastolic_bp":      76,
            "fundal_height_cm":  22.0,
            "weight_kg":         47.5,
            "danger_sign":       0,
        },
        {
            "visit_date":        "2024-02-22",
            "haemoglobin_g_dl":  7.8,    # dropping
            "systolic_bp":       132,
            "diastolic_bp":      84,
            "fundal_height_cm":  25.0,
            "weight_kg":         47.8,
            "danger_sign":       0,
        },
        {
            "visit_date":        "2024-03-15",
            "haemoglobin_g_dl":  6.5,    # severe anaemia
            "systolic_bp":       148,    # hypertension
            "diastolic_bp":      95,
            "fundal_height_cm":  25.2,   # nearly flat -- growth restricted?
            "weight_kg":         48.0,
            "danger_sign":       1,      # danger sign active
        },
    ]

    result = recompute_trajectory_risk(
        woman_history=example_history,
        baseline_score=0.45,
    )

    print("Input baseline score : 0.45")
    print("Result:")
    print(json.dumps(result, indent=2))

    # Scenario: stable woman (no escalation expected)
    stable_history = [
        {
            "visit_date":        "2024-03-01",
            "haemoglobin_g_dl":  11.0,
            "systolic_bp":       112,
            "diastolic_bp":      72,
            "fundal_height_cm":  28.0,
            "weight_kg":         52.0,
            "danger_sign":       0,
        },
        {
            "visit_date":        "2024-03-22",
            "haemoglobin_g_dl":  11.2,
            "systolic_bp":       110,
            "diastolic_bp":      70,
            "fundal_height_cm":  30.0,
            "weight_kg":         52.6,
            "danger_sign":       0,
        },
    ]

    stable_result = recompute_trajectory_risk(
        woman_history=stable_history,
        baseline_score=0.15,
    )

    print("\nStable scenario (baseline 0.15):")
    print(json.dumps(stable_result, indent=2))
