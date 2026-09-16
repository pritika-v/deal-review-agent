# Multi-Agent Deal Review Pipeline

A production-style take-home implementation for evidence-backed deal review using **LangGraph**, OCR-aware document ingestion, hybrid retrieval, LLM reasoning, deterministic compliance checks, transparent risk scoring, SQLite/ChromaDB storage, and Streamlit.

## Architecture

```text
Streamlit UI
    |
    v
LangGraph StateGraph (workflow/orchestration; no LLM orchestrator)
    |
    +--> Policy Validation --> Document Ingestion --> Term Extraction Agent
    |                                      |                 |
    |                                      |                 v
    |                                      +----------> Hybrid Evidence Retrieval
    |                                                        |
    |                                                        v
    |                                               Compliance Review Agent
    |                                                        |
    |                                                        v
    |                                               Risk & Summary Agent
    |                                                        |
    |                                                        v
    |                                             Deterministic Risk Engine
    |                                                        |
    |                                                        v
    |                                                Jinja2 Report Generator
    |                                                        |
    +--------------------------------------------------------+
                         |
                         v
              SQLite + ChromaDB + filesystem
                         |
                         v
                  Streamlit Results
```

## What is actually implemented

- Dynamic policy loading and Pydantic validation.
- PDF/DOCX/JSON policy normalization.
- Scanned/image PDF support: native PDF text first, then page rendering + RapidOCR fallback.
- Page-aware document model with sections/clauses/tables when available.
- Term Extraction Agent using an OpenRouter-compatible LLM and strict Pydantic validation.
- Hybrid evidence retrieval: BM25 + dense embeddings + CrossEncoder reranking.
- ChromaDB stores chunks and embeddings with page/section/clause/document metadata.
- Compliance Review Agent combines LLM reasoning with deterministic numeric/date/logical checks.
- Risk & Summary Agent generates grounded risks, executive summary and follow-up actions.
- Deterministic 0–100 risk engine with configurable weights and factor-by-factor explanation.
- LangGraph retry/error routing and human-review escalation.
- Jinja2 HTML-to-PDF reporting plus JSON reporting; no extra LLM call for report assembly.
- SQLite audit/workflow metadata and filesystem artifact storage.
- Streamlit UI for uploads, run status, findings and downloads.
- Normal/edge synthetic document tests.

## Quick start

### 1. Create the environment

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

macOS/Linux:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Configure OpenRouter

Copy `.env.example` to `.env` and set:

```env
OPENROUTER_API_KEY=your_key_here
OPENROUTER_MODEL=google/gemma-4-26b-a4b
```

The model is configurable because model availability can change. The application never hard-codes an API key.

### 3. Run

```bash
streamlit run app/ui/streamlit_app.py
```

Upload either sample PDF and choose `data/policies/TN_RERA_Compliance_Rules.json`.

### 4. Tests

Fast offline tests (no API key required):

```bash
pytest -q
```

Run the real pipeline from CLI:

```bash
python scripts/run_review.py --deal data/sample/normal_deal.pdf --policy data/policies/TN_RERA_Compliance_Rules.json
python scripts/run_review.py --deal data/sample/edge_case_deal.pdf --policy data/policies/TN_RERA_Compliance_Rules.json
```

The CLI requires `OPENROUTER_API_KEY` for real LLM extraction/review.

## Risk scoring

The score is deterministic and bounded to 100. Default configurable points are:

- Critical compliance FAIL: +30 each
- High compliance FAIL: +15 each
- Medium compliance FAIL: +7 each
- Critical missing evidence: +20 each
- High missing evidence: +10 each
- Material ambiguity: +8 each
- Material uncertainty: +6 each
- Financial inconsistency: +12 each
- Conflicting document information: +15 each
- Human-review escalation: +10

The raw sum is capped at 100. Risk level is derived from configurable bands: 0–24 LOW, 25–49 MEDIUM, 50–74 HIGH, 75–100 CRITICAL. This is a synthetic workflow score, not legal advice and not a legally authoritative conclusion.

