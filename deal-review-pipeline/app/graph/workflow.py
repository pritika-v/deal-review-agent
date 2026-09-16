from __future__ import annotations
import os, json, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from langgraph.graph import StateGraph, END
from app.models.state import ReviewState
from app.models.schemas import DealReport, RiskSummary, RiskScore
from app.policy.loader import load_policy, normalize_policy_text, PolicyValidationError
from app.ingestion.ingest import ingest_pdf
from app.retrieval.hybrid import HybridRetriever
from app.agents.term_extraction import TermExtractionAgent
from app.agents.compliance import ComplianceAgent
from app.agents.risk_summary import RiskSummaryAgent
from app.compliance.deterministic import run_deterministic_checks
from app.risk.scoring import score_risk
from app.reports.generator import ReportGenerator
from app.storage.sqlite import SQLiteStore
from app.llm.openrouter import OpenRouterClient
import fitz


RETRIEVERS={}

def now(): return datetime.now(timezone.utc).isoformat()
def log_event(state,node,**extra):
    state.setdefault('audit',[]).append({'node':node,'timestamp':now(),**extra})

def error(state,node,exc):
    state.setdefault('errors',[]).append({'node':node,'timestamp':now(),'error':str(exc)})
    state.setdefault('failure_reasons',{})[node]=str(exc)
    state.setdefault('retry_counts',{})[node]=state.get('retry_counts',{}).get(node,0)+1

def _max_retries(): return int(os.getenv('MAX_RETRIES','2'))

def policy_node(state):
    try:
        p=load_policy(state['policy_path'])
        state['policy']=p; log_event(state,'policy_validation',policy_id=p.policy_id,version=p.version); return state
    except PolicyValidationError as exc:
        # PDF/DOCX policy normalization is an LLM-assisted conversion step, then schema validation.
        try:
            suffix=Path(state['policy_path']).suffix.lower()
            if suffix=='.pdf':
                doc=fitz.open(state['policy_path']); text='\n'.join(x.get_text() for x in doc)
            elif suffix == '.docx':
                raise PolicyValidationError(
                    "DOCX policy files are not supported. "
                    "Please upload the policy as JSON or PDF."
                )
            else:
                text=Path(state['policy_path']).read_text(encoding='utf-8')
        except Exception:
            text=''
        if text:
            try:
                raw=OpenRouterClient().generate_json('''Normalize the supplied compliance policy into JSON with document_title, document_type, jurisdiction, policy_id, version, and rules[]. Each rule must contain rule_id, category, name, rule, severity, required_evidence, and optional check_type, parameters, evidence_requirements. Preserve wording; do not invent rules.''', text)
                from app.models.schemas import Policy
                state['policy']=Policy.model_validate(raw); log_event(state,'policy_normalization'); return state
            except Exception as norm_exc:
                error(state,'policy_validation',norm_exc); return state
        error(state,'policy_validation',exc); return state

def ingestion_node(state):
    try:
        did,pages,chunks=ingest_pdf(state['deal_path'],state.get('document_id'))
        state['document_id']=did; state['pages']=pages; state['chunks']=[c.model_dump() for c in chunks]
        log_event(state,'document_ingestion',pages=len(pages),chunks=len(chunks)); return state
    except Exception as exc: error(state,'document_ingestion',exc); return state

def extraction_node(state):
    try:
        from app.models.schemas import DocumentChunk
        terms=TermExtractionAgent().run(state['pages'])
        state['terms']=terms.model_dump(); log_event(state,'term_extraction',term_count=len(terms.terms)); return state
    except Exception as exc: error(state,'term_extraction',exc); return state

