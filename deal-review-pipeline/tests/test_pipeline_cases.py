from pathlib import Path
from app.ingestion.ingest import ingest_pdf
from app.models.schemas import ExtractedTerms, Term
from app.compliance.deterministic import run_deterministic_checks
from app.risk.scoring import score_risk

NORMAL='data/sample/normal_deal.pdf'
EDGE='data/sample/edge_case_deal.pdf'

def test_normal_document_is_actually_ingested():
    did,pages,chunks=ingest_pdf(NORMAL)
    assert len(pages)==6
    assert len(chunks)>0
    assert all(c.document_id==did for c in chunks)
    assert any('Total Sale Consideration' in p['text'] for p in pages)

def test_edge_document_preserves_page_structure_and_uncertainty():
    did,pages,chunks=ingest_pdf(EDGE)
    assert len(pages)==5
    assert len(chunks)>0
    # The edge PDF has visibly blank/garbled fields in the party section; the ingestion
    # layer must preserve page text rather than fabricate values.
    assert pages[0]['page']==1
    assert any('SYNTHETIC EDGE CASE' in p['text'] for p in pages)

def test_missing_term_is_not_fabricated():
    terms=ExtractedTerms(terms=[Term(field='rera_registration_number',value='MISSING',confidence=0.99,status='MISSING')])
    checks=run_deterministic_checks(terms)
    assert not any('rera_registration_number' in str(v) for v in checks.values())

def test_conflict_contributes_to_deterministic_risk():
    terms=ExtractedTerms(terms=[Term(field='consideration',value='INR 1,00,000',confidence=.5,status='CONFLICT')])
    rs=score_risk([],terms, type('S',(),{})(), ['unresolved contradiction'])
    assert rs.risk_score>0
    assert any('Conflicting' in f.factor for f in rs.factors)
