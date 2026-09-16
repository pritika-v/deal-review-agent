from __future__ import annotations

import re
from decimal import Decimal


def _money(s):
    """
    Extract monetary values from text.

    Supports formats such as:
    - INR 5,00,000
    - INR 1,85,00,000/-
    - Rs. 5,00,000
    - Rs 5,00,000
    - ₹5,00,000
    """

    if not s:
        return []

    vals = []

    pattern = r"(?:INR|Rs\.?|₹)\s*([\d,]+(?:\.\d+)?)"

    for m in re.findall(pattern, str(s), flags=re.IGNORECASE):
        try:
            vals.append(Decimal(m.replace(",", "")))
        except Exception:
            continue

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
        if (
            "payment" in t.field.lower()
            and t.status == "FOUND"
        ):
            schedule.extend(_money(str(t.value)))

    # ---------------------------------------------------------
    # TOTAL SALE CONSIDERATION
    # ---------------------------------------------------------

    consideration = []

    for t in terms.terms:
        if (
            any(
                x in t.field.lower()
                for x in [
                    "consideration",
                    "sale price",
                    "total sale"
                ]
            )
            and t.status == "FOUND"
        ):
            consideration.extend(_money(str(t.value)))

    # ---------------------------------------------------------
    # RECONCILIATION
    # ---------------------------------------------------------

    if schedule and consideration:
        total = max(consideration)
        sched = sum(schedule, Decimal("0"))

        difference = sched - total

        # Exact reconciliation.
        # TDS is already part of the payment schedule,
        # so it should not be added again separately.

        status = "PASS" if difference == Decimal("0") else "FAIL"

        checks["PAYMENT_ARITHMETIC"] = {
            "status": status,
            "message": (
                f"Payment values sum to {sched}; "
                f"stated consideration is {total}; "
                f"difference is {difference}."
            ),
        }

    return checks