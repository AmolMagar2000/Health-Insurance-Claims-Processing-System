"""
nodes/gatekeeper.py
===================
AGENT 1 – Gatekeeper

Responsibility: Validate that the right document types were uploaded for
the claimed category, and that the member exists in the policy roster.

Rules come from policy_terms.json → document_requirements.
If anything is wrong the pipeline is stopped immediately (pipeline_status = EARLY_EXIT)
with a specific, human-readable error message — NOT a generic one.

This node never calls an LLM.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from utils.policy_loader import get_member, get_required_documents

logger = logging.getLogger(__name__)


def gatekeeper_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph node — receives the full state dict, returns a partial dict
    with only the keys it changes.  LangGraph merges the return value back
    into the shared state.
    """
    trace: list[str] = list(state.get("trace_log", []))
    errors: list[str] = list(state.get("errors", []))

    trace.append("═" * 60)
    trace.append("AGENT 1 — GATEKEEPER: Starting validation")

    # ── Step 1: Check member exists ──────────────────────────────────────────
    member_id = state["member_id"]
    member = get_member(member_id)

    if member is None:
        msg = (
            f"Member '{member_id}' was not found in the policy roster. "
            f"Please verify the member ID and resubmit."
        )
        trace.append(f"  ✗ Member lookup: {msg}")
        errors.append(msg)
        return {
            "trace_log": trace,
            "errors": errors,
            "pipeline_status": "EARLY_EXIT",
            "decision": "REJECTED",
            "rejection_reasons": ["MEMBER_NOT_FOUND"],
            "member_info": None,
        }

    trace.append(f"  ✓ Member found: {member['name']} (ID: {member_id})")

    # ── Step 2: Check document types ─────────────────────────────────────────
    category = state["category"].upper()
    doc_rules = get_required_documents(category)
    required_types: list[str] = doc_rules.get("required", [])

    # What was actually uploaded?
    uploaded_types: list[str] = [
        d.get("actual_type", "UNKNOWN").upper()
        for d in state.get("documents", [])
    ]

    trace.append(f"  Category        : {category}")
    trace.append(f"  Required docs   : {required_types}")
    trace.append(f"  Uploaded docs   : {uploaded_types}")

    # Find missing required documents
    missing: list[str] = [t for t in required_types if t not in uploaded_types]

    if missing:
        # Find what was uploaded that does NOT belong in the required set
        wrong = [t for t in uploaded_types if t not in required_types]

        # Build a specific, actionable error message
        if wrong:
            msg = (
                f"Document mismatch for a {category} claim. "
                f"You uploaded: {', '.join(wrong)}. "
                f"Missing required document(s): {', '.join(missing)}. "
                f"Please upload {' and '.join(missing)} and resubmit."
            )
        else:
            msg = (
                f"Missing required document(s) for a {category} claim: "
                f"{', '.join(missing)}. "
                f"Please upload the missing document(s) and resubmit."
            )

        trace.append(f"  ✗ Document check: {msg}")
        errors.append(msg)

        return {
            "trace_log": trace,
            "errors": errors,
            "pipeline_status": "EARLY_EXIT",
            "decision": None,
            "rejection_reasons": ["WRONG_DOCUMENT_TYPE"],
            "member_info": member,
        }

    trace.append("  ✓ All required documents present")

    # ── Step 3: Record member info for downstream nodes ───────────────────────
    trace.append("AGENT 1 — GATEKEEPER: Validation passed ✓")

    return {
        "trace_log": trace,
        "errors": errors,
        "pipeline_status": "CONTINUE",
        "member_info": member,
        "decision": None,
    }
