from __future__ import annotations

import json
from typing import Any

from app.llm.openrouter import OpenRouterClient
from app.models.schemas import RiskSummary, RiskItem, Evidence


SYSTEM = """
You are the Risk & Summary Agent.

Use ONLY the supplied structured compliance findings, extracted terms,
and retrieved evidence.

Identify:
- financial risks
- legal/contractual risks
- compliance risks
- operational risks
- documentation risks

Prioritize risks by severity, but DO NOT assign a numerical overall risk score.

Return ONLY valid JSON in this structure:

{
  "risks": [
    {
      "risk_id": "RISK-001",
      "category": "COMPLIANCE",
      "severity": "LOW",
      "title": "Short risk title",
      "description": "Clear explanation",
      "evidence": [],
      "source_rule_ids": [],
      "action": "Recommended follow-up action"
    }
  ],
  "executive_summary": "Short executive summary",
  "follow_up_actions": []
}

IMPORTANT:

1. severity MUST be one of:
   LOW, MEDIUM, HIGH, CRITICAL.

2. evidence MUST ALWAYS be a JSON list.

3. Every evidence item MUST correspond to evidence supplied
   in the input. Never manufacture evidence.

4. Do not create fake document IDs, chunk IDs, page numbers,
   clauses, or quotations.

5. If no evidence supports a risk, return:
   "evidence": []

6. source_rule_ids MUST be a JSON list.

7. follow_up_actions MUST be a JSON list of strings.

8. If there are no risks, return:
   "risks": []

9. Do not calculate or assign the overall numerical risk score.
"""


