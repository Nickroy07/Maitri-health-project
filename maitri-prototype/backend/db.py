"""
db.py — SQLAlchemy ORM models and database session management for MAITRI.

Uses SQLite via a relative path derived from this file's location so the
database file always lands next to db.py regardless of the working directory.
"""

import os
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# ---------------------------------------------------------------------------
# Database URL — resolve absolute path so SQLite can always find the file
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = f"sqlite:///{os.path.join(_HERE, 'maitri.db')}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # required for SQLite + threaded FastAPI
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------


class Woman(Base):
    """
    Core registration record for a pregnant / postnatal woman.

    Risk-related columns (baseline_risk_score, current_risk_score, etc.) are
    populated after the ML models run and may be NULL until then.
    top_reason_codes and escalation_flags are stored as JSON strings so the
    table stays schema-simple while preserving structured data.
    """

    __tablename__ = "women"

    id = Column(String, primary_key=True, index=True)
    abha_mock_id = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    age = Column(Integer, nullable=False)
    district = Column(String, nullable=False)
    village = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    parity = Column(Integer, nullable=False)
    gravida = Column(Integer, nullable=False)
    height_cm = Column(Float, nullable=False)
    weight_kg = Column(Float, nullable=False)
    bmi = Column(Float, nullable=False)
    haemoglobin_g_dl = Column(Float, nullable=False)
    systolic_bp = Column(Integer, nullable=False)
    diastolic_bp = Column(Integer, nullable=False)
    obstetric_history_flag = Column(Boolean, nullable=False, default=False)
    interpregnancy_interval_months = Column(Integer, nullable=True)
    travel_time_to_frtu_minutes = Column(Integer, nullable=False)
    gestational_age_weeks_at_registration = Column(Integer, nullable=False)
    fundal_height_cm = Column(Float, nullable=True)
    danger_sign_reported = Column(Boolean, nullable=False, default=False)
    registration_date = Column(DateTime, nullable=False, default=datetime.utcnow)

    # ML output columns — populated asynchronously after model inference
    baseline_risk_score = Column(Float, nullable=True)
    baseline_risk_band = Column(String, nullable=True)   # 'low'|'medium'|'high'
    top_reason_codes = Column(String, nullable=True)     # JSON string list
    current_risk_score = Column(Float, nullable=True)
    escalation_flags = Column(String, nullable=True)     # JSON string list

    last_contact_date = Column(DateTime, nullable=True)

    # Offline-sync bookkeeping
    is_synced = Column(Boolean, nullable=False, default=True)

    # ORM relationships
    visits = relationship("Visit", back_populates="woman", cascade="all, delete-orphan")
    referral_events = relationship(
        "ReferralEvent", back_populates="woman", cascade="all, delete-orphan"
    )
    postnatal_contacts = relationship(
        "PostnatalContact", back_populates="woman", cascade="all, delete-orphan"
    )


class Visit(Base):
    """
    A single ANC or follow-up visit for a registered woman.

    risk_score and escalation_flags here reflect the model's output at the
    time of this specific visit, preserving the trajectory over time.
    """

    __tablename__ = "visits"

    id = Column(String, primary_key=True, index=True)
    woman_id = Column(String, ForeignKey("women.id"), nullable=False, index=True)
    visit_date = Column(DateTime, nullable=False, default=datetime.utcnow)
    visit_number = Column(Integer, nullable=False)
    haemoglobin_g_dl = Column(Float, nullable=True)
    systolic_bp = Column(Integer, nullable=True)
    diastolic_bp = Column(Integer, nullable=True)
    fundal_height_cm = Column(Float, nullable=True)
    weight_kg = Column(Float, nullable=True)
    danger_sign = Column(Boolean, nullable=False, default=False)
    updated_risk_score = Column(Float, nullable=True)
    escalation_flags = Column(String, nullable=True)  # JSON string list

    woman = relationship("Woman", back_populates="visits")


class ReferralEvent(Base):
    """
    Tracks the full lifecycle of a referral from initial raise to resolution.

    State machine: raised → bed_booked → ambulance_dispatched → arrived | lost
    Each state transition timestamp is stored for audit / analytics.
    """

    __tablename__ = "referral_events"

    id = Column(String, primary_key=True, index=True)
    woman_id = Column(String, ForeignKey("women.id"), nullable=False, index=True)
    status = Column(String, nullable=False, default="raised")
    raised_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    bed_booked_at = Column(DateTime, nullable=True)
    ambulance_dispatched_at = Column(DateTime, nullable=True)
    arrived_at = Column(DateTime, nullable=True)
    lost_at = Column(DateTime, nullable=True)
    notes = Column(String, nullable=True)
    is_resolved = Column(Boolean, nullable=False, default=False)

    woman = relationship("Woman", back_populates="referral_events")


class PostnatalContact(Base):
    """
    Scheduled postnatal follow-up contact stub.

    One record per contact day (1, 3, 7, 14, 28, 42).
    contact_made is flipped to True when the CHW confirms contact.
    delivery_date is stored per-row to support due-date calculations without
    joining back to the woman table on every query.
    """

    __tablename__ = "postnatal_contacts"

    id = Column(String, primary_key=True, index=True)
    woman_id = Column(String, ForeignKey("women.id"), nullable=False, index=True)
    contact_day = Column(Integer, nullable=False)         # 1 | 3 | 7 | 14 | 28 | 42
    contact_date = Column(DateTime, nullable=True)        # date contact was actually made
    contact_made = Column(Boolean, nullable=False, default=False)
    notes = Column(String, nullable=True)
    delivery_date = Column(DateTime, nullable=True)       # reference for due-date calc

    woman = relationship("Woman", back_populates="postnatal_contacts")


# ---------------------------------------------------------------------------
# Table creation helper — called from main.py lifespan / startup event
# ---------------------------------------------------------------------------


def create_tables() -> None:
    """Create all ORM-defined tables that do not yet exist in the DB."""
    Base.metadata.create_all(bind=engine)


# ---------------------------------------------------------------------------
# FastAPI dependency — yields a session and closes it when the request ends
# ---------------------------------------------------------------------------


def get_db():
    """
    Yield a SQLAlchemy Session for use as a FastAPI dependency.

    Example usage in a router:
        @router.get("/")
        def endpoint(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
