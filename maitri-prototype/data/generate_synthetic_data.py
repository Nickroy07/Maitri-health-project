"""
generate_synthetic_data.py
==========================
Generates two synthetic datasets for the MAITRI antenatal prototype:

1. synthetic_antenatal.csv  – one row per woman (5 000 rows)
2. synthetic_visits.csv     – longitudinal ANC visit records (4-8 per woman)

Ground-truth `high_risk` label is computed with a transparent, rule-based
weighted-score so the ML model has something meaningful to learn from while
still being explainable to domain experts.

Run:
    python data/generate_synthetic_data.py
"""

import os
import uuid
import json
import random
from datetime import date, timedelta

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------
SEED = 42
rng = np.random.default_rng(SEED)
random.seed(SEED)

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------
THIS_DIR   = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = THIS_DIR  # save inside data/

N = 5_000  # number of synthetic women

DISTRICTS = ["Nandurbar", "Palghar", "Gadchiroli", "Nashik", "Amravati"]
VILLAGES  = [f"Village_{i:04d}" for i in range(1, 501)]


# ===========================================================================
# 1.  CROSS-SECTIONAL TABLE
# ===========================================================================

def build_antenatal_table() -> pd.DataFrame:
    """
    Build the base cross-sectional antenatal dataset.

    Returns
    -------
    pd.DataFrame with one row per woman and all columns described in the
    module docstring.
    """

    # --- Identifiers --------------------------------------------------------
    woman_id = [str(uuid.uuid4()) for _ in range(N)]

    # --- Age: beta distribution right-skewed toward 18-32 ------------------
    # Beta(2, 5) spans [0,1]; scale to [15, 45]
    age_raw = rng.beta(2, 5, N)
    age     = (age_raw * 30 + 15).astype(int)  # maps [0,1] -> [15, 45]

    # --- Parity (0-6, roughly Poisson with lambda=1.2) ---------------------
    parity = np.clip(rng.poisson(1.2, N), 0, 6).astype(int)

    # --- Gravida: parity + 1, occasionally +2 for multiples ----------------
    extra   = rng.choice([0, 1, 2], N, p=[0.80, 0.15, 0.05])
    gravida = (parity + 1 + extra).astype(int)

    # --- Anthropometrics ----------------------------------------------------
    height_cm = rng.normal(152, 6, N).round(1)
    weight_kg = rng.normal(48,  8, N).round(1)
    bmi       = (weight_kg / (height_cm / 100) ** 2).round(2)

    # --- Haemoglobin: mixture model  ----------------------------------------
    # 30 % draw from N(11.5, 1.0) — normal; 70 % from N(8.5, 1.2) — anaemic
    is_normal_hb = rng.random(N) < 0.30
    hb_normal    = rng.normal(11.5, 1.0, N)
    hb_anaemic   = rng.normal(8.5,  1.2, N)
    hb           = np.where(is_normal_hb, hb_normal, hb_anaemic)
    hb           = np.clip(hb, 4.0, 15.0).round(1)

    # --- Blood pressure -----------------------------------------------------
    systolic_bp  = rng.normal(115, 15, N).round(0).astype(int)
    diastolic_bp = rng.normal(75,  10, N).round(0).astype(int)

    # --- Obstetric history flag (~25 % positive) ----------------------------
    obstetric_history_flag = (rng.random(N) < 0.25).astype(int)

    # --- Inter-pregnancy interval (NaN for primigravida) --------------------
    ipi = np.where(
        parity == 0,
        np.nan,
        rng.uniform(12, 48, N).round(0)
    )

    # --- Travel time to FRTU: exponential-ish, capped at 240 min -----------
    # Gamma(shape=1.5, scale=50) gives a right-skewed distribution
    travel_time = np.clip(rng.gamma(1.5, 50, N), 0, 240).round(0).astype(int)

    # --- Gestational age at registration (8-28 weeks) ----------------------
    gest_age = rng.integers(8, 29, N)

    # --- Fundal height: NaN before 20 weeks, otherwise ~ GA - 2 cm --------
    fundal_height = np.where(
        gest_age < 20,
        np.nan,
        (gest_age - rng.uniform(1, 3, N)).round(1)
    )

    # --- Danger sign (~5 %) ------------------------------------------------
    danger_sign_reported = (rng.random(N) < 0.05).astype(int)

    # --- Geography ----------------------------------------------------------
    district     = rng.choice(DISTRICTS, N)
    village_name = rng.choice(VILLAGES,  N)

    df = pd.DataFrame({
        "woman_id":                          woman_id,
        "age":                               age,
        "parity":                            parity,
        "gravida":                           gravida,
        "height_cm":                         height_cm,
        "weight_kg":                         weight_kg,
        "bmi":                               bmi,
        "haemoglobin_g_dl":                  hb,
        "systolic_bp":                       systolic_bp,
        "diastolic_bp":                      diastolic_bp,
        "obstetric_history_flag":            obstetric_history_flag,
        "interpregnancy_interval_months":    ipi,
        "travel_time_to_frtu_minutes":       travel_time,
        "gestational_age_weeks_at_registration": gest_age,
        "fundal_height_cm":                  fundal_height,
        "danger_sign_reported":              danger_sign_reported,
        "district":                          district,
        "village_name":                      village_name,
    })

    return df


