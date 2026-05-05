"""
eval_runner.py
==============
Runs all 12 test cases from test_cases.json and produces an eval report.
Run with: python eval_runner.py
"""

import json
import sys
import os

# Make sure we can import from the backend root
sys.path.insert(0, os.path.dirname(__file__))

from models import build_initial_state, ClaimSubmission
from pipeline import claims_pipeline

# Load test cases
with open("test_cases.json") as f:
    test_data = json.load(f)

test_cases = test_data["test_cases"]

results = []

for tc in test_cases:
    case_id = tc["case_id"]
    case_name = tc["case_name"]
    inp = tc["input"]
    expected = tc["expected"]

    # Build submission
    try:
        submission = ClaimSubmission(
            member_id=inp["member_id"],
            policy_id=inp["policy_id"],
            claim_category=inp["claim_category"],
            treatment_date=inp["treatment_date"],
            claimed_amount=inp["claimed_amount"],
            documents=inp.get("documents", []),
            claims_history=inp.get("claims_history", []),
            ytd_claims_amount=inp.get("ytd_claims_amount", 0),
            hospital_name=inp.get("hospital_name"),
            simulate_component_failure=inp.get("simulate_component_failure", False),
        )
        initial_state = build_initial_state(submission)
        final = claims_pipeline.invoke(initial_state)
    except Exception as e:
        results.append({
            "case_id": case_id,
            "case_name": case_name,
            "error": str(e),
            "pass": False,
        })
        continue

    actual_decision = final.get("decision")
    expected_decision = expected.get("decision")
    approved_amount = final.get("approved_amount", 0)

    # Evaluate pass/fail
    passed = True
    notes = []

    if expected_decision is not None:
        if actual_decision != expected_decision:
            passed = False
            notes.append(f"Decision: expected={expected_decision}, got={actual_decision}")

    if expected.get("approved_amount"):
        exp_amt = float(expected["approved_amount"])
        if abs(approved_amount - exp_amt) > 1:  # allow ₹1 rounding tolerance
            passed = False
            notes.append(f"Amount: expected=₹{exp_amt}, got=₹{approved_amount:.2f}")

    if expected.get("rejection_reasons"):
        for rr in expected["rejection_reasons"]:
            if rr not in (final.get("rejection_reasons") or []):
                passed = False
                notes.append(f"Missing rejection reason: {rr}")

    if expected.get("confidence_score") == "above 0.85":
        if final.get("confidence_score", 0) < 0.85:
            passed = False
            notes.append(f"Confidence too low: {final.get('confidence_score'):.2f}")

    if expected.get("confidence_score") == "above 0.90":
        if final.get("confidence_score", 0) < 0.90:
            passed = False
            notes.append(f"Confidence too low: {final.get('confidence_score'):.2f}")

    # system_must checks (qualitative)
    must_checks = []
    if expected.get("system_must"):
        for req in expected["system_must"]:
            must_checks.append(f"  [QUALITATIVE] {req}")

    results.append({
        "case_id": case_id,
        "case_name": case_name,
        "expected_decision": expected_decision,
        "actual_decision": actual_decision,
        "expected_amount": expected.get("approved_amount"),
        "actual_amount": round(approved_amount, 2) if approved_amount else None,
        "confidence": round(final.get("confidence_score", 0), 3),
        "fraud_flags": final.get("fraud_flags", []),
        "rejection_reasons": final.get("rejection_reasons", []),
        "errors": final.get("errors", []),
        "pass": passed,
        "notes": notes,
        "must_checks": must_checks,
        "trace_summary": final.get("trace_log", [])[-6:],  # last 6 trace lines
    })


# ── Print report ──────────────────────────────────────────────────────────────

print("\n" + "═" * 72)
print("  PLUM CLAIMS SYSTEM — EVAL REPORT")
print("═" * 72)

passed_count = sum(1 for r in results if r.get("pass"))
print(f"\n  OVERALL: {passed_count}/{len(results)} cases PASSED\n")

for r in results:
    status = "✅ PASS" if r.get("pass") else "❌ FAIL"
    print(f"{'─' * 72}")
    print(f"  {r['case_id']} | {r['case_name']}")
    print(f"  Status   : {status}")
    print(f"  Decision : expected={r.get('expected_decision')!r:20}  actual={r.get('actual_decision')!r}")

    if r.get("expected_amount"):
        print(f"  Amount   : expected=₹{r['expected_amount']:>10}     actual=₹{r.get('actual_amount') or 'N/A'}")

    print(f"  Confidence: {r.get('confidence', '?')}")

    if r.get("rejection_reasons"):
        print(f"  Rejection: {r['rejection_reasons']}")
    if r.get("fraud_flags"):
        print(f"  Fraud    : {r['fraud_flags']}")
    if r.get("notes"):
        for n in r["notes"]:
            print(f"  ⚠ {n}")
    if r.get("errors"):
        for e in r["errors"][:2]:
            print(f"  ERROR: {e[:120]}")
    if r.get("must_checks"):
        for m in r["must_checks"]:
            print(m)
    print(f"  Trace tail:")
    for line in r.get("trace_summary", []):
        print(f"    {line}")

print("\n" + "═" * 72)
print(f"  FINAL SCORE: {passed_count}/{len(results)} ({100*passed_count//len(results)}%)")
print("═" * 72 + "\n")
