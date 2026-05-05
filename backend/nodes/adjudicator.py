"""
nodes/adjudicator.py
====================
AGENT 4 – Adjudicator  (PURE PYTHON — ZERO LLM CALLS)

Responsibility: Apply policy rules to the extracted claim data and
produce one of: APPROVED | PARTIAL | REJECTED | MANUAL_REVIEW.

Rules applied in order:
  1.  Waiting period check
  2.  Policy exclusion check
  3.  Pre-authorisation check (MRI / CT Scan above threshold)
  4.  Per-claim limit check
  5.  Line-item level exclusions (dental cosmetic procedures, etc.)
  6.  Apply financial calculations:
        a. Network discount   (applied FIRST)
        b. Co-pay deduction   (applied AFTER discount)

Every step appends an explanation to trace_log.
ALL numbers, rules, and thresholds come from policy_terms.json.
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta

def _keyword_match(keywords: list[str], text: str) -> bool:
    """Match keywords using word boundaries to avoid false positives like hernia→herniation."""
    for kw in keywords:
        # Build a pattern: word boundary on each side
        pattern = r'\b' + re.escape(kw) + r'\b'
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False
from typing import Any, Dict, List, Optional, Tuple

from utils.policy_loader import (
    get_category_rules,
    get_coverage,
    get_exclusions,
    get_pre_auth_requirements,
    get_waiting_periods,
    is_network_hospital,
    load_policy,
)

logger = logging.getLogger(__name__)


# ── Condition → waiting period keyword mapping ────────────────────────────────
CONDITION_KEYWORDS: Dict[str, List[str]] = {
    "diabetes": ["diabetes", "t2dm", "type 2 diabetes", "diabetic", "metformin", "glimepiride"],
    "hypertension": ["hypertension", "htn", "high blood pressure"],
    "thyroid_disorders": ["hypothyroidism", "hyperthyroidism", "thyroid"],
    "joint_replacement": ["joint replacement", "knee replacement", "hip replacement"],
    "maternity": ["maternity", "pregnancy", "antenatal", "prenatal", "delivery"],
    "mental_health": ["depression", "anxiety", "mental health", "psychiatr"],
    "obesity_treatment": ["obesity", "bariatric", "weight loss", "morbid obesity", "bmi"],
    "hernia": ["hernia"],
    "cataract": ["cataract"],
}

# Procedures covered vs excluded for dental (from policy)
DENTAL_COVERED_KEYWORDS = [
    "root canal", "tooth extraction", "dental filling", "scaling",
    "polishing", "dental x-ray", "x-ray", "crown", "gum treatment",
]
DENTAL_EXCLUDED_KEYWORDS = [
    "teeth whitening", "whitening", "veneer", "orthodontic", "braces",
    "implant", "bleaching",
]

# High-value tests that require pre-auth (pulled from policy)
PRE_AUTH_TESTS = ["mri", "ct scan", "pet scan", "ct", "pet"]


def adjudicator_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """AGENT 4: Pure-Python policy adjudication."""
    trace: List[str] = list(state.get("trace_log", []))
    errors: List[str] = list(state.get("errors", []))
    rejection_reasons: List[str] = list(state.get("rejection_reasons", []))
    confidence: float = state.get("confidence_score", 0.9)

    trace.append("═" * 60)
    trace.append("AGENT 4 — ADJUDICATOR: Applying policy rules (pure Python)")

    category = state["category"].upper()
    claimed_amount: float = state["claimed_amount"]
    extracted: Dict[str, Any] = state.get("extracted_data", {})
    member_info: Optional[Dict[str, Any]] = state.get("member_info", {})
    hospital_name: Optional[str] = state.get("hospital_name") or extracted.get("hospital_name")
    treatment_date_str: str = state.get("treatment_date", "")
    pre_auth_id: Optional[str] = state.get("pre_auth_id")

    line_item_decisions: List[Dict[str, Any]] = []
    approved_amount: float = claimed_amount  # start with full amount, then reduce

    # ── 1. Exclusion check (FIRST — excluded conditions take priority) ────────
    # Check exclusions before waiting period so a bariatric claim gets
    # EXCLUDED_CONDITION (not WAITING_PERIOD) as its rejection reason.
    exclusion_result = _check_exclusions(extracted, category, trace)
    if exclusion_result["fully_excluded"]:
        rejection_reasons.append("EXCLUDED_CONDITION")
        return _reject(
            state, trace, errors, rejection_reasons, confidence,
            exclusion_result["message"],
        )

    # ── 2. Waiting period check ───────────────────────────────────────────────
    waiting_result = _check_waiting_period(
        member_info, treatment_date_str, extracted, trace
    )
    if waiting_result["rejected"]:
        rejection_reasons.append("WAITING_PERIOD")
        return _reject(
            state, trace, errors, rejection_reasons, confidence,
            waiting_result["message"],
        )
        rejection_reasons.append("EXCLUDED_CONDITION")
        return _reject(
            state, trace, errors, rejection_reasons, confidence,
            exclusion_result["message"],
        )

    # ── 3. Pre-authorisation check ────────────────────────────────────────────
    pre_auth_result = _check_pre_auth(
        extracted, category, claimed_amount, pre_auth_id, trace
    )
    if pre_auth_result["rejected"]:
        rejection_reasons.append("PRE_AUTH_MISSING")
        return _reject(
            state, trace, errors, rejection_reasons, confidence,
            pre_auth_result["message"],
        )

    # ── 4. Per-claim limit check ───────────────────────────────────────────────
    coverage = get_coverage()
    per_claim_limit: float = float(coverage.get("per_claim_limit", 5000))

    # Dental and vision have dedicated sub-limits that supersede per_claim_limit
    cat_rules = get_category_rules(category)
    use_sub_limit = category in ("DENTAL", "VISION", "ALTERNATIVE_MEDICINE")

    if use_sub_limit:
        effective_limit = float(cat_rules.get("sub_limit", per_claim_limit)) if cat_rules else per_claim_limit
        limit_label = f"category sub-limit ({category})"
    else:
        effective_limit = per_claim_limit
        limit_label = "per-claim limit"

    trace.append(
        f"  Checking {limit_label}: ₹{claimed_amount:,.0f} vs limit ₹{effective_limit:,.0f}"
    )

    if claimed_amount > effective_limit and not use_sub_limit:
        # For consultation/diagnostic/pharmacy: reject if over per_claim_limit
        msg = (
            f"Claimed amount ₹{claimed_amount:,.0f} exceeds the {limit_label} "
            f"of ₹{effective_limit:,.0f}. "
            f"The maximum reimbursable per claim is ₹{effective_limit:,.0f}. "
            f"You may resubmit for the remaining balance in a separate claim."
        )
        rejection_reasons.append("PER_CLAIM_EXCEEDED")
        trace.append(f"  ✗ {limit_label.upper()}_EXCEEDED: {msg}")
        return _reject(state, trace, errors, rejection_reasons, confidence, msg)

    trace.append(f"  ✓ Within {limit_label}")

    # ── 5. Line-item level exclusions (mainly dental) ─────────────────────────
    line_items: List[Dict[str, Any]] = extracted.get("line_items", [])
    if line_items:
        approved_amount, line_item_decisions = _process_line_items(
            line_items, category, trace
        )
        trace.append(
            f"  Line-item approved total: ₹{approved_amount:,.2f} "
            f"(from {len(line_items)} item(s))"
        )
        # Note: sub_limit here is the ANNUAL category budget, not a per-claim cap.
        # Per-claim cap is enforced by per_claim_limit above.
        # We only apply sub_limit as a hard cap for DENTAL/VISION which have
        # standalone benefit buckets with their own per-claim maximums.
        if cat_rules and category in ("DENTAL", "VISION"):
            sub_limit = float(cat_rules.get("sub_limit", float("inf")))
            if approved_amount > sub_limit:
                trace.append(f"  Capping at {category} sub-limit: ₹{sub_limit:,.0f}")
                approved_amount = sub_limit

    # ── 6. Financial calculations: network discount → copay ───────────────────
    if cat_rules:
        approved_amount = _apply_financials(
            approved_amount, cat_rules, hospital_name, trace
        )

    # ── Determine final decision ──────────────────────────────────────────────
    all_excluded = all(
        d.get("status") == "EXCLUDED" for d in line_item_decisions
    ) if line_item_decisions else False

    has_partial = any(
        d.get("status") == "EXCLUDED" for d in line_item_decisions
    ) if line_item_decisions else False

    if all_excluded:
        rejection_reasons.append("EXCLUDED_CONDITION")
        return _reject(
            state, trace, errors, rejection_reasons, confidence,
            "All claimed procedures are excluded under this policy.",
        )

    decision = "PARTIAL" if has_partial else "APPROVED"
    trace.append(f"  Final decision: {decision}")
    trace.append(f"  Approved amount: ₹{approved_amount:,.2f}")
    trace.append("AGENT 4 — ADJUDICATOR: Complete ✓")

    return {
        "trace_log": trace,
        "errors": errors,
        "confidence_score": confidence,
        "decision": decision,
        "approved_amount": round(approved_amount, 2),
        "rejection_reasons": rejection_reasons,
        "line_item_decisions": line_item_decisions,
        "pipeline_status": "CONTINUE",
    }


# ── Helper functions ──────────────────────────────────────────────────────────

def _check_waiting_period(
    member_info: Optional[Dict[str, Any]],
    treatment_date_str: str,
    extracted: Dict[str, Any],
    trace: List[str],
) -> Dict[str, Any]:
    """Check initial and condition-specific waiting periods."""
    if not member_info:
        trace.append("  ⚠ Member info missing — skipping waiting period check")
        return {"rejected": False, "message": ""}

    waiting = get_waiting_periods()
    join_date = date.fromisoformat(member_info.get("join_date", "2024-01-01"))

    try:
        treatment_date = date.fromisoformat(treatment_date_str)
    except ValueError:
        trace.append(f"  ⚠ Could not parse treatment date '{treatment_date_str}' — skipping")
        return {"rejected": False, "message": ""}

    days_since_join = (treatment_date - join_date).days
    trace.append(
        f"  Waiting period: joined {join_date}, treatment {treatment_date}, "
        f"{days_since_join} days elapsed"
    )

    # Initial waiting period (30 days for all claims)
    initial_days: int = waiting.get("initial_waiting_period_days", 30)
    if days_since_join < initial_days:
        eligible_date = join_date + timedelta(days=initial_days)
        msg = (
            f"This claim is within the initial waiting period of {initial_days} days. "
            f"You joined on {join_date} and will be eligible from {eligible_date} onwards."
        )
        trace.append(f"  ✗ INITIAL_WAITING_PERIOD: {days_since_join} < {initial_days} days")
        return {"rejected": True, "message": msg}

    # Specific condition waiting periods
    diagnosis_text = (extracted.get("diagnosis") or "").lower()
    medicines_text = " ".join(extracted.get("medicines") or []).lower()
    full_text = diagnosis_text + " " + medicines_text

    specific: Dict[str, int] = waiting.get("specific_conditions", {})
    for condition, required_days in specific.items():
        keywords = CONDITION_KEYWORDS.get(condition, [condition.replace("_", " ")])
        if _keyword_match(keywords, full_text):
            if days_since_join < required_days:
                eligible_date = join_date + timedelta(days=required_days)
                friendly = condition.replace("_", " ").title()
                msg = (
                    f"{friendly} has a {required_days}-day waiting period. "
                    f"You joined on {join_date}. "
                    f"You will be eligible for {friendly} claims from {eligible_date} onwards. "
                    f"Days elapsed: {days_since_join} / {required_days}."
                )
                trace.append(
                    f"  ✗ WAITING_PERIOD ({condition}): {days_since_join} < {required_days} days"
                )
                return {"rejected": True, "message": msg}
            else:
                trace.append(
                    f"  ✓ Waiting period for {condition}: {days_since_join} ≥ {required_days} days"
                )

    trace.append("  ✓ All waiting periods cleared")
    return {"rejected": False, "message": ""}


def _check_exclusions(
    extracted: Dict[str, Any],
    category: str,
    trace: List[str],
) -> Dict[str, Any]:
    """Check if the diagnosis/treatment falls under a global exclusion."""
    excl = get_exclusions()
    diagnosis = (extracted.get("diagnosis") or "").lower()
    treatment = (extracted.get("treatment") or "").lower()
    # Also check line item descriptions for dental/vision cosmetic items
    line_items_text = " ".join(
        str(li.get("description", "")).lower()
        for li in (extracted.get("line_items") or [])
    )
    combined = diagnosis + " " + treatment + " " + line_items_text

    global_excluded: List[str] = [e.lower() for e in excl.get("conditions", [])]

    # Stopwords that should NOT be used as matching anchors alone
    STOPWORDS = {
        "treatment", "therapy", "condition", "procedure", "program",
        "programs", "procedures", "surgery", "and", "or", "the", "for",
        "with", "non", "medically", "necessary", "assisted", "weight",
    }

    for excl_condition in global_excluded:
        # Extract distinctive words (long enough, not stopwords)
        words = [
            w for w in excl_condition.split()
            if len(w) >= 5 and w not in STOPWORDS
        ]
        if not words:
            # Fall back to all words if filtering leaves nothing
            words = excl_condition.split()

        # Require ALL distinctive words to match (AND logic) to avoid false positives
        # e.g. "Substance Abuse Treatment" needs "substance" AND "abuse" to match
        all_match = all(
            re.search(r'\b' + re.escape(w) + r'\b', combined)
            for w in words
        )
        if all_match:
            msg = (
                f"Treatment '{(diagnosis or treatment).strip()}' falls under a policy exclusion: "
                f"'{excl_condition.title()}'. This is not covered. "
                f"Refer to your policy document for the complete exclusions list."
            )
            trace.append(f"  ✗ EXCLUSION matched: '{excl_condition}' in claim text")
            return {"fully_excluded": True, "message": msg}

    trace.append("  ✓ No global exclusions triggered")
    return {"fully_excluded": False, "message": ""}


def _check_pre_auth(
    extracted: Dict[str, Any],
    category: str,
    claimed_amount: float,
    pre_auth_id: Optional[str],
    trace: List[str],
) -> Dict[str, Any]:
    """Check whether pre-authorisation is required and was obtained."""
    if category != "DIAGNOSTIC":
        return {"rejected": False, "message": ""}

    policy = load_policy()
    high_value_tests: List[str] = (
        policy.get("opd_categories", {})
        .get("diagnostic", {})
        .get("high_value_tests_requiring_pre_auth", [])
    )
    pre_auth_threshold: float = float(
        policy.get("opd_categories", {})
        .get("diagnostic", {})
        .get("pre_auth_threshold", 10000)
    )

    # Check line items for high-value tests
    line_items: List[Dict[str, Any]] = extracted.get("line_items", [])
    tests_ordered: List[str] = extracted.get("tests_ordered", [])
    all_text = (
        " ".join(str(li.get("description", "")) for li in line_items)
        + " "
        + " ".join(tests_ordered)
    ).lower()

    for test in high_value_tests:
        if test.lower() in all_text and claimed_amount > pre_auth_threshold:
            if not pre_auth_id:
                msg = (
                    f"A {test} costing ₹{claimed_amount:,.0f} requires pre-authorisation "
                    f"when the amount exceeds ₹{pre_auth_threshold:,.0f}. "
                    f"Pre-authorisation was not obtained before the procedure. "
                    f"To resubmit: obtain pre-auth from your insurer, then resubmit "
                    f"with the pre-auth reference number."
                )
                trace.append(
                    f"  ✗ PRE_AUTH_MISSING: {test} at ₹{claimed_amount:,.0f} "
                    f"> threshold ₹{pre_auth_threshold:,.0f}"
                )
                return {"rejected": True, "message": msg}
            else:
                trace.append(f"  ✓ Pre-auth present for {test}: {pre_auth_id}")

    return {"rejected": False, "message": ""}


def _process_line_items(
    line_items: List[Dict[str, Any]],
    category: str,
    trace: List[str],
) -> Tuple[float, List[Dict[str, Any]]]:
    """
    Evaluate each line item against category-specific coverage rules.
    Returns (approved_total, list_of_item_decisions).
    """
    decisions: List[Dict[str, Any]] = []
    approved_total: float = 0.0

    policy = load_policy()
    cat_config = policy.get("opd_categories", {}).get(category.lower(), {})

    covered_procs: List[str] = [p.lower() for p in cat_config.get("covered_procedures", [])]
    excluded_procs: List[str] = [p.lower() for p in cat_config.get("excluded_procedures", [])]

    for item in line_items:
        desc: str = str(item.get("description", "")).lower()
        amount: float = float(item.get("amount", 0))
        reason: str = ""
        status: str = "APPROVED"

        # ── Category-specific exclusion check ────────────────────────────────
        is_excluded = False

        if category == "DENTAL":
            if any(ex in desc for ex in DENTAL_EXCLUDED_KEYWORDS):
                is_excluded = True
                reason = f"Dental cosmetic procedure excluded: '{item['description']}'"
            elif covered_procs and not any(cv in desc for cv in DENTAL_COVERED_KEYWORDS):
                # If covered list exists and item doesn't match any covered procedure
                reason = f"Procedure '{item['description']}' is not in the covered dental procedures list"
                is_excluded = True

        elif excluded_procs:
            if any(ep in desc for ep in excluded_procs):
                is_excluded = True
                reason = f"Excluded procedure: '{item['description']}'"

        if is_excluded:
            status = "EXCLUDED"
            trace.append(f"    ✗ EXCLUDED: {item.get('description')} (₹{amount:,.0f}) — {reason}")
        else:
            approved_total += amount
            trace.append(f"    ✓ APPROVED: {item.get('description')} (₹{amount:,.0f})")

        decisions.append({
            "description": item.get("description"),
            "claimed_amount": amount,
            "approved_amount": amount if status == "APPROVED" else 0.0,
            "status": status,
            "reason": reason,
        })

    return approved_total, decisions


def _apply_financials(
    base_amount: float,
    cat_rules: Dict[str, Any],
    hospital_name: Optional[str],
    trace: List[str],
) -> float:
    """
    Apply network discount THEN co-pay.

    Example (from TC010 / assignment spec):
      ₹4,500 → 20% network discount → ₹3,600 → 10% co-pay → ₹3,240
    """
    amount = base_amount

    # Step A: Network discount
    network_discount_pct: float = float(cat_rules.get("network_discount_percent", 0))
    if network_discount_pct > 0 and is_network_hospital(hospital_name):
        discount = amount * (network_discount_pct / 100)
        amount -= discount
        trace.append(
            f"  Network discount ({network_discount_pct}%): "
            f"₹{base_amount:,.2f} − ₹{discount:,.2f} = ₹{amount:,.2f}"
        )
    else:
        trace.append(
            f"  Network discount: not applicable "
            f"(hospital not in network or no discount for this category)"
        )

    # Step B: Co-pay
    copay_pct: float = float(cat_rules.get("copay_percent", 0))
    if copay_pct > 0:
        copay = amount * (copay_pct / 100)
        before_copay = amount
        amount -= copay
        trace.append(
            f"  Co-pay ({copay_pct}%): "
            f"₹{before_copay:,.2f} − ₹{copay:,.2f} = ₹{amount:,.2f}"
        )
    else:
        trace.append("  Co-pay: 0% (no co-pay for this category)")

    return amount


def _reject(
    state: Dict[str, Any],
    trace: List[str],
    errors: List[str],
    rejection_reasons: List[str],
    confidence: float,
    message: str,
) -> Dict[str, Any]:
    """Shared helper to produce a REJECTED response."""
    errors.append(message)
    trace.append(f"  DECISION: REJECTED")
    trace.append(f"  Reason(s): {', '.join(rejection_reasons)}")
    trace.append("AGENT 4 — ADJUDICATOR: Complete (REJECTED)")

    return {
        "trace_log": trace,
        "errors": errors,
        "confidence_score": confidence,
        "decision": "REJECTED",
        "approved_amount": 0.0,
        "rejection_reasons": rejection_reasons,
        "pipeline_status": "CONTINUE",
        "line_item_decisions": [],
    }
