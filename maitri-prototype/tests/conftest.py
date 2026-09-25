"""
conftest.py — Shared pytest fixtures for the MAITRI test suite.

Provides:
  - test_db_path      : session-scoped temp SQLite file path
  - client            : function-scoped FastAPI TestClient wired to the temp DB
  - sample_woman_data : valid WomanCreate payload dict
  - sample_visit_data : valid visit payload dict
"""

import os
import sys
import tempfile
import pytest

# ---------------------------------------------------------------------------
# Make the project root importable so `from backend.main import app` works
# regardless of where pytest is invoked from.
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)



# ---------------------------------------------------------------------------
# Session-scoped: one temp DB engine shared across the whole test session.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def test_db_path(tmp_path_factory):
    """
    Yield a temporary directory for the test session's SQLite database.
    """
    db_dir = tmp_path_factory.mktemp("maitri_test_db")
    db_path = str(db_dir / "test_maitri.db")
    yield db_path


# ---------------------------------------------------------------------------
# Function-scoped: fresh TestClient for every test function.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="function")
def client(test_db_path):
    """
    FastAPI TestClient wired to a temporary SQLite database.
    Uses dependency_overrides to replace get_db for the duration of each test.
    """
    from fastapi.testclient import TestClient
    from backend.main import app, get_db
    from backend.db import Base, engine
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    test_engine = create_engine(
        f"sqlite:///{test_db_path}",
        connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    # Create all tables in the test DB
    Base.metadata.create_all(bind=test_engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(bind=test_engine)


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def sample_woman_data():
    """
    Returns a valid registration payload dict (matches WomanCreate schema).
    Represents a healthy low-risk woman.
    """
    return {
        "full_name": "Test Woman",
        "age": 25,
        "district": "Nandurbar",
        "village": "Test Village",
        "phone": "9876543210",
        "parity": 1,
        "gravida": 2,
        "height_cm": 155.0,
        "weight_kg": 53.0,
        "haemoglobin_g_dl": 11.5,
        "systolic_bp": 110,
        "diastolic_bp": 70,
        "obstetric_history_flag": False,
        "interpregnancy_interval_months": 24,
        "travel_time_to_frtu_minutes": 30,
        "gestational_age_weeks_at_registration": 12,
        "fundal_height_cm": None,
        "danger_sign_reported": False,
    }


@pytest.fixture
def sample_visit_data():
    """
    Returns a valid follow-up visit payload dict.
    Represents a routine stable visit — no escalation flags expected.
    """
    return {
        "haemoglobin_g_dl": 11.0,
        "systolic_bp": 112,
        "diastolic_bp": 72,
        "fundal_height_cm": 20.0,
        "weight_kg": 56.0,
        "danger_sign": False,
        "visit_date": "2026-06-15",
    }
