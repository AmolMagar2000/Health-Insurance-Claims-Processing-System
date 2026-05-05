"""
models.py
=========
Central data contracts for the claims pipeline.

Three layers:
  1. ClaimSubmission   – what the API receives from the client
  2. ClaimState        – the TypedDict that LangGraph nodes read/write
  3. ClaimStateModel   – the Pydantic mirror used for API response serialisation
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from typing_extensions import TypedDict


# ─────────────────────────────────────────────
# 1. API INPUT
# ─────────────────────────────────────────────

class DocumentInput(BaseModel):
    """One uploaded document — either a real file (base64) or a test fixture (content dict)."""
    file_id: str
    file_name: Optional[str] = None
    actual_type: Optional[str] = None          # PRESCRIPTION | HOSPITAL_BILL | etc.
    quality: Optional[str] = "GOOD"            # GOOD | POOR | UNREADABLE
    content: Optional[Dict[str, Any]] = None   # pre-extracted dict (test mode)
    patient_name_on_doc: Optional[str] = None  # used in TC003 cross-patient check
    base64_data: Optional[str] = None          # real file payload
    mime_type: Optional[str] = None            # image/jpeg | application/pdf


class ClaimsHistoryItem(BaseModel):
    claim_id: str
    date: str
    amount: float
    provider: Optional[str] = None


class ClaimSubmission(BaseModel):
    """
    What the frontend POSTs to /submit-claim.
    Every field mirrors the test_cases.json input shape.
    """
    member_id: str
    policy_id: str
    claim_category: str          # CONSULTATION | DENTAL | DIAGNOSTIC | PHARMACY | VISION | ALTERNATIVE_MEDICINE
    treatment_date: str          # ISO date string, e.g. "2024-11-01"
    claimed_amount: float
    documents: List[DocumentInput]
    hospital_name: Optional[str] = None
    claims_history: Optional[List[Dict[str, Any]]] = None
    ytd_claims_amount: Optional[float] = 0.0
    simulate_component_failure: Optional[bool] = False
    pre_auth_id: Optional[str] = None          # if member obtained pre-auth, pass it here


# ─────────────────────────────────────────────
# 2. LANGGRAPH STATE (TypedDict)
#    LangGraph merges dicts returned by each node
#    into this shared state object.
# ─────────────────────────────────────────────

class ClaimState(TypedDict):
    # ── Identity ──────────────────────────────
    claim_id: str
    member_id: str
    policy_id: str

    # ── Input details ─────────────────────────
    claimed_amount: float
    category: str
    treatment_date: str
    hospital_name: Optional[str]

    # ── Documents & history ───────────────────
    documents: List[Dict[str, Any]]
    claims_history: List[Dict[str, Any]]
    ytd_claims_amount: float
    pre_auth_id: Optional[str]

    # ── Feature flags ─────────────────────────
    simulate_component_failure: bool

    # ── Pipeline outputs ──────────────────────
    extracted_data: Dict[str, Any]
    decision: Optional[str]              # APPROVED | PARTIAL | REJECTED | MANUAL_REVIEW
    approved_amount: float
    confidence_score: float

    # ── Explainability ────────────────────────
    trace_log: List[str]
    errors: List[str]
    fraud_flags: List[str]
    rejection_reasons: List[str]
    line_item_decisions: List[Dict[str, Any]]  # per-item breakdown for PARTIAL decisions

    # ── Routing ───────────────────────────────
    pipeline_status: str                 # CONTINUE | EARLY_EXIT | RE_UPLOAD | MANUAL_REVIEW
    re_upload_required: bool
    re_upload_message: Optional[str]

    # ── Member info (populated by gatekeeper) ─
    member_info: Optional[Dict[str, Any]]


# ─────────────────────────────────────────────
# 3. API RESPONSE MODEL (Pydantic)
#    Serialises the final ClaimState to JSON.
# ─────────────────────────────────────────────

class ClaimStateModel(BaseModel):
    """Pydantic model returned by /submit-claim — mirrors ClaimState exactly."""
    claim_id: str = Field(default_factory=lambda: f"CLM_{uuid.uuid4().hex[:8].upper()}")
    member_id: str
    policy_id: str
    claimed_amount: float
    category: str
    treatment_date: str
    hospital_name: Optional[str] = None
    documents: List[Dict[str, Any]] = Field(default_factory=list)
    claims_history: List[Dict[str, Any]] = Field(default_factory=list)
    ytd_claims_amount: float = 0.0
    pre_auth_id: Optional[str] = None
    simulate_component_failure: bool = False
    extracted_data: Dict[str, Any] = Field(default_factory=dict)
    decision: Optional[str] = None
    approved_amount: float = 0.0
    confidence_score: float = 0.9
    trace_log: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    fraud_flags: List[str] = Field(default_factory=list)
    rejection_reasons: List[str] = Field(default_factory=list)
    line_item_decisions: List[Dict[str, Any]] = Field(default_factory=list)
    pipeline_status: str = "CONTINUE"
    re_upload_required: bool = False
    re_upload_message: Optional[str] = None
    member_info: Optional[Dict[str, Any]] = None


def build_initial_state(submission: ClaimSubmission) -> ClaimState:
    """Convert an API submission into a fresh LangGraph ClaimState."""
    return ClaimState(
        claim_id=f"CLM_{uuid.uuid4().hex[:8].upper()}",
        member_id=submission.member_id,
        policy_id=submission.policy_id,
        claimed_amount=submission.claimed_amount,
        category=submission.claim_category.upper(),
        treatment_date=submission.treatment_date,
        hospital_name=submission.hospital_name,
        documents=[d.model_dump() for d in submission.documents],
        claims_history=submission.claims_history or [],
        ytd_claims_amount=submission.ytd_claims_amount or 0.0,
        pre_auth_id=submission.pre_auth_id,
        simulate_component_failure=submission.simulate_component_failure or False,
        extracted_data={},
        decision=None,
        approved_amount=0.0,
        confidence_score=0.9,
        trace_log=[],
        errors=[],
        fraud_flags=[],
        rejection_reasons=[],
        line_item_decisions=[],
        pipeline_status="CONTINUE",
        re_upload_required=False,
        re_upload_message=None,
        member_info=None,
    )
