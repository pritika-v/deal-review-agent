from __future__ import annotations

import re
from decimal import Decimal


def _money(s):
    if not s:
        return []

    vals = []

    for m in re.findall(
        r'(?:INR|Rs\.?|₹)\s*([\d,]+)',
        str(s),
        flags=re.I
    ):
        vals.append(Decimal(m.replace(',', '')))

    return vals


def run_deterministic_checks(terms):
    checks = {}

    # ---------------------------------------------------------
    # PAYMENT ARITHMETIC CHECK
    # ---------------------------------------------------------
    # Only perform arithmetic when explicit monetary values
    # are available from the extracted payment terms.
    schedule = []

    for t in terms.terms:
        if 'payment' in t.field.lower() and t.status == 'FOUND':
            schedule.extend(_money(str(t.value)))

    consideration = []

    for t in terms.terms:
        if any(
            x in t.field.lower()
            for x in ['consideration', 'sale price', 'total sale']
        ):
            consideration.extend(_money(str(t.value)))

    if schedule and consideration:
        total = max(consideration)
        sched = sum(schedule)

        # Exact reconciliation.
        # TDS is part of the payment flow, so it should not be
        # automatically added on top of the total consideration.
        status = 'PASS' if sched == total else 'FAIL'

        checks['PAYMENT_ARITHMETIC'] = {
            'status': status,
            'message': (
                f'Payment values sum to {sched}; '
                f'stated consideration candidate is {total}.'
            )
        }

    return checks