from __future__ import annotations
import re
from decimal import Decimal

def _money(s):
    if not s: return []
    vals=[]
    for m in re.findall(r'(?:INR|Rs\.?|₹)\s*([\d,]+)', str(s), flags=re.I):
        vals.append(Decimal(m.replace(',','')))
    return vals

def run_deterministic_checks(terms):
    by={t.field.lower():t for t in terms.terms}
    checks={}
    # Payment schedule total-vs-components check: only flag when explicit values permit arithmetic.
    schedule=[]
    for t in terms.terms:
        if 'payment' in t.field.lower() and t.status=='FOUND': schedule.extend(_money(str(t.value)))
    consideration=[]
    for t in terms.terms:
        if any(x in t.field.lower() for x in ['consideration','sale price','total sale']): consideration.extend(_money(str(t.value)))
    if schedule and consideration:
        total=max(consideration)
        # Do not compare arbitrary duplicated TDS entries; require schedule sum to be within 2% or explicit TDS logic.
        sched=sum(schedule)
        checks['PAYMENT_ARITHMETIC']={'status':'PASS' if abs(sched-total)<=total*Decimal('0.02') else 'FAIL',
            'message':f'Payment values sum to {sched}; stated consideration candidate is {total}.'}
    # Jurisdiction mismatch is a review trigger, not a legal conclusion.
    loc=next((str(t.value) for t in terms.terms if 'location' in t.field.lower() and t.status=='FOUND'), '')
    if loc and 'tamil nadu' not in loc.lower() and any(x in loc.lower() for x in ['gurugram','gurgaon','haryana','delhi']):
        checks['JURISDICTION_MISMATCH']={'status':'HUMAN_REVIEW','message':f'Document location appears to be {loc}; supplied policy jurisdiction is Tamil Nadu.'}
    return checks
