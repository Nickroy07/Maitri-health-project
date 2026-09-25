"""
model_c_prioritisation.py
==========================
MAITRI weekly visit priority queue calculator (Model C).

Exposes:
    compute_priority_queue(women_list, weekly_visit_capacity) -> list

Algorithm overview
------------------
Priority score = current_risk_score x urgency_decay(days_since_contact)
                                     x distance_weight(travel_minutes)

The resulting list is sorted descending by priority_score and truncated
to the ASHA/ANM weekly visit capacity.

Relationship to Restless Multi-Armed Bandits (RMAB)
-----------------------------------------------------
This deterministic function is a **stand-in** for the RMAB-based scheduling
policy described in the MAITRI pitch deck.  A production RMAB would:

  1. **Reward signal** -- Define a scalar reward observed after each visit:
       r = delta(Hb) x w_hb + delta(BP normalisation) x w_bp
           - penalty if referral was avoidable
     This reward must be measurable from the longitudinal records.

  2. **State representation** -- Each woman is an "arm" with a latent state
     (risk level, recency of contact, trajectory trend).  The RMAB maintains
     a belief distribution over states and updates it after each visit.

  3. **Whittle index policy** -- For budget-constrained scheduling (only K
     visits per week across N women), the Whittle index provides a
     computationally tractable approximation to the optimal policy.  Each
     arm's Whittle index encodes "how urgent is it to act now vs. defer?".

  4. **Exploration vs. exploitation** -- The RMAB naturally balances:
       - Exploitation: visit confirmed high-risk women whose trajectory is
         worsening.
       - Exploration: visit under-observed women to update belief and avoid
         missing hidden deterioration.

  5. **Transition learning** -- Visit-outcome transition probabilities
     (P(state at t+1 | state at t, action)) are learned from historical
     data via maximum-likelihood or Bayesian updates as new visits accrue.

Until sufficient historical data exists for RMAB fitting, this module
provides an interpretable, manually-tunable alternative.

Usage
-----
    from models.model_c_prioritisation import compute_priority_queue
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


# ===========================================================================
# Sub-scoring functions
# ===========================================================================

def urgency_decay(days: int) -> float:
    """
    Return an urgency multiplier based on days since last contact.

    Logic
    -----
    A woman not seen in 14 days has 2x urgency; at 28 days she has 3x.
    The multiplier is capped at 3.0 to prevent extreme outliers from
    dominating the queue (e.g., a woman who was never registered).

    Parameters
    ----------
    days : int
        Days elapsed since the woman's last contact.  Use 0 if seen today.

    Returns
    -------
    float in [1.0, 3.0]

    Examples
    --------
    >>> urgency_decay(0)
    1.0
    >>> urgency_decay(14)
    2.0
    >>> urgency_decay(28)
    3.0
    >>> urgency_decay(60)   # capped
    3.0
    """
    return min(1.0 + (days / 14.0), 3.0)


def distance_weight(travel_minutes: int) -> float:
    """
    Return a distance-based access-barrier weight.

    Rationale
    ---------
    Harder-to-reach women are likely to receive fewer spontaneous visits,
    so the scheduler gives them a slight upweight so they are not
    systematically deprioritised.

    The cap at 1.3 means distance never dominates over clinical risk --
    a nearby high-risk woman always outranks a distant low-risk woman.

    Parameters
    ----------
    travel_minutes : int
        One-way travel time from woman's home to the nearest FRTU.

    Returns
    -------
    float in [1.0, 1.3]

    Examples
    --------
    >>> distance_weight(0)
    1.0
    >>> distance_weight(120)
    1.3
    >>> distance_weight(240)   # capped
    1.3
    """
    return min(1.0 + (travel_minutes / 120.0) * 0.3, 1.3)


# ===========================================================================
# Main function
# ===========================================================================

def compute_priority_queue(
    women_list: list[dict],
    weekly_visit_capacity: int = 20,
) -> list[dict]:
    """
    Compute and return the weekly priority visit queue for ASHA workers.

    This is a deterministic, rule-based stand-in for the Restless Multi-Armed
    Bandit (RMAB) scheduling policy described in the MAITRI pitch deck.
    See module docstring for full RMAB upgrade notes.

    Parameters
    ----------
    women_list : list[dict]
        Each dict must contain:
          - woman_id           : str
          - current_risk_score : float [0, 1]  -- output of Model A x Model B
          - last_contact_date  : str (ISO-8601) | None
          - travel_time_minutes: int

    weekly_visit_capacity : int, optional
        Maximum number of visits the ASHA/ANM worker can complete this week.
        Defaults to 20.

    Returns
    -------
    list[dict]
        Each dict contains all input fields plus:
          - days_since_contact : int
          - urgency_multiplier : float
          - distance_multiplier: float
          - priority_score     : float
        Sorted descending by priority_score, truncated to weekly_visit_capacity.

    Notes
    -----
    Women whose last_contact_date is None are treated as never seen (days = 999),
    giving them maximum urgency.  This is conservative -- unknown history -> high
    urgency is the safer default for maternal health.
    """
    today = datetime.now(timezone.utc).date()
    scored: list[dict] = []

    for woman in women_list:
        woman_id       = woman["woman_id"]
        risk_score     = float(woman["current_risk_score"])
        last_contact   = woman.get("last_contact_date")
        travel_minutes = int(woman.get("travel_time_minutes", 0))

        # --- Days since last contact ----------------------------------------
        if last_contact is None:
            # Never contacted: maximum urgency
            days = 999
        else:
            try:
                last_dt = datetime.fromisoformat(last_contact).date()
                days    = (today - last_dt).days
            except ValueError:
                days = 999  # unparseable date -> treat as never seen

        # --- Component scores -----------------------------------------------
        u_mult = urgency_decay(days)
        d_mult = distance_weight(travel_minutes)
        p_score = risk_score * u_mult * d_mult

        scored.append({
            **woman,                            # preserve original fields
            "days_since_contact":  days if days < 999 else None,
            "urgency_multiplier":  round(u_mult,  3),
            "distance_multiplier": round(d_mult,  3),
            "priority_score":      round(p_score, 4),
        })

    # Sort descending by priority_score, then truncate to capacity
    scored.sort(key=lambda x: x["priority_score"], reverse=True)
    return scored[:weekly_visit_capacity]


# ===========================================================================
# Example usage
# ===========================================================================

if __name__ == "__main__":
    import json

    print("=== Model C -- Priority Queue ===\n")

    # Simulate a small caseload for an ASHA worker
    women = [
        {
            "woman_id":           "w-001",
            "current_risk_score": 0.82,
            "last_contact_date":  "2024-04-01",
            "travel_time_minutes": 45,
        },
        {
            "woman_id":           "w-002",
            "current_risk_score": 0.45,
            "last_contact_date":  None,          # never seen
            "travel_time_minutes": 180,
        },
        {
            "woman_id":           "w-003",
            "current_risk_score": 0.91,
            "last_contact_date":  "2024-04-10",
            "travel_time_minutes": 20,
        },
        {
            "woman_id":           "w-004",
            "current_risk_score": 0.15,
            "last_contact_date":  "2024-03-15",  # very overdue
            "travel_time_minutes": 90,
        },
        {
            "woman_id":           "w-005",
            "current_risk_score": 0.60,
            "last_contact_date":  "2024-04-12",
            "travel_time_minutes": 130,
        },
    ]

    queue = compute_priority_queue(women, weekly_visit_capacity=3)

    print("Top 3 priority visits this week:")
    for rank, entry in enumerate(queue, start=1):
        print(f"\nRank {rank}: {entry['woman_id']}")
        print(f"  risk_score        : {entry['current_risk_score']:.2f}")
        print(f"  days_since_contact: {entry['days_since_contact']}")
        print(f"  urgency_multiplier: {entry['urgency_multiplier']:.2f}")
        print(f"  distance_multiplier:{entry['distance_multiplier']:.2f}")
        print(f"  priority_score    : {entry['priority_score']:.4f}")