def evidence_node(state):
    try:
        from app.models.schemas import DocumentChunk, ExtractedTerms
        chunks=[DocumentChunk.model_validate(x) for x in state['chunks']]
        retr=HybridRetriever(chunks,collection_name=f'deal_{state["document_id"]}')
        RETRIEVERS[state['document_id']]=retr
        terms=ExtractedTerms.model_validate(state['terms'])
        evidence=[]; by_rule={}
        for rule in state['policy'].rules:
            q=f'{rule.name}. {rule.rule}. Required evidence: {", ".join(rule.required_evidence)}'
            ev=retr.retrieve(q,top_k=3); by_rule[rule.rule_id]=ev; evidence.extend(ev)
        for term in terms.terms:
            if term.status=='FOUND': evidence.extend(retr.retrieve(f'{term.field}: {term.value}',top_k=1))
        uniq={e.chunk_id:e for e in evidence}; state['evidence']=[e.model_dump() for e in uniq.values()]
        state['_evidence_by_rule']={k:[e.model_dump() for e in v] for k,v in by_rule.items()}
        if not evidence: raise RuntimeError('EVIDENCE_NOT_FOUND')
        log_event(state,'evidence_retrieval',evidence_count=len(uniq)); return state
    except Exception as exc: error(state,'evidence_retrieval',exc); state.setdefault('evidence',[]); return state

def compliance_node(state):
    try:
        from app.models.schemas import ExtractedTerms, Evidence
        terms=ExtractedTerms.model_validate(state.get('terms',{'terms':[]}))
        by_rule={k:[Evidence.model_validate(x) for x in v] for k,v in state.get('_evidence_by_rule',{}).items()}
        det=run_deterministic_checks(terms)
        results=ComplianceAgent().run(state['policy'],terms,by_rule,det)
        # Deterministic arithmetic failures must not be overwritten by an optimistic LLM answer.
        if det.get('PAYMENT_ARITHMETIC',{}).get('status')=='FAIL':
            for r in results:
                if r.rule_id=='R14':
                    r.status='FAIL'; r.deterministic_check=det['PAYMENT_ARITHMETIC']['message']; r.confidence=max(r.confidence,.95)
        if det.get('JURISDICTION_MISMATCH'):
            state.setdefault('human_review_reasons',[]).append(det['JURISDICTION_MISMATCH']['message'])
        state['compliance']=[r.model_dump() for r in results]; log_event(state,'compliance_review',rule_count=len(results)); return state
    except Exception as exc: error(state,'compliance_review',exc); return state

def human_node(state):
    state.setdefault('human_review_reasons',[])
    for node,msg in state.get('failure_reasons',{}).items():
        if state.get('retry_counts',{}).get(node,0)>=_max_retries(): state['human_review_reasons'].append(f'{node}: {msg}')
    if not state.get('terms'): state['human_review_reasons'].append('Term extraction did not produce validated terms.')
    # If the risk-summary LLM itself exhausted retries, do not loop forever.
    if state.get('retry_counts',{}).get('risk_summary',0)>=_max_retries() and not state.get('risk_summary'):
        state['risk_summary']={'risks':[],'executive_summary':'Risk summary generation failed; human review is required.','follow_up_actions':['Review workflow errors and source evidence manually.']}
    log_event(state,'human_review',reasons=state['human_review_reasons']); return state

def risk_node(state):
    try:
        from app.models.schemas import ExtractedTerms, Evidence, ComplianceResult
        terms=ExtractedTerms.model_validate(state.get('terms',{'terms':[]}))
        comp=[ComplianceResult.model_validate(x) for x in state.get('compliance',[])]
        payload={'terms':terms.model_dump(),'evidence':state.get('evidence',[]),'compliance':state.get('compliance',[]),'missing_information':list({x for r in comp for x in r.missing_information}),'ambiguities':list({x for r in comp for x in r.ambiguity})}
        summary=RiskSummaryAgent().run(payload); state['risk_summary']=summary.model_dump(); log_event(state,'risk_summary',risk_count=len(summary.risks)); return state
    except Exception as exc: error(state,'risk_summary',exc); return state

def scoring_node(state):
    from app.models.schemas import ExtractedTerms, ComplianceResult, RiskSummary
    score=score_risk([ComplianceResult.model_validate(x) for x in state.get('compliance',[])],ExtractedTerms.model_validate(state.get('terms',{'terms':[]})),RiskSummary.model_validate(state.get('risk_summary',{'risks':[],'executive_summary':'Risk summary unavailable due to workflow failure.','follow_up_actions':[]})),state.get('human_review_reasons',[]))
    state['risk_score']=score.model_dump(); log_event(state,'deterministic_risk_engine',score=score.risk_score,level=score.risk_level); return state

