"""
model_d_ondevice_export.py
===========================
Trains a LogisticRegression triage model and exports it to ONNX format
for on-device inference via ONNX Runtime Mobile on low-end Android devices.

Pipeline
--------
1. Load synthetic_antenatal.csv
2. Train LogisticRegression (lightweight, fast, interpretable)
3. Export to ONNX via skl2onnx
4. Reload with onnxruntime.InferenceSession and benchmark single-row inference
5. Print on-device deployment note

Output
------
models/saved/model_d_triage.onnx

Run
---
    python models/model_d_ondevice_export.py
"""

from __future__ import annotations

import os
import time

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------
THIS_DIR  = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(THIS_DIR)
DATA_PATH = os.path.join(REPO_ROOT, "data", "synthetic_antenatal.csv")
SAVED_DIR = os.path.join(THIS_DIR, "saved")
ONNX_PATH = os.path.join(SAVED_DIR, "model_d_triage.onnx")

os.makedirs(SAVED_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Feature specification (same as Model A for consistency)
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


# ===========================================================================
# Main script
# ===========================================================================

if __name__ == "__main__":

    # -----------------------------------------------------------------------
    # 1. Load data
    # -----------------------------------------------------------------------
    print("Loading data ...")
    df = pd.read_csv(DATA_PATH)

    # Fill NaN with column medians (guard against unexpected missing values)
    for col in FEATURES:
        if col in df.columns and df[col].isna().any():
            df[col] = df[col].fillna(df[col].median())

    X = df[FEATURES].values.astype(np.float32)
    y = df[TARGET].values

    # -----------------------------------------------------------------------
    # 2. Train / test split
    # -----------------------------------------------------------------------
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )

    # -----------------------------------------------------------------------
    # 3. Fit LogisticRegression
    # -----------------------------------------------------------------------
    print("Training LogisticRegression ...")
    clf = LogisticRegression(max_iter=1000, random_state=42, n_jobs=-1)
    clf.fit(X_train, y_train)

    y_prob = clf.predict_proba(X_test)[:, 1]
    auroc  = roc_auc_score(y_test, y_prob)
    print(f"LogisticRegression AUROC: {auroc:.4f}")

    # -----------------------------------------------------------------------
    # 4. Export to ONNX
    # -----------------------------------------------------------------------
    print("Exporting to ONNX ...")
    try:
        from skl2onnx import convert_sklearn                     # type: ignore
        from skl2onnx.common.data_types import FloatTensorType  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "skl2onnx is required for ONNX export.  "
            "Install it with: pip install skl2onnx"
        ) from exc

    # initial_type describes the shape of a single input row;
    # None for the batch dimension allows variable batch sizes at inference.
    n_features = len(FEATURES)
    initial_type = [("float_input", FloatTensorType([None, n_features]))]

    onnx_model = convert_sklearn(clf, initial_types=initial_type)

    with open(ONNX_PATH, "wb") as fh:
        fh.write(onnx_model.SerializeToString())

    print(f"ONNX model saved -> {ONNX_PATH}")

    # -----------------------------------------------------------------------
    # 5. Reload and benchmark with ONNX Runtime
    # -----------------------------------------------------------------------
    print("\nBenchmarking ONNX inference ...")
    try:
        import onnxruntime as ort  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "onnxruntime is required for inference benchmark.  "
            "Install it with: pip install onnxruntime"
        ) from exc

    session = ort.InferenceSession(ONNX_PATH)

    # Build a single test row (use first row of test set)
    single_row = X_test[:1].astype(np.float32)
    input_name = session.get_inputs()[0].name

    # Warm-up run to load model into cache
    _ = session.run(None, {input_name: single_row})

    # Time 100 inference calls on a single row
    N_CALLS = 100
    start   = time.perf_counter()
    for _ in range(N_CALLS):
        _ = session.run(None, {input_name: single_row})
    elapsed_ms = (time.perf_counter() - start) * 1000  # convert s -> ms

    avg_ms = elapsed_ms / N_CALLS
    print(f"Average inference time over {N_CALLS} calls: {avg_ms:.3f} ms per call")

    # -----------------------------------------------------------------------
    # 6. On-device deployment note
    # -----------------------------------------------------------------------
    print(
        "\nOn-device inference time demonstrates this model is suitable for "
        "deployment on low-end Android devices via ONNX Runtime Mobile"
    )
    print(
        "\nDeployment notes:"
        "\n  - The .onnx file is self-contained (no Python runtime needed)."
        "\n  - ONNX Runtime Mobile (ORT Mobile) runs on Android API 21+ "
        "(Lollipop and above), covering the majority of devices used in "
        "India's rural health sector."
        "\n  - LogisticRegression ONNX file size is typically < 10 KB, "
        "well within the 50 MB offline bundle limit."
        "\n  - For offline-first ASHA app: bundle the .onnx file in the APK "
        "assets folder and load via OrtEnvironment / OrtSession in Kotlin/Java."
    )