## Status semantics

`PASS` means the supplied evidence and deterministic checks support the rule.
`FAIL` means a rule is contradicted or a required condition is not satisfied based on available evidence.
`HUMAN_REVIEW` means the available evidence is insufficient, ambiguous, conflicting, or the workflow experienced a material failure.

Missing information is never converted into invented facts.

## Human review / retry strategy

Each retryable graph node increments a node-specific retry counter and records an error/failure reason. `MAX_RETRIES` defaults to 2. Conditional LangGraph edges route retryable failures back to the relevant node. After the retry budget is exhausted, the graph routes to human-review/failure handling rather than looping indefinitely.

Examples:

- ingestion/OCR failure -> retry -> human review
- extraction validation/low confidence -> retry -> human review
- weak evidence -> retry retrieval -> `EVIDENCE_NOT_FOUND`/human review
- malformed compliance output -> retry -> human review
- risk generation failure -> retry -> human review

## Policy

The supplied policy is treated as canonical. It contains 20 Tamil Nadu RERA rules, including project registration, title/encumbrances, approvals, 70% separate account, controlled withdrawals, agreement form, interest, refund, promoter delay, payment obligations, approved-plan conformity, defect liability, association/handover, amendments and registered-agent checks. The policy is loaded from JSON rather than embedded in Python.

## Sample-case expectations

### Normal synthetic agreement

The supplied normal document is a Gurugram agreement. It contains explicit party/property/payment/possession/encumbrance statements and a detailed payment schedule. It is intentionally **not a Tamil Nadu RERA document**, so the policy engine must surface jurisdiction/policy applicability gaps rather than silently treating missing Tamil Nadu evidence as present. The system can still demonstrate extraction, evidence and risk behavior.

### Edge synthetic agreement

The edge document is an image-heavy five-page Gurugram agreement with OCR-sensitive fields and visibly incomplete/garbled party fields on page 2. The pipeline should preserve uncertainty instead of filling blanks. It also contains an apparent payment inconsistency that the deterministic checks can flag for review. The page images are the source of truth when OCR text is incomplete.

## Assignment mapping

| Assignment requirement | Implementation |
|---|---|
| Term Extraction Agent | `app/agents/term_extraction.py` |
| Compliance Review Agent | `app/agents/compliance.py` |
| Risk & Summary Agent | `app/agents/risk_summary.py` |
| Orchestration/shared state | `app/graph/workflow.py`, `app/models/state.py` |
| Traceability | `Evidence`, `Term`, `ComplianceResult` models + page metadata |
| Uncertainty/human escalation | `app/graph/workflow.py`, `app/graph/routing.py` |
| Normal + edge validation | `tests/test_pipeline_cases.py` |
| OCR/document ingestion | `app/ingestion/ingest.py` |
| BM25+dense+rerank | `app/retrieval/hybrid.py` |
| Deterministic risk | `app/risk/scoring.py` |
| Reports | `app/reports/generator.py` + Jinja template |
| Storage/audit | `app/storage/sqlite.py`, ChromaDB adapter |
| UI | `app/ui/streamlit_app.py` |

## Limitations / assumptions

1. OCR quality depends on the local OCR model and scan quality.
2. The synthetic policy is used as supplied; the application does not independently establish the legal validity of its rules.
3. A compliance `FAIL` is a workflow finding against the supplied policy/evidence, not legal advice.
4. Dense retrieval and reranking download open-source model weights on first use unless already cached.
5. The supplied deals are Gurugram documents while the supplied policy is Tamil Nadu-specific; the mismatch is intentionally retained as an applicability signal.
6. ChromaDB and SQLite are local take-home storage; interfaces are isolated so PostgreSQL/pgvector/S3 can replace them later.
7. For policy PDF/DOCX conversion, the normalization layer asks an LLM to map source text into the standardized schema only when needed; the resulting JSON is schema-validated before review.
