# MAITRI — Maternal AI for Tracking, Risk-prediction and Timely Intervention

> A predict-and-protect continuum of care for antenatal women in the tribal Western Ghats.
> **Hackathon prototype — built on synthetic data.**

---

## Problem Statement

20–30% of pregnancies are classified as high-risk, yet they carry 70–80% of all maternal and neonatal deaths. In the tribal belt of the Western Ghats (Nandurbar, Palghar, Gadchiroli), anaemia prevalence among pregnant women reaches ~70%, compounding risks of postpartum haemorrhage and low birth-weight neonates. Field-level Auxiliary Nurse Midwives (ANMs) operate on paper registers, without decision support, often in areas with no mobile connectivity — meaning deteriorating women are identified late, referrals are delayed, and the continuum of care is broken between registration and day-42 follow-up.

---

## What This Prototype Demonstrates vs. What It Does NOT

### ✅ What it demonstrates (mechanism only)

- End-to-end data flow: offline registration → cloud sync → ML risk prediction → prioritisation → referral tracking → postnatal follow-up
- How a four-model pipeline (registration risk, trajectory re-scoring, prioritisation queue, on-device triage) could coordinate in production
- Offline-first PWA pattern for intermittent connectivity environments via IndexedDB + background sync
- Retrieval-based protocol assistant that answers only from grounded protocol excerpts (no hallucination)

### ❌ What it does NOT do

- Use real patient data — **all training and demo data is fully synthetic**
- Integrate with ABDM/ABHA — mock IDs used throughout; no real health record linkage
- Use satellite connectivity — standard HTTPS assumed
- Constitute a clinical decision-support system or medical device
- Have externally validated, clinically audited, or fairness-reviewed models

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│   React PWA  (Vite + TypeScript + Tailwind + Dexie)      │
│   Pages: Register | Dashboard | WomanDetail |            │
│          ReferralTracker | PostnatalTracker | Assistant   │
└──────────────────┬───────────────────────────────────────┘
                   │  offline-first via Dexie/IndexedDB
                   │  background sync on reconnect (POST /sync)
┌──────────────────▼───────────────────────────────────────┐
│   FastAPI Backend  (Python + SQLAlchemy)                  │
│   /register | /visits | /prioritise | /referral           │
│   /postnatal | /assistant | /sync | /dashboard/summary    │
└───┬─────────────┬─────────────────┬────────────────────-─┘
    │             │                 │
 ┌──▼──┐    ┌─────▼──────┐   ┌─────▼────────────────────┐
 │SQLite│   │ ML Models  │   │ Protocol Assistant        │
 │     │   │ A: XGBoost │   │ sentence-transformers     │
 └─────┘   │ B: Rules   │   │ (all-MiniLM-L6-v2)       │
           │ C: Queue   │   │ + FAISS flat index        │
           │ D: ONNX    │   │ verbatim retrieval only   │
           └────────────┘   └──────────────────────────┘
```

---

## Five Stages → Endpoints + Pages

| Stage | Concept | Endpoint(s) | Frontend Page |
|---|---|---|---|
| **Register** | Offline-first registration with baseline risk | `POST /register`, `POST /sync` | Register |
| **Predict** | Re-score at each follow-up visit | `POST /visits/{id}`, `GET /visits/{id}/visits` | WomanDetail |
| **Prioritise** | Weekly home-visit queue | `GET /prioritise/queue` | Dashboard |
| **Pull** | Referral lifecycle tracking | `POST /referral/{id}/raise`, `POST /referral/{eid}/status`, `GET /referral/open` | ReferralTracker |
| **Persist** | Day-42 postnatal follow-up | `POST /postnatal/{id}/delivery`, `POST /postnatal/contact/{cid}`, `GET /postnatal/due/today` | PostnatalTracker |

---

## Setup Instructions

### Prerequisites

- Python 3.10+
- Node.js 18+
- ~1 GB disk (for sentence-transformers model download on first run)

### Backend Setup

```bash
# 1. Navigate to project root
cd maitri-prototype

# 2. Create and activate virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Generate synthetic training data (creates data/synthetic_antenatal.csv + data/synthetic_visits.csv)
python data/generate_synthetic_data.py

# 5. Train Model A — baseline XGBoost risk classifier
#    (prints AUROC, Brier score; saves models/saved/model_a.pkl)
python models/train_model_a_baseline_risk.py

# 6. Export Model D — ONNX on-device triage model
#    (saves models/saved/model_d_triage.onnx; prints inference timing)
python models/model_d_ondevice_export.py

# 7. Start the backend API
uvicorn backend.main:app --reload
# → API available at http://localhost:8000
# → Interactive docs at http://localhost:8000/docs
```

### Frontend Setup

```bash
# In a new terminal
cd maitri-prototype/frontend
npm install
npm run dev
# → App available at http://localhost:5173
```

> **Note:** The backend must be running before the frontend can fetch live data. The frontend works offline (registration, visit logging) without the backend, using IndexedDB.

---

## Running Tests

```bash
# From project root with venv active
pytest tests/ -v

