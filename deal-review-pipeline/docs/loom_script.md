# 5–7 minute Loom demonstration script

1. **0:00–0:40 — Problem:** explain that the input is a synthetic deal PDF plus a dynamic policy and the output is evidence-backed review, not an LLM-generated opinion.
2. **0:40–1:30 — Architecture:** show `docs/architecture.md`; emphasize that LangGraph is the orchestrator and there is no LLM orchestrator.
3. **1:30–2:10 — Ingestion:** upload the edge-case PDF and point out that it is image-heavy; explain native extraction + RapidOCR fallback and page preservation.
4. **2:10–3:00 — Agents:** show structured term extraction, hybrid evidence retrieval, and the compliance matrix. Open an evidence row to demonstrate page/chunk traceability.
5. **3:00–3:50 — Deterministic controls:** show the rule result and explain that arithmetic/date/simple logic is checked in Python rather than invented by the LLM.
6. **3:50–4:40 — Risk:** show the risk register, score factors, and human-review reasons. Explain that the score is computed from explicit configurable weights.
7. **4:40–5:30 — Normal case:** run the normal synthetic agreement and show the same workflow end-to-end.
8. **5:30–6:10 — Failure handling:** briefly demonstrate or show code for retry counters, failure reasons and conditional human-review routing.
9. **6:10–6:40 — Deliverables:** download JSON/PDF and show the audit metadata.
10. **6:40–7:00 — Close:** mention limitations: synthetic policy/data, OCR dependence, local storage and configurable model provider.
