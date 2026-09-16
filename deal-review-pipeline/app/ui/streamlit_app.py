from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from app.graph.workflow import run_review

st.set_page_config(page_title='Deal Review Pipeline',page_icon='📑',layout='wide')
st.title('📑 Multi-Agent Deal Review Pipeline')
st.caption('Evidence-backed synthetic deal review using LangGraph, OCR, hybrid retrieval and deterministic risk scoring.')

with st.sidebar:
    st.header('Inputs')
    deal=st.file_uploader('Deal document',type=['pdf'])
    default_policy='data/policies/TN_RERA_Compliance_Rules.json'
    policy_choice=st.radio('Policy',['Default Compliance policy','Upload another policy'])
    uploaded_policy=st.file_uploader('Alternative policy',type=['json','pdf']) if policy_choice!='Default Compliance policy' else None
    run=st.button('Run Deal Review',type='primary',disabled=deal is None)

if run and deal:
    with tempfile.TemporaryDirectory() as td:
        deal_path=Path(td)/deal.name; deal_path.write_bytes(deal.getvalue())
        if uploaded_policy:
            policy_path=Path(td)/uploaded_policy.name; policy_path.write_bytes(uploaded_policy.getvalue())
        else: policy_path=Path(default_policy)
        with st.status('Running LangGraph workflow...',expanded=True) as status:
            try:
                result=run_review(str(deal_path),str(policy_path))
                status.update(label='Review complete',state='complete')
            except Exception as exc:
                status.update(label='Workflow failed',state='error')
                st.exception(exc); st.stop()
        st.session_state['result']=result

result=st.session_state.get('result')
if result:
    score=result.get('risk_score',{})
    c1,c2,c3=st.columns(3); c1.metric('Risk score',f"{score.get('risk_score','—')}/100"); c2.metric('Risk level',score.get('risk_level','—')); c3.metric('Status',score.get('status','—'))
    st.subheader('Executive Summary'); st.write(result.get('risk_summary',{}).get('executive_summary',''))
    tabs=st.tabs(['Terms','Evidence','Compliance','Risks','Missing / Uncertainty','Audit'])
    with tabs[0]: st.dataframe(result.get('terms',{}).get('terms',[]),use_container_width=True)
    with tabs[1]: st.dataframe(result.get('evidence',[]),use_container_width=True)
    with tabs[2]: st.dataframe(result.get('compliance',[]),use_container_width=True)
    with tabs[3]:
        for r in result.get('risk_summary',{}).get('risks',[]):
            with st.expander(f"{r['severity']} — {r['title']}"): st.write(r['description']); st.write('Action:',r['action'])
        st.json(score.get('factors',[]))
    with tabs[4]:
        st.write('Human-review reasons'); st.write(result.get('human_review_reasons',[]))
        st.write('Workflow errors'); st.json(result.get('errors',[]))
    with tabs[5]: st.json({'events':result.get('audit',[]),'retries':result.get('retry_counts',{}),'failures':result.get('failure_reasons',{})})
    jp=result.get('report_json_path'); pp=result.get('report_pdf_path')
    if jp and Path(jp).exists(): st.download_button('Download JSON report',Path(jp).read_bytes(),file_name=Path(jp).name,mime='application/json')
    if pp and Path(pp).exists(): st.download_button('Download PDF report',Path(pp).read_bytes(),file_name=Path(pp).name,mime='application/pdf')
else:
    st.info('Upload the Document deal PDF, select the supplied policy, and click Run Deal Review.')
