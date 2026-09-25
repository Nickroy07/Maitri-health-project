"""
schemas.py — Pydantic v2 request/response schemas for the MAITRI API.

All ORM-backed schemas use ConfigDict(from_attributes=True) so they can be
constructed directly from SQLAlchemy model instances via model_validate().
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Woman schemas
# ---------------------------------------------------------------------------


class WomanCreate(BaseModel):
    """Payload to register a new woman.  All clinical fields required."""

    full_name: str
    age: int
    district: str
    village: str
    phone: Optional[str] = None
    parity: int
    gravida: int
    height_cm: float
    weight_kg: float
    bmi: Optional[float] = None
    haemoglobin_g_dl: float
    systolic_bp: int
    diastolic_bp: int
    obstetric_history_flag: bool = False
    interpregnancy_interval_months: Optional[int] = None
    travel_time_to_frtu_minutes: int
    gestational_age_weeks_at_registration: int
    fundal_height_cm: Optional[float] = None
    danger_sign_reported: bool = False
    # registration_date defaults to utcnow() in the router if not supplied
    registration_date: Optional[datetime] = None


class WomanOut(BaseModel):
    """Full woman record returned after registration or lookup."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    abha_mock_id: str
    full_name: str
    age: int
    district: str
    village: str
    phone: Optional[str]
    parity: int
    gravida: int
    height_cm: float
    weight_kg: float
    bmi: float
    haemoglobin_g_dl: float
    systolic_bp: int
    diastolic_bp: int
    obstetric_history_flag: bool
    interpregnancy_interval_months: Optional[int]
    travel_time_to_frtu_minutes: int
    gestational_age_weeks_at_registration: int
    fundal_height_cm: Optional[float]
    danger_sign_reported: bool
    registration_date: datetime
    baseline_risk_score: Optional[float]
    baseline_risk_band: Optional[str]
    top_reason_codes: Optional[str]   # JSON string
    current_risk_score: Optional[float]
    escalation_flags: Optional[str]   # JSON string
    last_contact_date: Optional[datetime]
    is_synced: bool


class WomanSummary(BaseModel):
    """Lightweight woman record for list / dashboard views."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    full_name: str
    district: str
    village: str
    current_risk_score: Optional[float] = None
    # alias maps the ORM column name to the API field name
    risk_band: Optional[str] = Field(None, alias="baseline_risk_band")
    last_contact_date: Optional[datetime] = None
    travel_time: int = Field(..., alias="travel_time_to_frtu_minutes")


# ---------------------------------------------------------------------------
# Visit schemas
# ---------------------------------------------------------------------------


class VisitCreate(BaseModel):
    """Payload for recording a new ANC / follow-up visit."""

    visit_date: Optional[datetime] = None   # defaults to utcnow() in router
    visit_number: Optional[int] = None      # auto-assigned in router if omitted
    haemoglobin_g_dl: Optional[float] = None
    systolic_bp: Optional[int] = None
    diastolic_bp: Optional[int] = None
    fundal_height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    danger_sign: bool = False


class VisitOut(BaseModel):
    """Full visit record including ML-computed risk update."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    woman_id: str
    visit_date: datetime
    visit_number: int
    haemoglobin_g_dl: Optional[float]
    systolic_bp: Optional[int]
    diastolic_bp: Optional[int]
    fundal_height_cm: Optional[float]
    weight_kg: Optional[float]
    danger_sign: bool
    updated_risk_score: Optional[float]
    escalation_flags: Optional[str]   # JSON string


# ---------------------------------------------------------------------------
# Referral schemas
# ---------------------------------------------------------------------------


class ReferralEventOut(BaseModel):
    """Full referral lifecycle record."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    woman_id: str
    status: str
    raised_at: datetime
    bed_booked_at: Optional[datetime]
    ambulance_dispatched_at: Optional[datetime]
    arrived_at: Optional[datetime]
    lost_at: Optional[datetime]
    notes: Optional[str]
    is_resolved: bool


# ---------------------------------------------------------------------------
# Postnatal schemas
# ---------------------------------------------------------------------------


class PostnatalContactOut(BaseModel):
    """Single postnatal follow-up contact stub."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    woman_id: str
    contact_day: int
    contact_date: Optional[datetime]
    contact_made: bool
    notes: Optional[str]
    delivery_date: Optional[datetime]


# ---------------------------------------------------------------------------
# ML / prioritisation schemas
# ---------------------------------------------------------------------------


class PredictResponse(BaseModel):
    """Output from the risk prediction models."""

    risk_score: Optional[float]
    risk_band: Optional[str]           # 'low' | 'medium' | 'high'
    top_reason_codes: List[str] = []   # human-readable feature labels
    escalation_flags: List[str] = []   # e.g. ['danger_sign', 'severe_anaemia']


class PriorityWoman(BaseModel):
    """Single entry in the CHW outreach priority queue."""

    model_config = ConfigDict(from_attributes=True)

    woman_id: str
    full_name: str
    current_risk_score: Optional[float]
    priority_score: float
    risk_band: Optional[str]
    last_contact_date: Optional[datetime]
    travel_time_minutes: int
    escalation_flags: Optional[str]   # JSON string


# ---------------------------------------------------------------------------
# Sync schemas
# ---------------------------------------------------------------------------


class SyncPayload(BaseModel):
    """Offline-sync bundle pushed from a mobile device."""

    registrations: List[WomanCreate] = []
    visits: List[Dict[str, Any]] = []   # each dict must contain 'woman_id'


# ---------------------------------------------------------------------------
# Dashboard schema
# ---------------------------------------------------------------------------


class DashboardSummary(BaseModel):
    """Top-level counts for the supervisor dashboard."""

    total_registered: int
    high_risk_count: int
    open_referrals: int
    postnatal_due_today: int


# ---------------------------------------------------------------------------
# Assistant schemas
# ---------------------------------------------------------------------------


class AssistantQuery(BaseModel):
    """Free-text clinical query from the CHW."""

    query: str = Field(
        ..., min_length=3, description="Clinical question in natural language"
    )


class AssistantResponse(BaseModel):
    """
    RAG response — always verbatim protocol excerpts, never free-generated text.

    The assistant is strictly retrieval-only: it returns the most relevant
    section(s) from the antenatal protocol document verbatim.
    """

    answer: str           # verbatim excerpt text
    source_excerpt_id: str  # e.g. 'section_3'
    excerpt_label: str    # section heading used as human-readable label