def compute_risk_score(df: pd.DataFrame) -> pd.Series:
    """
    Transparent, weighted rule-based risk score.

    Scoring rubric
    --------------
    +3  age < 18 or age > 35          (adolescent / advanced maternal age)
    +3  parity > 4                    (grand multiparity)
    +2  bmi < 18.5                    (underweight)
    +4  haemoglobin < 7.0             (severe anaemia)
    +2  haemoglobin < 9.0             (moderate anaemia; cumulative with +4)
    +3  systolic >= 140 or diastolic >= 90  (hypertension)
    +3  obstetric_history_flag == 1   (previous complications)
    +2  danger_sign_reported == 1     (active warning sign)
    +1  travel_time > 90 min          (access barrier)

    Parameters
    ----------
    df : pd.DataFrame
        Must contain all scored columns.

    Returns
    -------
    pd.Series of integer risk scores.
    """
    score = pd.Series(0, index=df.index)

    score += 3 * ((df["age"] < 18) | (df["age"] > 35)).astype(int)
    score += 3 * (df["parity"] > 4).astype(int)
    score += 2 * (df["bmi"] < 18.5).astype(int)
    score += 4 * (df["haemoglobin_g_dl"] < 7.0).astype(int)
    score += 2 * (df["haemoglobin_g_dl"] < 9.0).astype(int)   # cumulative
    score += 3 * ((df["systolic_bp"] >= 140) | (df["diastolic_bp"] >= 90)).astype(int)
    score += 3 * (df["obstetric_history_flag"] == 1).astype(int)
    score += 2 * (df["danger_sign_reported"] == 1).astype(int)
    score += 1 * (df["travel_time_to_frtu_minutes"] > 90).astype(int)

    return score


def binarize_with_noise(score: pd.Series, threshold: int = 4,
                         noise_rate: float = 0.10) -> np.ndarray:
    """
    Convert continuous score to binary label with label noise.

    ~10 % of labels are randomly flipped to prevent perfect separability
    and simulate real-world annotation uncertainty.

    Parameters
    ----------
    score       : risk score Series
    threshold   : score >= threshold -> high_risk = 1
    noise_rate  : fraction of labels to randomly flip

    Returns
    -------
    np.ndarray of int (0/1)
    """
    labels = (score >= threshold).astype(int).values.copy()
    n_flip = int(noise_rate * len(labels))
    flip_idx = rng.choice(len(labels), size=n_flip, replace=False)
    labels[flip_idx] = 1 - labels[flip_idx]  # flip 0->1 or 1->0
    return labels


# ===========================================================================
# 2.  LONGITUDINAL VISITS TABLE
# ===========================================================================

