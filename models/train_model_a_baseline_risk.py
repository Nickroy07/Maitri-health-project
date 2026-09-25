"""
train_model_a_baseline_risk.py
===============================
Trains the MAITRI baseline antenatal risk classifier (Model A).

Model: XGBoostClassifier
Target: high_risk (binary, ~22 % positive)

Outputs (all written to models/saved/):
  - model_a.pkl            -- serialised model (joblib)
  - model_a_features.json  -- ordered feature list consumed by the API
  - model_a_calibration.png -- reliability diagram

Usage
-----
    # Train and evaluate (only when run as main script)
    python models/train_model_a_baseline_risk.py

    # Import prediction function into FastAPI backend
    from models.train_model_a_baseline_risk import predict_with_reasons
"""

from __future__ import annotations

import json
import os
import time
from typing import Optional

import joblib
import matplotlib
matplotlib.use("Agg")          # headless backend for servers / CI
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------
THIS_DIR    = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT   = os.path.dirname(THIS_DIR)          # maitri-prototype/
DATA_PATH   = os.path.join(REPO_ROOT, "data", "synthetic_antenatal.csv")
SAVED_DIR   = os.path.join(THIS_DIR, "saved")
MODEL_PATH  = os.path.join(SAVED_DIR, "model_a.pkl")
FEAT_PATH   = os.path.join(SAVED_DIR, "model_a_features.json")
CALIB_PATH  = os.path.join(SAVED_DIR, "model_a_calibration.png")

os.makedirs(SAVED_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Feature specification
# ---------------------------------------------------------------------------
FEATURES: list[str] = [
    "age",
    "parity",
    "gravida",
    "height_cm",
    "weight_kg",
    "bmi",
    "haemoglobin_g_dl",
    "systolic_bp",
    "diastolic_bp",
    "obstetric_history_flag",
    "travel_time_to_frtu_minutes",
    "gestational_age_weeks_at_registration",
    "danger_sign_reported",
]

TARGET = "high_risk"

# ---------------------------------------------------------------------------
# Module-level model cache (used by predict_with_reasons)
# ---------------------------------------------------------------------------
_cached_model:    Optional[XGBClassifier] = None
_cached_features: Optional[list[str]]    = None


# ===========================================================================
# Helper utilities
# ===========================================================================

def load_data() -> pd.DataFrame:
    """Load and lightly pre-process the antenatal CSV."""
    df = pd.read_csv(DATA_PATH)

    # Fill NaN with column medians so the model never sees missing values
    for col in FEATURES:
        if col in df.columns and df[col].isna().any():
            df[col] = df[col].fillna(df[col].median())

    return df


def save_calibration_plot(y_true: np.ndarray, y_prob: np.ndarray) -> None:
    """
    Save a reliability diagram (calibration curve) as a PNG.

    A well-calibrated model will have its curve close to the diagonal.
    """
    frac_pos, mean_pred = calibration_curve(y_true, y_prob, n_bins=10)

    fig, ax = plt.subplots(figsize=(6, 5))
    ax.plot(mean_pred, frac_pos, "s-", label="XGBoost (Model A)", color="#2563EB")
    ax.plot([0, 1], [0, 1], "--", color="grey", label="Perfect calibration")
    ax.set_xlabel("Mean predicted probability")
    ax.set_ylabel("Fraction of positives")
    ax.set_title("Model A -- Calibration Curve")
    ax.legend()
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(CALIB_PATH, dpi=150)
    plt.close(fig)
    print(f"Calibration plot saved -> {CALIB_PATH}")


def print_shap_importance(model: XGBClassifier, feature_names: list[str]) -> None:
    """
    Print top-5 feature importances.

    Uses the XGBoost built-in 'gain' importance (sum of gain across splits).
    SHAP values would give per-prediction explanations in production -- this
    is the global proxy used in the prototype.
    """
    try:
        import shap  # type: ignore
        # shap.TreeExplainer gives per-prediction SHAP values in production.
        # For the prototype we fall through to the faster built-in importances.
        raise ImportError("Using built-in importances for prototype speed.")
    except Exception:
        pass

    # XGBoost built-in: 'gain' represents average gain of splits
    scores  = model.get_booster().get_score(importance_type="gain")
    paired  = [(scores.get(f, 0), f) for f in feature_names]
    paired.sort(reverse=True)

    print("\nTop-5 features by XGBoost gain importance:")
    for score, feat in paired[:5]:
        print(f"  {feat:<45s} {score:>10.2f}")


# ===========================================================================
# Training entry point
# ===========================================================================

def train_and_evaluate() -> None:
    """Full training pipeline: load -> split -> fit -> evaluate -> save."""

    print("Loading data ...")
    df = load_data()

    X = df[FEATURES]
    y = df[TARGET]

    # --- Train / test split (stratified to preserve class balance) ----------
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )
    print(f"Train size: {len(X_train)} | Test size: {len(X_test)}")
    print(f"Positive rate -- train: {y_train.mean():.2%} | test: {y_test.mean():.2%}")

    # --- Model --------------------------------------------------------------
    model = XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.1,
        eval_metric="logloss",
        use_label_encoder=False,   # suppresses deprecation warning in older XGBoost
        random_state=42,
        n_jobs=-1,
    )

    print("Training XGBoost ...")
    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=False,
    )

    # --- Evaluation ---------------------------------------------------------
    y_prob = model.predict_proba(X_test)[:, 1]

    auroc  = roc_auc_score(y_test, y_prob)
    brier  = brier_score_loss(y_test, y_prob)
    print(f"\nAUROC      : {auroc:.4f}")
    print(f"Brier Score: {brier:.4f}")

    save_calibration_plot(y_test.values, y_prob)
    print_shap_importance(model, FEATURES)

    # --- Persist artefacts --------------------------------------------------
    joblib.dump(model, MODEL_PATH)
    print(f"\nModel saved -> {MODEL_PATH}")

    with open(FEAT_PATH, "w", encoding="utf-8") as fh:
        json.dump(FEATURES, fh, indent=2)
    print(f"Features saved -> {FEAT_PATH}")


