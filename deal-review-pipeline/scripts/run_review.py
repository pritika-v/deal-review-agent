from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
import argparse, json
from app.graph.workflow import run_review
p=argparse.ArgumentParser(); p.add_argument('--deal',required=True); p.add_argument('--policy',required=True); a=p.parse_args()
r=run_review(a.deal,a.policy)
print(json.dumps({'document_id':r.get('document_id'),'status':r.get('status'),'risk_score':r.get('risk_score'),'json_report':r.get('report_json_path'),'pdf_report':r.get('report_pdf_path'),'human_review_reasons':r.get('human_review_reasons')},indent=2,default=str))

