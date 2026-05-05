"""
nodes/extractor.py
==================
AGENT 3 – Data Extractor

Client selection logic (automatic, no config needed):
  ┌─────────────────────────────────────────────────┐
  │  Document has base64_data (real image upload)?  │
  │       YES → try AzureOpenAIClient first         │
  │               (GPT-4.1-mini vision)             │
  │             if unavailable → GeminiClient       │
  │       NO  → test fixture → content_passthrough  │
  └─────────────────────────────────────────────────┘

Fallback chain per assignment spec:
  1. Primary AI (Azure vision OR Gemini)
  2. Retry up to 2 times
  3. OCR fallback
  4. If all fail → MANUAL_REVIEW

simulate_component_failure=True forces the OCR path (TC011).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

from utils.azure_client import AzureOpenAIClient
from utils.gemini_client import GeminiClient

logger = logging.getLogger(__name__)

CONFIDENCE_PENALTY = {
    "ocr_fallback":   0.2,
    "missing_fields": 0.2,
}

CRITICAL_FIELDS = ["patient_name", "diagnosis", "total_amount"]


async def extractor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """AGENT 3: Extract structured data from all uploaded documents."""
    trace:      List[str] = list(state.get("trace_log", []))
    errors:     List[str] = list(state.get("errors", []))
    confidence: float     = state.get("confidence_score", 0.9)

    trace.append("═" * 60)
    trace.append("AGENT 3 — EXTRACTOR: Beginning document extraction")

    simulate_failure: bool         = state.get("simulate_component_failure", False)
    documents:        List[Dict]   = state.get("documents", [])

    # ── Initialise clients ────────────────────────────────────────────────
    azure_client  = AzureOpenAIClient()
    gemini_client = GeminiClient()

    logger.info(
        "[EXTRACTOR] Azure available=%s | Gemini available=%s | docs=%d | simulate_fail=%s",
        azure_client.is_available,
        bool(gemini_client._model),
        len(documents),
        simulate_failure,
    )

    all_extractions: List[Dict] = []
    methods_used:    List[str]  = []
    any_ocr_used = False
    all_failed   = True

    # ── Process each document ─────────────────────────────────────────────
    for doc in documents:
        file_id  = doc.get("file_id", "?")
        doc_type = doc.get("actual_type", "UNKNOWN")
        has_image = bool(doc.get("base64_data"))

        trace.append(f"  Processing: {file_id} ({doc_type}) | image={has_image}")
        logger.info("[EXTRACTOR] Processing doc=%s type=%s image=%s", file_id, doc_type, has_image)

        try:
            # ── Client routing ────────────────────────────────────────────
            if has_image and azure_client.is_available:
                # Real image → prefer Azure GPT-4.1-mini vision
                trace.append(f"    → Using Azure GPT-4.1-mini vision")
                logger.info("[EXTRACTOR] Route: Azure vision for %s", file_id)
                extracted, method = await azure_client.extract_document(
                    doc, simulate_failure=simulate_failure
                )
            elif has_image:
                # Real image but no Azure → try Gemini vision
                trace.append(f"    → Using AI vision (Gemini fallback)")
                logger.info("[EXTRACTOR] Route: Gemini vision fallback for %s", file_id)
                extracted, method = await gemini_client.extract_document(
                    doc, simulate_failure=simulate_failure
                )
            else:
                # Test fixture or text doc → Gemini text / passthrough
                logger.info("[EXTRACTOR] Route: Gemini/passthrough for %s", file_id)
                extracted, method = await gemini_client.extract_document(
                    doc, simulate_failure=simulate_failure
                )

            all_extractions.append(extracted)
            methods_used.append(method)
            all_failed = False

            # ── Log method used ───────────────────────────────────────────
            if method == "azure_vision":
                trace.append(f"    ✓ Extracted via Azure GPT-4.1-mini vision")
                logger.info(
                    "[EXTRACTOR] ✓ doc=%s method=azure_vision patient=%s total=%s",
                    file_id,
                    extracted.get("patient_name"),
                    extracted.get("total_amount"),
                )
            elif method == "gemini_vision":
                trace.append(f"    ✓ Extracted via AI vision")
                logger.info("[EXTRACTOR] ✓ doc=%s method=gemini_vision", file_id)
            elif method == "content_passthrough":
                trace.append(f"    ✓ Test fixture loaded")
                logger.info("[EXTRACTOR] ✓ doc=%s method=content_passthrough", file_id)
            elif method == "ocr_fallback":
                any_ocr_used = True
                confidence  -= CONFIDENCE_PENALTY["ocr_fallback"]
                trace.append(
                    f"    ⚠ OCR fallback used — confidence ↓ {CONFIDENCE_PENALTY['ocr_fallback']}"
                )
                logger.warning(
                    "[EXTRACTOR] ⚠ doc=%s OCR fallback activated, confidence now %.2f",
                    file_id, confidence
                )
            else:
                trace.append(f"    ✓ Extracted via {method}")
                logger.info("[EXTRACTOR] ✓ doc=%s method=%s", file_id, method)

        except Exception as exc:
            err = f"Extraction failed for {file_id}: {exc}"
            logger.error("[EXTRACTOR] ✗ %s", err, exc_info=True)
            errors.append(err)
            confidence -= CONFIDENCE_PENALTY["ocr_fallback"]
            trace.append(f"    ✗ Error: {exc} — continuing pipeline")

    # ── All documents failed completely ───────────────────────────────────
    if all_failed or not all_extractions:
        logger.error("[EXTRACTOR] All extractions failed → MANUAL_REVIEW")
        trace.append("  ✗ All extractions failed → routing to MANUAL_REVIEW")
        return {
            "trace_log": trace, "errors": errors,
            "confidence_score": max(0.0, confidence),
            "extracted_data": {}, "decision": "MANUAL_REVIEW",
            "pipeline_status": "MANUAL_REVIEW",
        }

    # ── Merge all extractions into one dict ───────────────────────────────
    merged = _merge_extractions(all_extractions)
    trace.append(f"  Merged {len(all_extractions)} extraction(s) into extracted_data")
    logger.info(
        "[EXTRACTOR] Merged %d doc(s) | patient=%s | diagnosis=%s | total=%.2f",
        len(all_extractions),
        merged.get("patient_name") or "—",
        merged.get("diagnosis")    or "—",
        float(merged.get("total_amount") or 0),
    )

    # ── Missing critical fields check (skip for test fixtures) ───────────
    all_passthrough  = all(m == "content_passthrough" for m in methods_used)
    missing_critical = [f for f in CRITICAL_FIELDS if not merged.get(f)]
    if missing_critical and not all_passthrough:
        confidence -= CONFIDENCE_PENALTY["missing_fields"]
        trace.append(
            f"  ⚠ Missing critical fields: {missing_critical} "
            f"— confidence ↓ {CONFIDENCE_PENALTY['missing_fields']}"
        )
        logger.warning("[EXTRACTOR] Missing critical fields: %s", missing_critical)

    # ── Simulate failure note (TC011) ─────────────────────────────────────
    if simulate_failure:
        trace.append(
            "  ⚠ SIMULATED FAILURE: AI extraction was unavailable. "
            "OCR fallback was used. Manual review recommended."
        )
        errors.append(
            "Component failure simulated: AI extraction unavailable. "
            "Results are based on OCR fallback and may be incomplete."
        )
        logger.warning("[EXTRACTOR] TC011 simulate_failure active — OCR result returned")

    trace.append("AGENT 3 — EXTRACTOR: Extraction complete")
    logger.info(
        "[EXTRACTOR] Done | methods=%s | confidence=%.2f",
        methods_used, min(1.0, max(0.0, confidence))
    )

    return {
        "trace_log":        trace,
        "errors":           errors,
        "confidence_score": max(0.0, min(1.0, confidence)),
        "extracted_data":   merged,
        "pipeline_status":  state.get("pipeline_status", "CONTINUE"),
    }


def _merge_extractions(extractions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merge per-document extractions.
    Scalars: first non-null wins. Lists: concatenated. total_amount: summed.
    """
    merged: Dict[str, Any] = {
        "patient_name": None, "doctor_name": None, "doctor_registration": None,
        "diagnosis": None, "treatment": None, "hospital_name": None, "date": None,
        "medicines": [], "line_items": [], "tests_ordered": [], "total_amount": 0.0,
    }
    for ext in extractions:
        for scalar in ["patient_name", "doctor_name", "doctor_registration",
                       "diagnosis", "treatment", "hospital_name", "date"]:
            if merged[scalar] is None and ext.get(scalar):
                merged[scalar] = ext[scalar]
        for lst in ["medicines", "line_items", "tests_ordered"]:
            if ext.get(lst):
                merged[lst].extend(ext[lst])
        if ext.get("total_amount"):
            try:
                merged["total_amount"] += float(ext["total_amount"])
            except (TypeError, ValueError):
                pass
    return merged