def build_visits_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate 4-8 ANC visit records per woman.

    Each visit drifts the clinical measurements by a small random delta to
    simulate realistic longitudinal trajectories.

    Parameters
    ----------
    df : base antenatal DataFrame (must include woman_id and all measurement
         columns used as starting values)

    Returns
    -------
    pd.DataFrame with one row per visit.
    """
    registration_start = date(2024, 1, 1)
    registration_end   = date(2024, 6, 30)
    reg_range_days     = (registration_end - registration_start).days

    records = []

    for _, row in df.iterrows():
        n_visits = rng.integers(4, 9)  # 4 to 8 visits inclusive

        # Registration date: random within Jan-Jun 2024
        reg_offset  = rng.integers(0, reg_range_days + 1)
        visit_date  = registration_start + timedelta(days=int(reg_offset))

        # Starting values from baseline record
        hb      = float(row["haemoglobin_g_dl"])
        sys_bp  = float(row["systolic_bp"])
        dia_bp  = float(row["diastolic_bp"])
        weight  = float(row["weight_kg"])
        fh      = row["fundal_height_cm"]  # may be NaN
        gest    = int(row["gestational_age_weeks_at_registration"])

        for visit_num in range(1, n_visits + 1):
            # Small random drift per visit
            hb     = np.clip(hb + rng.uniform(-0.5, 0.5), 4.0, 15.0)
            sys_bp = np.clip(sys_bp + rng.uniform(-5, 5), 70, 200)
            dia_bp = np.clip(dia_bp + rng.uniform(-5, 5), 40, 130)
            weight = weight + 0.5 + rng.uniform(-0.2, 0.4)  # gain ~0.5 kg/visit

            # Fundal height grows ~1 cm/week if past 20 weeks
            weeks_elapsed = (visit_num - 1) * rng.uniform(3, 5)
            current_gest  = gest + weeks_elapsed
            if current_gest >= 20:
                if np.isnan(fh) if isinstance(fh, float) else fh is None:
                    fh = current_gest - rng.uniform(1, 3)  # initialise
                else:
                    fh = fh + rng.uniform(0.5, 1.5)  # grow
                fh = round(float(fh), 1)
                fh_val = fh
            else:
                fh_val = None  # still pre-20 weeks

            danger = int(rng.random() < 0.05)

            records.append({
                "woman_id":          row["woman_id"],
                "visit_number":      visit_num,
                "visit_date":        visit_date.isoformat(),
                "haemoglobin_g_dl":  round(float(hb), 1),
                "systolic_bp":       int(round(sys_bp)),
                "diastolic_bp":      int(round(dia_bp)),
                "fundal_height_cm":  fh_val,
                "weight_kg":         round(float(weight), 1),
                "danger_sign":       danger,
            })

            # Advance date by 3-5 weeks for next visit
            visit_date += timedelta(weeks=int(rng.integers(3, 6)))

    return pd.DataFrame(records)


# ===========================================================================
# 3.  SUMMARY STATISTICS
# ===========================================================================

def print_summary(df: pd.DataFrame, visits: pd.DataFrame) -> None:
    """Print key descriptive statistics after data generation."""
    print("\n" + "=" * 60)
    print("SYNTHETIC DATA SUMMARY")
    print("=" * 60)
    print(f"Antenatal table shape : {df.shape}")
    print(f"Visits table shape    : {visits.shape}")
    print(f"High-risk rate        : {df['high_risk'].mean():.2%}")
    print(f"Mean Haemoglobin      : {df['haemoglobin_g_dl'].mean():.2f} g/dL")
    print(f"% Hb < 7.0 (severe)  : {(df['haemoglobin_g_dl'] < 7.0).mean():.2%}")
    print(f"% Hb < 9.0 (moderate): {(df['haemoglobin_g_dl'] < 9.0).mean():.2%}")
    print(f"Mean age              : {df['age'].mean():.1f} years")
    print(f"% Hypertensive        : {((df['systolic_bp'] >= 140) | (df['diastolic_bp'] >= 90)).mean():.2%}")
    print(f"Mean travel time      : {df['travel_time_to_frtu_minutes'].mean():.0f} min")
    print(f"District distribution:\n{df['district'].value_counts()}")
    print("=" * 60 + "\n")


# ===========================================================================
# 4.  MAIN
# ===========================================================================

if __name__ == "__main__":
    print("Building antenatal cross-sectional table ...")
    antenatal_df = build_antenatal_table()

    print("Computing risk scores ...")
    raw_score             = compute_risk_score(antenatal_df)
    antenatal_df["high_risk"] = binarize_with_noise(raw_score)

    print("Building longitudinal visits table ...")
    visits_df = build_visits_table(antenatal_df)

    # Save outputs
    antenatal_path = os.path.join(OUTPUT_DIR, "synthetic_antenatal.csv")
    visits_path    = os.path.join(OUTPUT_DIR, "synthetic_visits.csv")

    antenatal_df.to_csv(antenatal_path, index=False)
    visits_df.to_csv(visits_path,    index=False)

    print(f"Saved: {antenatal_path}")
    print(f"Saved: {visits_path}")

    print_summary(antenatal_df, visits_df)