class RiskSummaryAgent:

    def __init__(self, llm=None):
        self.llm = llm or OpenRouterClient()

    @staticmethod
    def _as_list(value: Any) -> list:
        """
        Normalize:
        None       -> []
        ""         -> []
        "abc"      -> ["abc"]
        ["a","b"]  -> ["a","b"]
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
    def _normalize_severity(value: Any) -> str:
        allowed = {
            "LOW",
            "MEDIUM",
            "HIGH",
            "CRITICAL",
        }

        if isinstance(value, str):
            value = value.strip().upper()

            if value in allowed:
                return value

        return "MEDIUM"

    @staticmethod
    def _normalize_evidence(
        value: Any,
        supplied_evidence: list[Evidence],
    ) -> list[Evidence]:

        raw_items = RiskSummaryAgent._as_list(value)

        normalized = []
        seen = set()

        for item in raw_items:

            matched = None

            # Case 1: LLM returned an evidence object
            if isinstance(item, dict):

                try:
                    candidate = Evidence.model_validate(item)

                    for existing in supplied_evidence:

                        if (
                            candidate.document_id
                            == existing.document_id
                            and candidate.chunk_id
                            == existing.chunk_id
                        ):
                            matched = existing
                            break

                except Exception:
                    matched = None

            # Case 2: LLM returned evidence text
            elif isinstance(item, str):

                text = item.strip()

                if text:

                    for existing in supplied_evidence:

                        if text == existing.text.strip():
                            matched = existing
                            break

                    if matched is None:

                        for existing in supplied_evidence:

                            if (
                                text in existing.text
                                or existing.text in text
                            ):
                                matched = existing
                                break

            if matched is None:
                continue

            key = (
                matched.document_id,
                matched.chunk_id,
            )

            if key not in seen:
                normalized.append(matched)
                seen.add(key)

        return normalized

    def _collect_supplied_evidence(
        self,
        payload: dict,
    ) -> list[Evidence]:

        """
        Extract all evidence supplied to the Risk Agent.

        This lets us verify that the LLM does not invent evidence.
        """

        evidence = []

        def walk(value):

            if isinstance(value, Evidence):
                evidence.append(value)
                return

            if isinstance(value, dict):

                # Direct evidence object
                if {
                    "document_id",
                    "chunk_id",
                    "text",
                    "page",
                }.issubset(value.keys()):

                    try:
                        evidence.append(
                            Evidence.model_validate(value)
                        )
                        return
                    except Exception:
                        pass

                for child in value.values():
                    walk(child)

            elif isinstance(value, list):

                for child in value:
                    walk(child)

        walk(payload)

        # Remove duplicates
        unique = []
        seen = set()

        for item in evidence:

            key = (
                item.document_id,
                item.chunk_id,
            )

            if key not in seen:
                unique.append(item)
                seen.add(key)

        return unique

    def _normalize_risk(
        self,
        raw_risk: Any,
        supplied_evidence: list[Evidence],
        index: int,
    ) -> RiskItem:

        if not isinstance(raw_risk, dict):
            raw_risk = {}

        risk_id = raw_risk.get("risk_id")

        if not isinstance(risk_id, str) or not risk_id.strip():
            risk_id = f"RISK-{index:03d}"

        category = raw_risk.get("category")

        if not isinstance(category, str) or not category.strip():
            category = "DOCUMENTATION"

        severity = self._normalize_severity(
            raw_risk.get("severity")
        )

        title = raw_risk.get("title")

        if not isinstance(title, str) or not title.strip():
            title = "Unspecified risk requiring review"

        description = raw_risk.get("description")

        if not isinstance(description, str) or not description.strip():
            description = (
                "The risk requires further review based on the "
                "available deal information."
            )

        evidence = self._normalize_evidence(
            raw_risk.get("evidence"),
            supplied_evidence,
        )

        source_rule_ids = [
            str(x)
            for x in self._as_list(
                raw_risk.get("source_rule_ids")
            )
            if x is not None and str(x).strip()
        ]

        action = raw_risk.get("action")

        if not isinstance(action, str) or not action.strip():
            action = "Review the finding and obtain supporting documentation."

        return RiskItem(
            risk_id=risk_id,
            category=category,
            severity=severity,
            title=title,
            description=description,
            evidence=evidence,
            source_rule_ids=source_rule_ids,
            action=action,
        )

    def run(self, payload) -> RiskSummary:

        raw = self.llm.generate_json(
            SYSTEM,
            json.dumps(
                payload,
                ensure_ascii=False,
            ),
        )

        if not isinstance(raw, dict):
            raw = {}

        supplied_evidence = self._collect_supplied_evidence(
            payload
        )

        raw_risks = raw.get("risks", [])

        if not isinstance(raw_risks, list):
            raw_risks = []

        risks = []

        for index, raw_risk in enumerate(
            raw_risks,
            start=1,
        ):

            try:

                normalized = self._normalize_risk(
                    raw_risk,
                    supplied_evidence,
                    index,
                )

                validated = RiskItem.model_validate(
                    normalized.model_dump()
                )

                risks.append(validated)

            except Exception:
                # Never allow one malformed risk to destroy
                # the complete report.

                risks.append(
                    RiskItem(
                        risk_id=f"RISK-{index:03d}",
                        category="DOCUMENTATION",
                        severity="MEDIUM",
                        title="Risk requires human review",
                        description=(
                            "The risk model returned an output "
                            "that could not be safely normalized."
                        ),
                        evidence=[],
                        source_rule_ids=[],
                        action=(
                            "Review the underlying compliance "
                            "findings manually."
                        ),
                    )
                )

        executive_summary = raw.get(
            "executive_summary",
            "",
        )

        if not isinstance(executive_summary, str):
            executive_summary = str(executive_summary)

        if not executive_summary.strip():
            executive_summary = (
                "Risk summary generation did not provide a "
                "validated executive summary. Human review is required."
            )

        follow_up_actions = [
            str(x)
            for x in self._as_list(
                raw.get("follow_up_actions")
            )
            if x is not None and str(x).strip()
        ]

        result = RiskSummary(
            risks=risks,
            executive_summary=executive_summary,
            follow_up_actions=follow_up_actions,
        )

        # Final Pydantic validation
        return RiskSummary.model_validate(
            result.model_dump()
        )