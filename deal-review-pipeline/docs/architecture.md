# One-page architecture diagram

```mermaid
flowchart TD
  UI[Streamlit UI] --> G[LangGraph StateGraph\nworkflow manager]
  G --> P[Policy Validation\nPydantic schema]
  P --> I[Document Ingestion\nPyMuPDF + RapidOCR]
  I --> T[Term Extraction Agent\nOpenRouter LLM + Pydantic]
  T --> E[Hybrid Evidence Retrieval\nBM25 + SentenceTransformer + ChromaDB + CrossEncoder]
  E --> C[Compliance Review Agent\nLLM + deterministic checks]
  C --> R[Risk & Summary Agent\nLLM reasoning]
  R --> S[Deterministic Risk Engine\nconfigurable 0-100]
  S --> F[Jinja2 Report Generator\nJSON + PDF]
  F --> ST[(SQLite + ChromaDB + filesystem)]
  ST --> UI2[Streamlit Results]
  P -. retry/error .-> H[Human Review]
  I -. retry/error .-> H
  T -. retry/error .-> H
  E -. retry/error .-> H
  C -. retry/error .-> H
  R -. retry/error .-> H
  H --> R
  G --- A[(Shared LangGraph State\nterms/evidence/compliance/risk/audit/retries)]
```

Key handoffs: page-aware document chunks -> structured terms -> retrieved evidence -> rule-level compliance results -> grounded risks/summary -> deterministic score -> final report.
