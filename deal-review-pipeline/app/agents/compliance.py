from __future__ import annotations

import json
from typing import Any

from app.llm.openrouter import OpenRouterClient
from app.models.schemas import (
    ComplianceResult,
    Evidence,
    Policy,
    ExtractedTerms,
)


SYSTEM = """
You are a Compliance Review Agent.

Review each supplied policy rule against ONLY the supplied extracted terms,
evidence candidates, and deterministic checks.

Do not invent evidence, page numbers, clauses, facts, or numeric results.

Allowed status values:
- PASS
- FAIL
- HUMAN_REVIEW

If required evidence is absent, incomplete, ambiguous, or the deal is
outside the policy jurisdiction, use HUMAN_REVIEW unless a concrete
contradiction supports FAIL.

Return ONLY valid JSON.

Required top-level structure:

{
  "results": [
    {
      "rule_id": "R01",
      "status": "PASS",
      "severity": "LOW",
      "rationale": "Explanation",
      "evidence": [],
      "page": null,
      "section": null,
      "missing_information": [],
      "ambiguity": [],
      "confidence": 0.0,
      "deterministic_check": null
    }
  ]
}

IMPORTANT OUTPUT RULES:

1. evidence MUST be a JSON list.
2. Each evidence item MUST be a JSON object containing:
   document_id, chunk_id, text, page, section, clause, score, source.

3. NEVER return evidence as a plain string.
4. missing_information MUST be a JSON list of strings.
5. ambiguity MUST be a JSON list of strings.
6. deterministic_check MUST be either:
   "PASS", "FAIL", "NOT_CHECKED", or null.

7. confidence MUST be a number between 0 and 1.
8. severity MUST be one of:
   LOW, MEDIUM, HIGH, CRITICAL.

9. If there is no evidence, return:
   "evidence": []

10. If there is no missing information, return:
   "missing_information": []

11. If there is no ambiguity, return:
   "ambiguity": []

Evidence must come ONLY from the supplied evidence candidates.
"""


