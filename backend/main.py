"""
main.py
=======
FastAPI application with detailed terminal logging.

Every claim prints a full pipeline summary to the terminal —
decisions, amounts, fraud flags, and the full trace — so you can
follow exactly what happened without opening the UI.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from models import ClaimStateModel, ClaimSubmission, build_initial_state
from pipeline import claims_pipeline
from utils.policy_loader import load_policy

# ── Terminal logging setup ────────────────────────────────────────────────────
# Uses ANSI colour codes so the terminal output is easy to scan at a glance.

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BLUE   = "\033[94m"
PURPLE = "\033[95m"
WHITE  = "\033[97m"

DECISION_COLOR = {
    "APPROVED":      GREEN,
    "PARTIAL":       YELLOW,
    "REJECTED":      RED,
    "MANUAL_REVIEW": PURPLE,
}

logging.basicConfig(
    level=logging.INFO,
    format=f"{DIM}%(asctime)s{RESET}  %(levelname)s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("claims.api")

# Suppress noisy third-party loggers
for noisy in ("httpx", "httpcore", "urllib3", "openai._base_client"):
    logging.getLogger(noisy).setLevel(logging.WARNING)


def _box(title: str, color: str = WHITE) -> str:
    width = 62
    bar = "═" * width
    return f"\n{color}{BOLD}╔{bar}╗\n║  {title:<{width - 2}}║\n╚{bar}╝{RESET}"


def _separator(char: str = "─", width: int = 64) -> str:
    return f"{DIM}{char * width}{RESET}"


def _log_claim_start(state: Dict[str, Any]) -> None:
    """Print a formatted start banner when a claim enters the pipeline."""
    print(_box(f"CLAIM RECEIVED  ·  {state['claim_id']}", CYAN))
    print(f"  {BOLD}Member      :{RESET} {state['member_id']}")
    print(f"  {BOLD}Category    :{RESET} {state['category']}")
    print(f"  {BOLD}Amount      :{RESET} ₹{state['claimed_amount']:,.0f}")
    print(f"  {BOLD}Date        :{RESET} {state['treatment_date']}")
    print(f"  {BOLD}Hospital    :{RESET} {state.get('hospital_name') or '—'}")
    print(f"  {BOLD}Documents   :{RESET} {len(state.get('documents', []))} file(s)")
    doc_types = [d.get("actual_type", "?") for d in state.get("documents", [])]
    print(f"  {BOLD}Doc types   :{RESET} {', '.join(doc_types)}")
    has_image = any(d.get("base64_data") for d in state.get("documents", []))
    print(f"  {BOLD}Upload mode :{RESET} {'YES — real image(s) present' if has_image else 'No — test fixture mode'}")
    if state.get("simulate_component_failure"):
        print(f"  {YELLOW}{BOLD}⚠  Simulate failure ON (TC011){RESET}")
    print(_separator())


def _log_claim_result(state: Dict[str, Any], elapsed_ms: float) -> None:
    """Print a formatted result summary after the pipeline completes."""
    decision = state.get("decision") or "—"
    d_color  = DECISION_COLOR.get(decision, WHITE)

    print(_box(f"PIPELINE RESULT  ·  {state.get('claim_id', '—')}", d_color))
    print(f"  {BOLD}Decision    :{RESET} {d_color}{BOLD}{decision}{RESET}")
    print(f"  {BOLD}Approved    :{RESET} ₹{state.get('approved_amount', 0):,.2f}")
    print(f"  {BOLD}Confidence  :{RESET} {state.get('confidence_score', 0):.0%}")
    print(f"  {BOLD}Pipeline    :{RESET} {state.get('pipeline_status', '—')}")
    print(f"  {BOLD}Duration    :{RESET} {elapsed_ms:.0f}ms")

    if state.get("rejection_reasons"):
        rr = ", ".join(state["rejection_reasons"])
        print(f"  {BOLD}Rejection   :{RESET} {RED}{rr}{RESET}")

    if state.get("fraud_flags"):
        for ff in state["fraud_flags"]:
            print(f"  {YELLOW}⚠  FRAUD FLAG:{RESET} {ff}")

    if state.get("errors"):
        for err in state["errors"][:3]:
            print(f"  {RED}✗  ERROR     :{RESET} {err[:100]}")

    # Extracted data summary
    ext = state.get("extracted_data", {})
    if ext:
        print(_separator("·"))
        print(f"  {DIM}Extracted — patient: {ext.get('patient_name') or '—'}"
              f"  |  diagnosis: {ext.get('diagnosis') or '—'}"
              f"  |  total: ₹{ext.get('total_amount') or '—'}{RESET}")

    # Line items
    items = state.get("line_item_decisions", [])
    if items:
        print(_separator("·"))
        for item in items:
            icon = f"{GREEN}✓{RESET}" if item.get("status") == "APPROVED" else f"{RED}✗{RESET}"
            print(
                f"  {icon}  {item.get('description', '?'):<35} "
                f"₹{item.get('claimed_amount', 0):>8,.0f}  [{item.get('status')}]"
            )

    # Trace summary (last 8 meaningful lines)
    trace = state.get("trace_log", [])
    meaningful = [l for l in trace if l.strip() and not l.startswith("═")][-8:]
    if meaningful:
        print(_separator("·"))
        print(f"  {DIM}Trace tail:{RESET}")
        for line in meaningful:
            color = GREEN if "✓" in line else (YELLOW if "⚠" in line else (RED if "✗" in line else DIM))
            indent = "    " if line.startswith("  ") else "  "
            print(f"{indent}{color}{line.strip()}{RESET}")

    print(_separator())
    print()


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Plum Health Claims Processing API",
    description="Multi-agent AI pipeline for health insurance claims adjudication",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routes ────────────────────────────────────────────────────────────────────
# ✅ FIXED — unique function names
@app.get("/")
def root():            # Azure health probe hits this
    return {"status": "ok", "service": "claims-pipeline"}

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "claims-pipeline"}


@app.get("/members")
def list_members():
    policy = load_policy()
    return {"members": policy.get("members", [])}


@app.get("/policy")
def get_policy():
    return load_policy()


@app.get("/test-cases")
def get_test_cases():
    tc_path = Path(__file__).parent / "test_cases.json"
    if tc_path.exists():
        with open(tc_path) as f:
            return json.load(f)
    raise HTTPException(status_code=404, detail="test_cases.json not found")


@app.post("/submit-claim", response_model=ClaimStateModel)
async def submit_claim(submission: ClaimSubmission) -> Dict[str, Any]:
    """
    Main claims endpoint. Runs the full LangGraph pipeline and returns
    the complete ClaimState including trace, decision, and amounts.
    """
    initial_state = build_initial_state(submission)

    # ── Print start banner ────────────────────────────────────────────────
    _log_claim_start(initial_state)
    t0 = time.perf_counter()

    try:
        final_state: Dict[str, Any] = claims_pipeline.invoke(initial_state)
    except Exception as exc:
        logger.exception("Pipeline crashed unexpectedly: %s", exc)
        initial_state["decision"]       = "MANUAL_REVIEW"
        initial_state["confidence_score"] = 0.0
        initial_state["errors"].append(f"Pipeline error: {exc}")
        initial_state["trace_log"].append(
            f"CRITICAL: Unhandled pipeline error: {exc}. Routed to manual review."
        )
        final_state = initial_state

    elapsed_ms = (time.perf_counter() - t0) * 1000

    # ── Print result banner ───────────────────────────────────────────────
    _log_claim_result(final_state, elapsed_ms)

    return final_state


# ── Startup banner ────────────────────────────────────────────────────────────

@app.on_event("startup")
async def _startup():
    from utils.azure_client  import AzureOpenAIClient
    from utils.gemini_client import GeminiClient
    import os

    azure  = AzureOpenAIClient()
    gemini = GeminiClient()

    print(_box("PLUM CLAIMS PIPELINE  ·  STARTING UP", CYAN))
    print(f"  {BOLD}FastAPI     :{RESET}  http://localhost:8000")
    print(f"  {BOLD}Docs        :{RESET}  http://localhost:8000/docs")
    print(f"  {BOLD}Azure AI    :{RESET}  {'✓ ' + GREEN + 'READY' + RESET + ' (' + azure.deployment + ')' if azure.is_available else RED + '✗ not configured (AZURE_OPENAI_KEY missing)' + RESET}")
    print(f"  {BOLD}Gemini AI   :{RESET}  {'✓ ' + GREEN + 'READY' + RESET if gemini._model else YELLOW + '⚠ not configured (GEMINI_API_KEY missing)' + RESET}")
    print(f"  {BOLD}Agents      :{RESET}  Gatekeeper → DocQuality → Extractor → Adjudicator → Auditor")
    print(f"  {BOLD}Vision route:{RESET}  {'Azure GPT-4.1-mini (primary)' if azure.is_available else 'Gemini (Azure unavailable)'}")
    print(_separator())
    print()
