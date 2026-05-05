# Plum Health Insurance Claims Processing System

Multi-agent AI pipeline for adjudicating health insurance claims.
**12/12 test cases pass.**

---

## Architecture

```
CLAIM SUBMISSION
      │
      ▼
┌─────────────────────────────────────────────────────────────────┐
│                     LangGraph Pipeline                          │
│                                                                 │
│  [1] Gatekeeper       → validate member + doc types            │
│         │  (wrong docs → EARLY_EXIT)                           │
│         ▼                                                       │
│  [2] Doc Quality      → check readability + patient mismatch   │
│         │  (unreadable → RE_UPLOAD; mismatch → EARLY_EXIT)     │
│         ▼                                                       │
│  [3] Extractor        → Gemini API → retry → OCR fallback      │
│         │  (all fail → MANUAL_REVIEW)                          │
│         ▼                                                       │
│  [4] Adjudicator      → pure Python policy logic               │
│         │  (exclusion / waiting period / pre-auth / limits)    │
│         ▼                                                       │
│  [5] Auditor          → fraud detection → final output         │
│         │  (fraud signals → MANUAL_REVIEW)                     │
│         ▼                                                       │
│       END                                                       │
└─────────────────────────────────────────────────────────────────┘
```

## Stack

| Layer | Tech |
|-------|------|
| Frontend | React + Vite |
| Backend | FastAPI (async) |
| Orchestration | LangGraph |
| LLM | Google Gemini 1.5 Flash (+ OCR fallback) |
| Validation | Pydantic v2 |
| Policy | `policy_terms.json` (zero hardcoding) |

---

## Quick Start

### Backend

```bash
cd backend
pip install -r requirements.txt

# Optional: add Gemini key for real LLM extraction
cp .env.example .env
# edit .env

uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# opens on http://localhost:5173
```

### Run Eval (all 12 test cases)

```bash
cd backend
python eval_runner.py
```

---

## API

### POST /submit-claim

**Request:**
```json
{
  "member_id": "EMP001",
  "policy_id": "PLUM_GHI_2024",
  "claim_category": "CONSULTATION",
  "treatment_date": "2024-11-01",
  "claimed_amount": 1500,
  "hospital_name": "Apollo Hospitals",
  "documents": [
    {
      "file_id": "F001",
      "actual_type": "PRESCRIPTION",
      "quality": "GOOD",
      "content": { "doctor_name": "...", "diagnosis": "...", ... }
    }
  ],
  "claims_history": [],
  "simulate_component_failure": false
}
```

**Response:** Full `ClaimState` JSON including `decision`, `approved_amount`,
`confidence_score`, `trace_log`, `fraud_flags`, `rejection_reasons`,
`line_item_decisions`.

### GET /test-cases
Returns all 12 test cases for the demo UI.

### GET /members
Returns the member roster from `policy_terms.json`.

---

## Design Decisions & Trade-offs

### Why LangGraph?
Provides explicit state transitions and conditional routing. Every edge is a
named, testable function — not implicit control flow.

### Why pure Python in Adjudicator?
The assignment explicitly forbids LLM usage in policy logic. Deterministic
Python is auditable, fast, and produces the same output every run.

### Why exclusions before waiting periods?
An excluded procedure should be rejected as EXCLUDED even if it also happens
to fall within a waiting period. The exclusion is the primary business reason.

### What I'd change at 10x load
- Move Gemini calls to a job queue (Celery/RQ) with a result cache.
- Store `ClaimState` in Postgres with jsonb for full history.
- Separate the document store (S3) from the processing pipeline.
- Add a proper OCR microservice (not in-process Tesseract).
- Add structured logging (OpenTelemetry) instead of trace_log strings.

### Known Limitations
- The exclusion matcher uses keyword heuristics; a production system would
  use an ICD-10 code database for reliable diagnosis classification.
- OCR is simulated — real document images need Tesseract/PaddleOCR plumbing.
- No auth/JWT on API endpoints (out of scope for assignment).