class ComplianceAgent:
    def __init__(self, llm=None):
        self.llm = llm or OpenRouterClient()

    @staticmethod
    def _as_list(value: Any) -> list:
        """
        Normalize values such as:
        None       -> []
        ""         -> []
        "abc"      -> ["abc"]
        ["a", "b"] -> ["a", "b"]
        """
        if value is None:
            return []

        if isinstance(value, list):
            return value

        if isinstance(value, str):
            value = value.strip()
            if not value:
                return []
            return [value]

        return [value]

    @staticmethod
    def _normalize_deterministic_check(value: Any) -> str | None:
        """
        Normalize LLM outputs such as:
        false -> "FAIL"
        true  -> "PASS"
        null  -> None
        ""    -> None
        """
        if value is None:
            return None

        if isinstance(value, bool):
            return "PASS" if value else "FAIL"

        if isinstance(value, str):
            value = value.strip().upper()

            if not value:
                return None

            if value in {"PASS", "FAIL", "NOT_CHECKED"}:
                return value

            return value

        return str(value)

    @staticmethod
    def _normalize_status(value: Any) -> str:
        if isinstance(value, str):
            value = value.strip().upper()

            if value in {"PASS", "FAIL", "HUMAN_REVIEW"}:
                return value

        return "HUMAN_REVIEW"

    @staticmethod
    def _normalize_severity(value: Any, fallback: str) -> str:
        allowed = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

        if isinstance(value, str):
            value = value.strip().upper()

            if value in allowed:
                return value

        return fallback

    @staticmethod
    def _normalize_confidence(value: Any) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.0

        return max(0.0, min(1.0, confidence))

    @staticmethod
    def _find_matching_evidence(
        item: Any,
        candidates: list[Evidence],
    ) -> Evidence | None:
        """
        Convert LLM evidence output into a real Evidence object.

        The LLM is NOT allowed to create new evidence.
        It must point back to evidence supplied by retrieval.
        """

        # Already a dictionary containing evidence metadata
        if isinstance(item, dict):
            try:
                candidate = Evidence.model_validate(item)

                # Verify it actually corresponds to retrieved evidence.
                for existing in candidates:
                    if (
                        candidate.document_id == existing.document_id
                        and candidate.chunk_id == existing.chunk_id
                    ):
                        return existing

                # Do not accept fabricated evidence.
                return None

            except Exception:
                return None

        # LLM sometimes returns only the evidence text.
        if isinstance(item, str):
            text = item.strip()

            if not text:
                return None

            # Prefer exact match.
            for candidate in candidates:
                if text == candidate.text.strip():
                    return candidate

            # Then allow the model to quote a portion of retrieved evidence.
            for candidate in candidates:
                if text in candidate.text or candidate.text in text:
                    return candidate

        return None

    def _normalize_evidence(
        self,
        value: Any,
        candidates: list[Evidence],
    ) -> list[Evidence]:

        raw_items = self._as_list(value)

        normalized = []
        seen = set()

        for item in raw_items:
            evidence = self._find_matching_evidence(item, candidates)

            if evidence is None:
                continue

            key = (evidence.document_id, evidence.chunk_id)

            if key not in seen:
                normalized.append(evidence)
                seen.add(key)

        return normalized

    def _normalize_result(
        self,
        raw_result: dict[str, Any],
        policy_rule,
        evidence_candidates: list[Evidence],
    ) -> ComplianceResult:

        if not isinstance(raw_result, dict):
            raw_result = {}

        rule_id = raw_result.get("rule_id") or policy_rule.rule_id

        status = self._normalize_status(
            raw_result.get("status")
        )

        severity = self._normalize_severity(
            raw_result.get("severity"),
            policy_rule.severity,
        )

        rationale = raw_result.get("rationale")

        if not isinstance(rationale, str) or not rationale.strip():
            rationale = (
                "No valid rationale was returned by the compliance model. "
                "Human review is required."
            )

        evidence = self._normalize_evidence(
            raw_result.get("evidence"),
            evidence_candidates,
        )

        missing_information = [
            str(x)
            for x in self._as_list(
                raw_result.get("missing_information")
            )
            if x is not None and str(x).strip()
        ]

        ambiguity = [
            str(x)
            for x in self._as_list(
                raw_result.get("ambiguity")
            )
            if x is not None and str(x).strip()
        ]

        confidence = self._normalize_confidence(
            raw_result.get("confidence", 0.0)
        )

        deterministic_check = self._normalize_deterministic_check(
            raw_result.get("deterministic_check")
        )

        page = raw_result.get("page")
        if not isinstance(page, int):
            page = None

        section = raw_result.get("section")
        if not isinstance(section, str):
            section = None

        return ComplianceResult(
            rule_id=rule_id,
            status=status,
            severity=severity,
            rationale=rationale,
            evidence=evidence,
            page=page,
            section=section,
            missing_information=missing_information,
            ambiguity=ambiguity,
            confidence=confidence,
            deterministic_check=deterministic_check,
        )

    def run(
        self,
        policy: Policy,
        terms: ExtractedTerms,
        evidence_by_rule: dict[str, list[Evidence]],
        deterministic: dict[str, dict],
    ) -> list[ComplianceResult]:

        payload = {
            "policy": policy.model_dump(),
            "terms": terms.model_dump(),
            "evidence": {
                rule_id: [
                    evidence.model_dump()
                    for evidence in evidence_list
                ]
                for rule_id, evidence_list in evidence_by_rule.items()
            },
            "deterministic": deterministic,
        }

        raw = self.llm.generate_json(
            SYSTEM,
            json.dumps(payload, ensure_ascii=False),
        )

        raw_results = raw.get("results", [])

        if not isinstance(raw_results, list):
            raw_results = []

        by_rule: dict[str, ComplianceResult] = {}

        for raw_result in raw_results:

            if not isinstance(raw_result, dict):
                continue

            rule_id = raw_result.get("rule_id")

            if not rule_id:
                continue

            policy_rule = next(
                (
                    rule
                    for rule in policy.rules
                    if rule.rule_id == rule_id
                ),
                None,
            )

            if policy_rule is None:
                # Ignore hallucinated rule IDs.
                continue

            candidates = evidence_by_rule.get(
                rule_id,
                [],
            )

            try:
                normalized = self._normalize_result(
                    raw_result,
                    policy_rule,
                    candidates,
                )

                # Final Pydantic validation.
                validated = ComplianceResult.model_validate(
                    normalized.model_dump()
                )

                by_rule[rule_id] = validated

            except Exception:
                # Never allow one malformed LLM row to destroy
                # the entire compliance review.
                by_rule[rule_id] = ComplianceResult(
                    rule_id=rule_id,
                    status="HUMAN_REVIEW",
                    severity=policy_rule.severity,
                    rationale=(
                        "The compliance model returned an output that "
                        "could not be safely normalized. Human review "
                        "is required."
                    ),
                    evidence=[],
                    missing_information=policy_rule.required_evidence,
                    ambiguity=[],
                    confidence=0.0,
                    deterministic_check=None,
                )

        # Ensure every policy rule has a result.
        out: list[ComplianceResult] = []

        for rule in policy.rules:

            if rule.rule_id in by_rule:
                out.append(by_rule[rule.rule_id])
                continue

            out.append(
                ComplianceResult(
                    rule_id=rule.rule_id,
                    status="HUMAN_REVIEW",
                    severity=rule.severity,
                    rationale=(
                        "No validated review result was returned "
                        "for this rule."
                    ),
                    evidence=[],
                    missing_information=rule.required_evidence,
                    ambiguity=[],
                    confidence=0.0,
                    deterministic_check=None,
                )
            )

        return out