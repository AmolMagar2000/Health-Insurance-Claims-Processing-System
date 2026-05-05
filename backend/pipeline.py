"""
pipeline.py
===========
LangGraph Pipeline Definition

Wires the five agents together with conditional routing edges.

Graph flow:
    START
    → gatekeeper_node         (validate docs & member)
    → document_quality_node   (check readability & consistency)
    → extractor_node          (async — calls Gemini)
    → adjudicator_node        (pure Python policy logic)
    → auditor_node            (fraud checks + finalise)
    → END

Conditional edges:
  • gatekeeper    → early_exit if pipeline_status == EARLY_EXIT
  • doc_quality   → early_exit if pipeline_status in (EARLY_EXIT, RE_UPLOAD)
  • extractor     → manual_review if decision == MANUAL_REVIEW
  • adjudicator   → auditor (always — auditor makes the final routing call)
  • auditor       → END

Two terminal nodes (early_exit, manual_review) are lightweight nodes
that simply stamp a final decision onto the state before END.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from langgraph.graph import END, StateGraph

from models import ClaimState
from nodes.adjudicator import adjudicator_node
from nodes.auditor import auditor_node
from nodes.document_quality import document_quality_node
from nodes.extractor import extractor_node
from nodes.gatekeeper import gatekeeper_node

logger = logging.getLogger(__name__)


# ── Terminal nodes ────────────────────────────────────────────────────────────

def early_exit_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Called when the pipeline detects a fatal document or member problem.
    Stamps the trace and returns — no decision is made on the claim itself.
    """
    trace = list(state.get("trace_log", []))
    trace.append("PIPELINE TERMINATED — EARLY EXIT")
    trace.append(
        "The claim was stopped before processing. "
        "Please address the error(s) above and resubmit."
    )
    return {"trace_log": trace, "pipeline_status": "EARLY_EXIT"}


def manual_review_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Stamps the claim as MANUAL_REVIEW with a clear explanation.
    The claim is not auto-rejected — it goes to a human reviewer.
    """
    trace = list(state.get("trace_log", []))
    trace.append("PIPELINE COMPLETE — ROUTED TO MANUAL REVIEW")
    trace.append(
        "This claim requires human review. "
        "Check fraud_flags and errors for the reason."
    )
    return {
        "trace_log": trace,
        "decision": "MANUAL_REVIEW",
        "pipeline_status": "MANUAL_REVIEW",
    }


# ── Routing functions (edges) ─────────────────────────────────────────────────

def route_after_gatekeeper(state: Dict[str, Any]) -> str:
    """After gatekeeper: stop if docs are wrong, else continue."""
    if state.get("pipeline_status") in ("EARLY_EXIT",):
        return "early_exit"
    return "document_quality"


def route_after_quality(state: Dict[str, Any]) -> str:
    """After quality check: stop if re-upload needed or patient mismatch."""
    status = state.get("pipeline_status", "CONTINUE")
    if status in ("EARLY_EXIT", "RE_UPLOAD"):
        return "early_exit"
    return "extractor"


def route_after_extractor(state: Dict[str, Any]) -> str:
    """After extraction: send to manual review if extraction completely failed."""
    if state.get("decision") == "MANUAL_REVIEW":
        return "manual_review"
    return "adjudicator"


def route_after_adjudicator(state: Dict[str, Any]) -> str:
    """After adjudication: always go to auditor for fraud checks."""
    # Even REJECTED claims go through the auditor for fraud screening
    return "auditor"


def route_after_auditor(state: Dict[str, Any]) -> str:
    """After audit: route to manual_review if fraud signals present, else END."""
    if state.get("pipeline_status") == "MANUAL_REVIEW":
        return "manual_review"
    return END


# ── Async wrapper for extractor_node ─────────────────────────────────────────
# LangGraph nodes must be synchronous; we wrap the async extractor.

def extractor_node_sync(state: Dict[str, Any]) -> Dict[str, Any]:
    """Synchronous wrapper that runs the async extractor in an event loop."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're inside an existing event loop (e.g. FastAPI) — use a new thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, extractor_node(state))
                return future.result()
        else:
            return loop.run_until_complete(extractor_node(state))
    except RuntimeError:
        # Fallback: create a fresh event loop
        return asyncio.run(extractor_node(state))


# ── Build the graph ───────────────────────────────────────────────────────────

def build_pipeline() -> Any:
    """
    Construct and compile the LangGraph StateGraph.
    Returns a compiled graph that can be invoked with a ClaimState dict.
    """
    graph = StateGraph(ClaimState)

    # ── Register all nodes ────────────────────────────────────────────────────
    graph.add_node("gatekeeper",       gatekeeper_node)
    graph.add_node("document_quality", document_quality_node)
    graph.add_node("extractor",        extractor_node_sync)   # sync wrapper
    graph.add_node("adjudicator",      adjudicator_node)
    graph.add_node("auditor",          auditor_node)
    graph.add_node("early_exit",       early_exit_node)
    graph.add_node("manual_review",    manual_review_node)

    # ── Entry point ───────────────────────────────────────────────────────────
    graph.set_entry_point("gatekeeper")

    # ── Edges ─────────────────────────────────────────────────────────────────
    graph.add_conditional_edges(
        "gatekeeper",
        route_after_gatekeeper,
        {"early_exit": "early_exit", "document_quality": "document_quality"},
    )
    graph.add_conditional_edges(
        "document_quality",
        route_after_quality,
        {"early_exit": "early_exit", "extractor": "extractor"},
    )
    graph.add_conditional_edges(
        "extractor",
        route_after_extractor,
        {"manual_review": "manual_review", "adjudicator": "adjudicator"},
    )
    graph.add_conditional_edges(
        "adjudicator",
        route_after_adjudicator,
        {"auditor": "auditor"},
    )
    graph.add_conditional_edges(
        "auditor",
        route_after_auditor,
        {"manual_review": "manual_review", END: END},
    )

    graph.add_edge("early_exit",    END)
    graph.add_edge("manual_review", END)

    return graph.compile()


# ── Module-level compiled pipeline (singleton) ───────────────────────────────
# Import this in main.py:  from pipeline import claims_pipeline

claims_pipeline = build_pipeline()