# Expected output:
# tests/test_model_a.py   — SKIPPED if models/saved/model_a.pkl not found; 4 tests if trained
# tests/test_model_b.py   — 8 tests (no model file required)
# tests/test_model_c.py   — 6 tests (no model file required)
# tests/test_api.py       — 8 integration tests via TestClient
```

---

## Demo Script (3-minute walkthrough for judges)

### Step 1 — Register a high-risk woman
Open the **Register** page. Enter:
- Age: **17**, Parity: **5**, District: **Nandurbar**
- Haemoglobin: **5.8 g/dL**, Systolic BP: **148**, Diastolic BP: **95**
- Obstetric history complications: ✅, Danger sign reported: ✅
- Travel time to FRU: **150 minutes**

Hit Submit. Model A scores her **High Risk** (~0.85) with reason codes such as `['haemoglobin_g_dl', 'systolic_bp', 'danger_sign_reported']`.

### Step 2 — Log a follow-up visit with worsening vitals
Navigate to **Dashboard** → click her name → **Log New Visit**:
- Haemoglobin: **5.0** (drop of 0.8 — triggers `HB_FALLING`)
- Systolic BP: **155** (triggers `HYPERTENSION` + `BP_RISING`)
- Danger sign: ✅

Model B detects `HB_FALLING + SEVERE_ANAEMIA + HYPERTENSION` flags. Risk escalates.

### Step 3 — Prioritisation queue
Return to **Dashboard**. She appears at **#1** in the priority queue, highlighted red, with the highest priority score.

### Step 4 — Raise and track a referral
On her detail page → **Raise Referral** → navigate to **Referral Tracker**.
Walk through the state machine:
1. **Confirm Bed Booked** → status turns blue
2. **Dispatch Ambulance** → status turns orange
3. **Mark Arrived** → status turns green ✅

### Step 5 — Ask the protocol assistant
Navigate to **Assistant** → ask:
> *"What are the danger signs requiring immediate referral?"*

The system retrieves **ANC-05** verbatim and displays it with its source label. No free-text generation — only grounded protocol text.

---

## Model Documentation

### Model A — Baseline Risk (XGBoost Classifier)
**What it predicts:** Probability of high-risk pregnancy at first antenatal registration, from 13 demographic and clinical variables (age, parity, Hb, BMI, BP, obstetric history, travel time, danger sign, gestational age).

**Training data:** Fully synthetic dataset (5,000 women, `data/generate_synthetic_data.py`).

**Output:** `{risk_score: float, risk_band: 'low'|'medium'|'high', top_reason_codes: list[str]}`

**Real-world validation requirements (future work):** AUROC ≥ 0.80 on held-out block-level records from 3+ years of antenatal registers; calibration audit (reliability plot); external validation on ≥1 second district; fairness audit by age, parity, district subgroup; published model card. None of these have been done for this prototype.

---

### Model B — Trajectory Re-scoring (Rule Engine)
**What it predicts:** Updates the risk score at each follow-up visit by detecting deteriorating patterns: Hb falling, BP rising, fundal height stagnation, weight gain below expected, danger signs.

**Note:** This is a **rule-based stand-in** for the production design's longitudinal time-to-event model trained on sequential multi-visit trajectories (e.g., a survival model or LSTM). The rule engine is chosen for prototype explainability — every flag has a transparent threshold and clinical rationale.

---

### Model C — Prioritisation Queue (Deterministic Formula)
**What it predicts:** Ranks all registered women for the weekly home-visit schedule.

`priority_score = current_risk_score × urgency_decay(days_since_last_contact) × distance_weight(travel_time)`

**Note:** This is a **deterministic stand-in** for the pitch's Restless Multi-Armed Bandit (RMAB). A real RMAB would: (1) define a reward signal (observed outcome: Hb improvement, BP normalisation, referral avoided), (2) model each woman as an arm with a Whittle index for index-based policy, (3) learn visit-outcome transition probabilities from historical data, (4) balance exploration vs. exploitation. The deterministic formula is intentionally explainable.

---

### Model D — On-Device Triage (Logistic Regression → ONNX)
**What it predicts:** Same binary high/low risk as Model A, via a lighter logistic regression suitable for on-device deployment.

**Export:** ONNX via `skl2onnx`, loaded with `onnxruntime`. Sub-millisecond inference time on CPU, demonstrating suitability for low-end Android devices via ONNX Runtime Mobile.

**Note:** In production, this would be a quantised XGBoost model validated for accuracy parity with the full Model A, and deployed via a Flutter plugin.

---

## Known Limitations / Real Deployment Requirements

| Limitation | What real deployment needs |
|---|---|
| **ABDM/ABHA integration** | Real ABHA ID creation, Consent Manager API, Health Records linkage |
| **Real clinical data** | 3+ years of block ANC registers, institutional ethics clearance, informed consent framework |
| **Satellite escalation** | VSAT/NB-IoT fallback channel for areas with no mobile signal |
| **DPDP Act compliance** | Data minimisation, consent artefacts, audit log, data residency enforcement |
| **Marathi/Bhili voice interface** | Vernacular ASR + TTS for ANMs; English-only in this prototype |
| **Model validation** | External validation, fairness audit, prospective clinical evaluation |
| **Security** | Authentication (JWT), authorisation (role-based), TLS, field device MDM |
| **Scalability** | Replace SQLite with PostgreSQL; add caching layer for dashboard queries |

---

## License

MIT License — see `LICENSE` file.

## Contributors

[Add team names here]

---

*This is a hackathon prototype built on synthetic data. It is not a medical device and has not been clinically validated. It must not be used with real patient data without ethics clearance, clinical validation, and regulatory approval.*
