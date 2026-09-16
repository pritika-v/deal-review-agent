from __future__ import annotations
from pathlib import Path
import yaml
from app.models.schemas import RiskScore, RiskFactor

def load_config(path='config.yaml'):
    return yaml.safe_load(Path(path).read_text())

def score_risk(compliance, terms, risk_summary, human_review_reasons, config=None):
    cfg=(config or load_config())['risk']; w=cfg['weights']; factors=[]
    counts={'critical_fail':0,'high_fail':0,'medium_fail':0,'critical_missing_evidence':0,'high_missing_evidence':0}
    for r in compliance:
        if r.status=='FAIL': counts[f'{r.severity.lower()}_fail']+=1
        if r.missing_information:
            if r.severity=='CRITICAL': counts['critical_missing_evidence']+=1
            elif r.severity=='HIGH': counts['high_missing_evidence']+=1
    for key,label in [('critical_fail','Critical compliance failure'),('high_fail','High-severity compliance failure'),('medium_fail','Medium-severity compliance failure'),('critical_missing_evidence','Critical evidence missing'),('high_missing_evidence','High-severity evidence missing')]:
        if counts[key]: factors.append(RiskFactor(factor=label,points=counts[key]*w[key],reason=f'{counts[key]} finding(s)'))
    amb=sum(len(r.ambiguity) for r in compliance)+sum(1 for t in terms.terms if t.status=='AMBIGUOUS')
    unc=sum(1 for t in terms.terms if t.confidence < .6 or t.status in {'MISSING','CONFLICT'})
    conflicts=sum(1 for t in terms.terms if t.status=='CONFLICT')
    if amb: factors.append(RiskFactor(factor='Material ambiguity',points=amb*w['material_ambiguity'],reason=f'{amb} ambiguity finding(s)'))
    if unc: factors.append(RiskFactor(factor='Material uncertainty',points=unc*w['material_uncertainty'],reason=f'{unc} low-confidence/missing/conflict term(s)'))
    if conflicts: factors.append(RiskFactor(factor='Conflicting document information',points=conflicts*w['conflicting_information'],reason=f'{conflicts} conflict term(s)'))
    financial_inconsistency=sum(1 for r in compliance if r.deterministic_check and 'FAIL' in r.deterministic_check.upper())
    if financial_inconsistency: factors.append(RiskFactor(factor='Financial inconsistency',points=financial_inconsistency*w['financial_inconsistency'],reason=f'{financial_inconsistency} deterministic inconsistency flag(s)'))
    if human_review_reasons: factors.append(RiskFactor(factor='Human review escalation',points=w['human_review'],reason=f'{len(human_review_reasons)} escalation reason(s)'))
    raw=sum(f.points for f in factors); score=min(int(cfg['max_score']),raw)
    bands=cfg['bands']; level='LOW' if score<=bands['LOW'] else 'MEDIUM' if score<=bands['MEDIUM'] else 'HIGH' if score<=bands['HIGH'] else 'CRITICAL'
    status='HUMAN_REVIEW' if human_review_reasons or any(r.status=='HUMAN_REVIEW' for r in compliance) else 'FAIL' if any(r.status=='FAIL' for r in compliance) else 'PASS'
    return RiskScore(risk_score=score,risk_level=level,factors=factors,status=status)
