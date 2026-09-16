from __future__ import annotations
from typing import Any, TypedDict
from app.models.schemas import Policy, DocumentChunk, ExtractedTerms, ComplianceResult, RiskSummary, RiskScore, Evidence

class ReviewState(TypedDict, total=False):
    document_id: str
    deal_path: str
    policy_path: str
    policy: Policy
    pages: list[dict[str, Any]]
    chunks: list[DocumentChunk]
    terms: ExtractedTerms
    evidence: list[Evidence]
    _evidence_by_rule: dict[str, list[dict[str, Any]]]
    compliance: list[ComplianceResult]
    risk_summary: RiskSummary
    risk_score: RiskScore
    report_json_path: str
    report_pdf_path: str
    errors: list[dict[str, Any]]
    retry_counts: dict[str, int]
    failure_reasons: dict[str, str]
    human_review_reasons: list[str]
    audit: list[dict[str, Any]]
    started_at: str
    completed_at: str
    status: str
