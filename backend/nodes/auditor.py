"""
nodes/auditor.py
================
AGENT 5 – Auditor

Responsibility:
  1. Run fraud signal checks against claims history and policy thresholds.
  2. Finalise the output — compile trace, set final confidence, add summary.
  3. Route to MANUAL_REVIEW if any fraud signal fires.

Fraud signals (from policy_terms.json → fraud_thresholds):
  • Same-day claims count > limit
  • Monthly claims count > limit
  • Claimed amount > high_value_claim_threshold

This node does NOT call an LLM.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import date
from typing import Any, Dict, List

from utils.policy_loader import get_fraud_thresholds

logger = logging.getLogger(__name__)

FRAUD_CONFIDENCE_PENALTY = 0.3


def auditor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """AGENT 5: Fraud detection and final output compilation."""
    trace: List[str] = list(state.get("trace_log", []))
    errors: List[str] = list(state.get("errors", []))
    fraud_flags: List[str] = list(state.get("fraud_flags", []))
    confidence: float = state.get("confidence_score", 0.9)
    decision: str = state.get("decision", "APPROVED")
    approved_amount: float = state.get("approved_amount", 0.0)

    trace.append("═" * 60)
    trace.append("AGENT 5 — AUDITOR: Running fraud checks")

    thresholds = get_fraud_thresholds()
    claims_history: List[Dict[str, Any]] = state.get("claims_history", [])
    claimed_amount: float = state.get("claimed_amount", 0.0)
    treatment_date_str: str = state.get("treatment_date", "")

    # ── Fraud Check 1: Same-day claims ────────────────────────────────────────
    same_day_limit: int = int(thresholds.get("same_day_claims_limit", 2))
    same_day_count = _count_same_day_claims(claims_history, treatment_date_str)

    trace.append(
        f"  Same-day claims: {same_day_count} existing + this claim "
        f"(limit: {same_day_limit})"
    )

    if same_day_count >= same_day_limit:
        flag = (
            f"SAME_DAY_CLAIMS: {same_day_count} prior claims on {treatment_date_str} "
            f"(limit is {same_day_limit}). Unusual pattern detected."
        )
        fraud_flags.append(flag)
        confidence -= FRAUD_CONFIDENCE_PENALTY
        trace.append(f"  ⚠ FRAUD SIGNAL: {flag} — confidence ↓ {FRAUD_CONFIDENCE_PENALTY}")

    # ── Fraud Check 2: Monthly claims count ───────────────────────────────────
    monthly_limit: int = int(thresholds.get("monthly_claims_limit", 6))
    monthly_count = _count_monthly_claims(claims_history, treatment_date_str)

    trace.append(f"  Monthly claims: {monthly_count} (limit: {monthly_limit})")

    if monthly_count >= monthly_limit:
        flag = (
            f"MONTHLY_LIMIT: {monthly_count} claims this month "
            f"(limit is {monthly_limit})."
        )
        fraud_flags.append(flag)
        confidence -= FRAUD_CONFIDENCE_PENALTY
        trace.append(f"  ⚠ FRAUD SIGNAL: {flag} — confidence ↓ {FRAUD_CONFIDENCE_PENALTY}")

    # ── Fraud Check 3: High-value claim ───────────────────────────────────────
    high_value_threshold: float = float(thresholds.get("high_value_claim_threshold", 25000))
    auto_manual_threshold: float = float(thresholds.get("auto_manual_review_above", 25000))

    trace.append(
        f"  High-value check: ₹{claimed_amount:,.0f} vs threshold ₹{high_value_threshold:,.0f}"
    )

    if claimed_amount > auto_manual_threshold:
        flag = (
            f"HIGH_VALUE_CLAIM: ₹{claimed_amount:,.0f} exceeds auto-review threshold "
            f"₹{auto_manual_threshold:,.0f}."
        )
        fraud_flags.append(flag)
        trace.append(f"  ⚠ FRAUD SIGNAL: {flag}")

    # ── Route to MANUAL_REVIEW if any fraud signal fired ─────────────────────
    if fraud_flags:
        decision = "MANUAL_REVIEW"
        approved_amount = 0.0
        trace.append(
            f"  Routing to MANUAL_REVIEW due to {len(fraud_flags)} fraud signal(s): "
            + "; ".join(fraud_flags)
        )
    else:
        trace.append("  ✓ No fraud signals detected")

    # ── Clamp confidence ──────────────────────────────────────────────────────
    confidence = max(0.0, min(1.0, confidence))

    # ── Add a manual-review recommendation if component failed (TC011) ────────
    if state.get("simulate_component_failure"):
        trace.append(
            "  ⚠ NOTE: Component failure occurred during extraction. "
            "Manual review is recommended to verify extracted data."
        )

    # ── Final summary line ────────────────────────────────────────────────────
    trace.append("═" * 60)
    trace.append(f"FINAL DECISION  : {decision}")
    trace.append(f"APPROVED AMOUNT : ₹{approved_amount:,.2f}")
    trace.append(f"CONFIDENCE SCORE: {confidence:.2f}")
    if fraud_flags:
        trace.append(f"FRAUD FLAGS     : {len(fraud_flags)}")
    trace.append("═" * 60)
    trace.append("AGENT 5 — AUDITOR: Complete ✓")

    return {
        "trace_log": trace,
        "errors": errors,
        "fraud_flags": fraud_flags,
        "confidence_score": confidence,
        "decision": decision,
        "approved_amount": approved_amount,
        "pipeline_status": "MANUAL_REVIEW" if fraud_flags else state.get("pipeline_status", "CONTINUE"),
    }


# ── Private helpers ───────────────────────────────────────────────────────────

def _count_same_day_claims(
    claims_history: List[Dict[str, Any]],
    treatment_date_str: str,
) -> int:
    """Count how many existing claims share the same date as the current claim."""
    return sum(
        1 for c in claims_history
        if c.get("date", "") == treatment_date_str
    )


def _count_monthly_claims(
    claims_history: List[Dict[str, Any]],
    treatment_date_str: str,
) -> int:
    """Count claims in the same calendar month as the current claim."""
    try:
        treatment_date = date.fromisoformat(treatment_date_str)
    except ValueError:
        return 0

    return sum(
        1 for c in claims_history
        if _same_month(c.get("date", ""), treatment_date)
    )


def _same_month(date_str: str, reference: date) -> bool:
    try:
        d = date.fromisoformat(date_str)
        return d.year == reference.year and d.month == reference.month
    except ValueError:
        return False
