from __future__ import annotations
import json
from app.llm.openrouter import OpenRouterClient
from app.models.schemas import ExtractedTerms

SYSTEM='''You are the Term Extraction Agent in an evidence-backed deal review pipeline. Extract only facts supported by the 
supplied document. Never infer missing values. Every FOUND term must cite a page and source text copied from the input. 
Use MISSING when absent, AMBIGUOUS when wording is unclear, and CONFLICT when the document contains contradictory values. 
Return JSON only matching: {"terms":[{"field":string,"value":any,"confidence":0..1,"page":integer|null,"section":string|null,"clause":string|null,"supporting_source_text":string|null,"status":"FOUND|MISSING|AMBIGUOUS|CONFLICT"}]}'''

class TermExtractionAgent:
    def __init__(self, llm=None): self.llm=llm or OpenRouterClient()
    def run(self, pages) -> ExtractedTerms:
        source='\n'.join(f'PAGE {p["page"]}\n{p["text"]}' for p in pages)
        user=f'''Extract material deal terms from this document. Cover parties/roles, asset, consideration, payment schedule, dates/deadlines, possession, obligations, covenants, collateral/security, termination/refund, conditions, representations, encumbrances, approvals, agent information and other material terms. Do not add facts not present.\n\nDOCUMENT:\n{source}'''
        raw=self.llm.generate_json(SYSTEM,user)
        return ExtractedTerms.model_validate(raw)