# ===========================================================================
# Prediction API (importable by FastAPI backend)
# ===========================================================================

def _load_model_cached() -> tuple[XGBClassifier, list[str]]:
    """
    Lazy-load the trained model from disk into module-level cache.

    Returns
    -------
    (model, feature_names)
    """
    global _cached_model, _cached_features
    if _cached_model is None:
        _cached_model    = joblib.load(MODEL_PATH)
        with open(FEAT_PATH, encoding="utf-8") as fh:
            _cached_features = json.load(fh)
    return _cached_model, _cached_features


def predict_with_reasons(input_dict: dict) -> dict:
    """
    Predict maternal risk and return human-readable reason codes.

    Parameters
    ----------
    input_dict : dict
        Keys must include all features in FEATURES.  Missing keys are
        filled with the column median learned at training time (placeholder
        approach; production would use imputer stored alongside model).

    Returns
    -------
    dict with:
        risk_score      : float [0, 1]
        risk_band       : 'low' | 'medium' | 'high'
        top_reason_codes: list[str] -- top 3 feature names by global XGBoost
                          importance.  In production, per-prediction SHAP
                          values would replace this global proxy.
    """
    model, features = _load_model_cached()

    # Build a single-row DataFrame in the exact feature order the model expects
    row = {feat: input_dict.get(feat, np.nan) for feat in features}
    X   = pd.DataFrame([row], columns=features)

    # Fill any remaining NaN with 0 (safe default for prototype)
    X = X.fillna(0)

    risk_score = float(model.predict_proba(X)[0, 1])

    # Risk band thresholds
    if risk_score < 0.33:
        risk_band = "low"
    elif risk_score <= 0.66:
        risk_band = "medium"
    else:
        risk_band = "high"

    # --- Top-3 reason codes (global importances as prototype proxy) ---------
    # NOTE: In production, replace this with per-prediction SHAP values so
    #       each woman receives an individualised explanation.
    scores = model.get_booster().get_score(importance_type="gain")
    paired = sorted([(scores.get(f, 0), f) for f in features], reverse=True)
    top_reason_codes = [feat for _, feat in paired[:3]]

    return {
        "risk_score":       risk_score,
        "risk_band":        risk_band,
        "top_reason_codes": top_reason_codes,
    }


# ===========================================================================
# Main guard
# ===========================================================================

if __name__ == "__main__":
    train_and_evaluate()

    # Quick smoke-test of the prediction function
    print("\n--- Smoke-test predict_with_reasons ---")
    sample = {
        "age": 17,
        "parity": 0,
        "gravida": 1,
        "height_cm": 148,
        "weight_kg": 40,
        "bmi": 18.3,
        "haemoglobin_g_dl": 6.5,
        "systolic_bp": 145,
        "diastolic_bp": 95,
        "obstetric_history_flag": 1,
        "travel_time_to_frtu_minutes": 120,
        "gestational_age_weeks_at_registration": 22,
        "danger_sign_reported": 1,
    }
    result = predict_with_reasons(sample)
    print(json.dumps(result, indent=2))
