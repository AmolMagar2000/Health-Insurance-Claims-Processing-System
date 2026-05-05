"""
nodes/document_quality.py
==========================
AGENT 2 – Document Quality Checker

Responsibility: Inspect each uploaded document for quality problems
(blurry, unreadable, missing critical fields, or patient name mismatch
across documents — TC003 scenario).

Key design decisions:
  • A bad-quality document → ask for re-upload, but DON'T reject the claim.
  • A patient-name mismatch → stop the pipeline (fraud / error signal).
  • Every quality issue reduces confidence_score.

This node does NOT call an LLM.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# How much to reduce confidence for each quality problem
CONFIDENCE_REDUCTION = {
    "UNREADABLE": 0.3,
    "POOR": 0.15,
    "MISSING_FIELDS": 0.2,
    "PATIENT_MISMATCH": 0.4,
}


def document_quality_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """AGENT 2: Check every uploaded document for quality and consistency."""
    trace: List[str] = list(state.get("trace_log", []))
    errors: List[str] = list(state.get("errors", []))
    confidence: float = state.get("confidence_score", 0.9)

    trace.append("═" * 60)
    trace.append("AGENT 2 — DOCUMENT QUALITY: Checking documents")

    documents: List[Dict[str, Any]] = state.get("documents", [])
    problem_docs: List[str] = []
    re_upload_messages: List[str] = []

    # ── Check 1: Quality flag per document ───────────────────────────────────
    for doc in documents:
        file_id = doc.get("file_id", "?")
        file_name = doc.get("file_name", file_id)
        quality = (doc.get("quality") or "GOOD").upper()
        doc_type = doc.get("actual_type", "UNKNOWN")

        trace.append(f"  Checking '{file_name}' ({doc_type}) — quality: {quality}")

        if quality == "UNREADABLE":
            msg = (
                f"The {doc_type} you uploaded ('{file_name}') cannot be read — "
                f"it appears blurry or too dark. Please re-upload a clear, well-lit photo."
            )
            re_upload_messages.append(msg)
            problem_docs.append(file_id)
            confidence -= CONFIDENCE_REDUCTION["UNREADABLE"]
            trace.append(f"    ✗ UNREADABLE — confidence ↓ by {CONFIDENCE_REDUCTION['UNREADABLE']}")
            errors.append(msg)

        elif quality == "POOR":
            msg = (
                f"'{file_name}' ({doc_type}) is low quality — some fields may be missed. "
                f"Re-uploading a clearer image will improve accuracy."
            )
            re_upload_messages.append(msg)
            confidence -= CONFIDENCE_REDUCTION["POOR"]
            trace.append(f"    ⚠ POOR quality — confidence ↓ by {CONFIDENCE_REDUCTION['POOR']}")

        else:
            trace.append(f"    ✓ Quality OK")

    # ── Check 2: Patient name consistency across documents ────────────────────
    # This catches TC003 (different patient names on different docs)
    patient_names_on_docs: Dict[str, str] = {}   # file_id → patient name
    for doc in documents:
        name_on_doc = doc.get("patient_name_on_doc")
        if name_on_doc:
            patient_names_on_docs[doc.get("file_id", "?")] = name_on_doc

    if len(set(patient_names_on_docs.values())) > 1:
        # Multiple distinct patient names found across documents
        detail = "; ".join(
            f"'{fid}' shows '{name}'"
            for fid, name in patient_names_on_docs.items()
        )
        msg = (
            f"Documents appear to belong to different patients: {detail}. "
            f"All documents in a claim must be for the same patient. "
            f"Please verify and resubmit."
        )
        trace.append(f"  ✗ PATIENT NAME MISMATCH: {detail}")
        errors.append(msg)
        confidence -= CONFIDENCE_REDUCTION["PATIENT_MISMATCH"]

        return {
            "trace_log": trace,
            "errors": errors,
            "confidence_score": max(0.0, confidence),
            "pipeline_status": "EARLY_EXIT",
            "decision": None,
            "rejection_reasons": ["PATIENT_NAME_MISMATCH"],
            "re_upload_required": False,
            "re_upload_message": msg,
        }

    # ── If any documents need re-upload, pause the pipeline ──────────────────
    if problem_docs:
        combined_msg = " | ".join(re_upload_messages)
        trace.append(f"  ⚠ Re-upload required for {len(problem_docs)} document(s)")
        trace.append("AGENT 2 — DOCUMENT QUALITY: Re-upload requested")

        return {
            "trace_log": trace,
            "errors": errors,
            "confidence_score": max(0.0, confidence),
            "pipeline_status": "RE_UPLOAD",
            "decision": None,
            "re_upload_required": True,
            "re_upload_message": combined_msg,
        }

    # ── All good ──────────────────────────────────────────────────────────────
    trace.append("  ✓ All documents passed quality checks")
    trace.append("AGENT 2 — DOCUMENT QUALITY: Passed ✓")

    return {
        "trace_log": trace,
        "errors": errors,
        "confidence_score": max(0.0, confidence),
        "pipeline_status": "CONTINUE",
        "re_upload_required": False,
        "re_upload_message": None,
    }
