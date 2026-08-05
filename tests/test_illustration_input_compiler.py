from datetime import date

from suiteview.illustration.core.input_compiler import compile_month_inputs
from suiteview.illustration.models.input_set import (
    DatedTransaction,
    IllustrationInputSet,
    ScheduledTransaction,
    TransactionKind,
)
from suiteview.illustration.models.policy_data import IllustrationPolicyData


def _policy() -> IllustrationPolicyData:
    return IllustrationPolicyData(
        issue_date=date(1985, 2, 2),
        valuation_date=date(2026, 8, 2),
        duration=499,
    )


def test_current_year_modal_premium_compiles_as_scheduled_with_its_mode():
    inputs = IllustrationInputSet(
        scheduled_transactions=[
            ScheduledTransaction(
                kind=TransactionKind.PREMIUM,
                policy_year=42,
                amount=0.0,
                mode="A",
            ),
        ],
        dated_transactions=[
            DatedTransaction(
                kind=TransactionKind.PREMIUM,
                effective_date=date(2026, 9, 2),
                amount=1_200.0,
                metadata={"scheduled_current_year": True, "mode": "M"},
            ),
        ],
    )

    month = compile_month_inputs(_policy(), inputs, 1)[500]

    assert month.scheduled_premium == 1_200.0
    assert month.unscheduled_premium == 0.0
    assert month.premium_mode == "M"


def test_manual_lumpsum_remains_unscheduled_beside_current_year_payment():
    inputs = IllustrationInputSet(dated_transactions=[
        DatedTransaction(
            kind=TransactionKind.PREMIUM,
            effective_date=date(2026, 9, 2),
            amount=1_200.0,
            metadata={"scheduled_current_year": True, "mode": "M"},
        ),
        DatedTransaction(
            kind=TransactionKind.PREMIUM,
            effective_date=date(2026, 9, 2),
            amount=5_000.0,
            subtype="manual_lumpsum",
        ),
    ])

    month = compile_month_inputs(_policy(), inputs, 1)[500]

    assert month.scheduled_premium == 1_200.0
    assert month.unscheduled_premium == 5_000.0
    assert month.total_premium == 6_200.0


def test_current_year_billable_to_md_payment_uses_scheduled_bucket():
    inputs = IllustrationInputSet(dated_transactions=[
        DatedTransaction(
            kind=TransactionKind.PREMIUM,
            effective_date=date(2026, 9, 2),
            amount=174.12,
            metadata={
                "billable_to_md": True,
                "scheduled_current_year": True,
                "mode": "M",
            },
        ),
    ])

    month = compile_month_inputs(_policy(), inputs, 1)[500]

    assert month.scheduled_premium == 174.12
    assert month.unscheduled_premium == 0.0
    assert month.billable_to_md_premium == 0.0