def report_node(state):
    from app.models.schemas import DealReport, Term, Evidence, ComplianceResult, RiskItem, RiskScore
    terms=[Term.model_validate(x) for x in state.get('terms',{}).get('terms',[])]
    comp=[ComplianceResult.model_validate(x) for x in state.get('compliance',[])]
    risks=[RiskItem.model_validate(x) for x in state.get('risk_summary',{}).get('risks',[])]
    rs=RiskScore.model_validate(state['risk_score'])
    missing=sorted({x for t in terms if t.status=='MISSING' for x in [t.field]} | {x for r in comp for x in r.missing_information})
    ambiguities=sorted({x for t in terms if t.status in {'AMBIGUOUS','CONFLICT'} for x in [f'{t.field}: {t.status}']+([t.supporting_source_text] if t.supporting_source_text else [])} | {x for r in comp for x in r.ambiguity})
    high=[r.title+': '+r.description for r in risks if r.severity in {'HIGH','CRITICAL'}]
    overview={t.field:t.value for t in terms if t.status=='FOUND'}
    summary=state.get('risk_summary',{}).get('executive_summary','Risk summary unavailable.')
    report=DealReport(document_id=state['document_id'],policy_id=state['policy'].policy_id,policy_version=state['policy'].version,generated_at=now(),executive_summary=summary,deal_overview=overview,extracted_terms=terms,evidence=[Evidence.model_validate(x) for x in state.get('evidence',[])],compliance_matrix=comp,risk_register=risks,missing_information=missing,ambiguities=ambiguities,high_risk_findings=high,follow_up_actions=state.get('risk_summary',{}).get('follow_up_actions',[]),risk_score=rs,human_review_reasons=sorted(set(state.get('human_review_reasons',[]))),audit_metadata={'events':state.get('audit',[]),'errors':state.get('errors',[]),'retry_counts':state.get('retry_counts',{}),'failure_reasons':state.get('failure_reasons',{})})
    jp,pp=ReportGenerator().generate(report); state['report_json_path']=jp; state['report_pdf_path']=pp; state['completed_at']=now(); state['status']=rs.status
    SQLiteStore().upsert(state['document_id'],status=state['status'],started_at=state.get('started_at'),completed_at=state['completed_at'],risk_score=rs.risk_score,policy_id=report.policy_id,policy_version=report.policy_version,report_json=jp,report_pdf=pp)
    log_event(state,'report_generation',json=jp,pdf=pp); return state

def route(state,node):
    if state.get('failure_reasons',{}).get(node):
        if state.get('retry_counts',{}).get(node,0) < _max_retries(): return node
        return 'human_review'
    return {'policy_validation':'document_ingestion','document_ingestion':'term_extraction','term_extraction':'evidence_retrieval','evidence_retrieval':'compliance_review','compliance_review':'risk_summary','risk_summary':'deterministic_risk_engine'}.get(node,'deterministic_risk_engine')

def build_graph():
    g=StateGraph(ReviewState)
    nodes={'policy_validation':policy_node,'document_ingestion':ingestion_node,'term_extraction':extraction_node,'evidence_retrieval':evidence_node,'compliance_review':compliance_node,'human_review':human_node,'risk_summary':risk_node,'deterministic_risk_engine':scoring_node,'final_report':report_node}
    for n,f in nodes.items(): g.add_node(n,f)
    g.set_entry_point('policy_validation')
    for n in ['policy_validation','document_ingestion','term_extraction','evidence_retrieval','compliance_review','risk_summary']:
        g.add_conditional_edges(n, lambda s,n=n: route(s,n))
    def human_route(s):
        if s.get('risk_summary'):
            return 'deterministic_risk_engine'
        return 'risk_summary'
    g.add_conditional_edges('human_review', human_route)
    g.add_edge('deterministic_risk_engine','final_report'); g.add_edge('final_report',END)
    return g.compile()

def run_review(deal_path,policy_path):
    state:ReviewState={'deal_path':deal_path,'policy_path':policy_path,'retry_counts':{},'errors':[],'failure_reasons':{},'human_review_reasons':[],'audit':[],'started_at':now()}
    return build_graph().invoke(state)
