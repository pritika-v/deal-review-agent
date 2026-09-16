from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
from app.models.schemas import DealReport

class ReportGenerator:
    def __init__(self,out_dir='data/reports'):
        self.out=Path(out_dir); self.out.mkdir(parents=True,exist_ok=True)
        self.env=Environment(loader=FileSystemLoader('app/reports/templates'))
    def generate(self, report: DealReport):
        stem=report.document_id
        jp=self.out/f'{stem}_report.json'; pp=self.out/f'{stem}_report.pdf'
        jp.write_text(json.dumps(report.model_dump(),indent=2,ensure_ascii=False,default=str),encoding='utf-8')
        html=self.env.get_template('report.html').render(report=report.model_dump())
        HTML(string=html,base_url=str(Path.cwd())).write_pdf(str(pp))
        return str(jp),str(pp)
