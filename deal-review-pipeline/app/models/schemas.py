from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field, ConfigDict

Status = Literal['PASS','FAIL','HUMAN_REVIEW']
Severity = Literal['LOW','MEDIUM','HIGH','CRITICAL']

class Evidence(BaseModel):
    document_id: str
    chunk_id: str
    text: str
    page: int
    section: str | None = None
    clause: str | None = None
    score: float = 0.0
    source: str = 'hybrid'

class Term(BaseModel):
    field: str
    value: Any
    confidence: float = Field(ge=0, le=1)
    page: int | None = None
    section: str | None = None
    clause: str | None = None
    supporting_source_text: str | None = None
    status: Literal['FOUND','MISSING','AMBIGUOUS','CONFLICT'] = 'FOUND'

class ExtractedTerms(BaseModel):
    terms: list[Term] = Field(default_factory=list)

class PolicyRule(BaseModel):
    model_config = ConfigDict(extra='allow')
    rule_id: str
    category: str
    name: str
    rule: str
    required_evidence: list[str] = Field(default_factory=list)
    severity: Severity
    check_type: str = 'LLM_PLUS_DETERMINISTIC'
    parameters: dict[str, Any] = Field(default_factory=dict)
    evidence_requirements: list[str] = Field(default_factory=list)

class Policy(BaseModel):
    document_title: str
    document_type: str
    jurisdiction: str | None = None
    policy_id: str = 'TN_RERA_DEMO'
    version: str = '1.0'
    rules: list[PolicyRule]

class ComplianceResult(BaseModel):
    rule_id: str
    status: Status
    severity: Severity
    rationale: str = ""
    evidence: list[Evidence] = Field(default_factory=list)
    page: int | None = None
    section: str | None = None
    missing_information: list[str] = Field(default_factory=list)
    ambiguity: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)
    deterministic_check: str | None = None

class RiskItem(BaseModel):
    risk_id: str
    category: str
    severity: Severity
    title: str
    description: str
    evidence: list[Evidence] = Field(default_factory=list)
    source_rule_ids: list[str] = Field(default_factory=list)
    action: str


class RiskSummary(BaseModel):
    risks: list[RiskItem] = Field(default_factory=list)
    executive_summary: str
    follow_up_actions: list[str] = Field(default_factory=list)

class RiskFactor(BaseModel):
    factor: str
    points: int
    reason: str

class RiskScore(BaseModel):
    risk_score: int = Field(ge=0, le=100)
    risk_level: Literal['LOW','MEDIUM','HIGH','CRITICAL']
    factors: list[RiskFactor] = Field(default_factory=list)
    status: Status

class DocumentChunk(BaseModel):
    document_id: str
    chunk_id: str
    page: int
    text: str
    section: str | None = None
    clause: str | None = None

class DealReport(BaseModel):
    schema_version: str = '1.0'
    document_id: str
    policy_id: str
    policy_version: str
    generated_at: str
    executive_summary: str
    deal_overview: dict[str, Any]
    extracted_terms: list[Term]
    evidence: list[Evidence]
    compliance_matrix: list[ComplianceResult]
    risk_register: list[RiskItem]
    missing_information: list[str]
    ambiguities: list[str]
    high_risk_findings: list[str]
    follow_up_actions: list[str]
    risk_score: RiskScore
    human_review_reasons: list[str]
    audit_metadata: dict[str, Any]
