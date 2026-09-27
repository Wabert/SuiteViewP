"""PolicyInformation billing section."""

from __future__ import annotations

from .base import PolicySection
from ..cl_polrec.policy_translations import BILLING_MODE_CODES
from ..cl_polrec.policy_translations import NON_STANDARD_BILL_MODE_CODES
from datetime import date
from decimal import Decimal
from typing import Optional


class BillingSection(PolicySection):
    """Cohesive PolicyInformation billing view."""

    TABLES = frozenset(('ANNUAL_POLICY_FEE', 'BILLING_FREQUENCY', 'BILL_DAY', 'BILL_FORM_CODE', 'FORCED_PREMIUM_INDICATOR', 'INITIAL_MODE', 'INITIAL_PAY_DUR', 'MDO_CODE', 'MODAL_PREMIUM', 'NEXT_BILL_DATE', 'NON_STANDARD_MODE_CODE', 'NON_TRADITIONAL_INDICATOR', 'PREMIUM_PAID_TO_DATE', 'TARGET_PREMIUM', 'TH_USER_GENERIC',))
    CACHE_ATTRS = ()

    @property
    def billing_frequency(self) -> int:
        """Billing frequency in months."""
        return int(self._field("billing_frequency") or 0)

    @property
    def billing_mode(self) -> str:
        """Billing mode description."""
        nsd = self.non_standard_mode_code
        if nsd in NON_STANDARD_BILL_MODE_CODES:
            return NON_STANDARD_BILL_MODE_CODES[nsd]
        return BILLING_MODE_CODES.get(self.billing_frequency, f"{self.billing_frequency} months")

    @property
    def non_standard_mode_code(self) -> str:
        """Non-standard billing mode code (NSD_MD_CD)."""
        return str(self._field("non_standard_mode_code") or "")

    @property
    def bill_day(self) -> int:
        """Billing day of month."""
        return int(self._field("bill_day") or 0)

    @property
    def regular_premium(self) -> Optional[Decimal]:
        """Regular premium amount (alias for modal_premium)."""
        return self.modal_premium

    @property
    def modal_premium(self) -> Optional[Decimal]:
        """Modal premium (premium per billing period)."""
        val = self._field("modal_premium")
        return Decimal(str(val)) if val is not None else None

    @property
    def annual_premium(self) -> Optional[Decimal]:
        """Annualized premium."""
        if self.modal_premium and self.billing_frequency:
            return self.modal_premium * (Decimal(12) / Decimal(self.billing_frequency))
        return self.modal_premium

    @property
    def annual_policy_fee(self) -> Optional[Decimal]:
        """Annual policy fee for traditional products."""
        if str(self._field("non_traditional_indicator") or "").strip() == "1":
            return None
        val = self._field("annual_policy_fee")
        return Decimal(str(val)) if val is not None else None

    @property
    def target_premium(self) -> Optional[Decimal]:
        """Target premium (for UL products)."""
        val = self._field("target_premium")
        return Decimal(str(val)) if val is not None else None

    @property
    def minimum_premium(self) -> Optional[Decimal]:
        """Minimum premium (for UL products — not stored on LH_BAS_POL)."""
        return None

    @property
    def total_regular_premium(self) -> Decimal:
        """Total regular premiums paid lifetime (VBA: TotalRegularPremium)."""
        return self.policy.total_records.TOT_REG_PRM_AMT

    @property
    def total_premiums_paid(self) -> Optional[Decimal]:
        """Total premiums paid lifetime (alias for total_regular_premium for backward compat)."""
        return self.total_regular_premium

    @property
    def total_additional_premium(self) -> Decimal:
        """Total additional premiums paid (VBA: TotalAdditionalPremium)."""
        return self.policy.total_records.TOT_ADD_PRM_AMT

    @property
    def total_additional_premiums(self) -> Optional[Decimal]:
        """Alias for backward compat."""
        return self.total_additional_premium

    @property
    def premium_td(self) -> Decimal:
        """Total premiums to date = regular + additional (VBA: PremiumTD)."""
        return self.policy.total_records.premium_td

    @property
    def total_regular_premium_ytd(self) -> Decimal:
        """Total regular premium year-to-date from LH_POL_YR_TOT (VBA: TotalRegularPremiumYTD)."""
        return self.policy.total_records.total_regular_premium_ytd

    @property
    def total_additional_premium_ytd(self) -> Decimal:
        """Total additional premium year-to-date from LH_POL_YR_TOT (VBA: TotalAdditionalPremiumYTD)."""
        return self.policy.total_records.total_additional_premium_ytd

    @property
    def premium_ytd(self) -> Decimal:
        """Premium year-to-date = regular YTD + additional YTD (VBA: PremiumYTD)."""
        return self.policy.total_records.premium_ytd

    @property
    def next_bill_date(self) -> Optional[date]:
        """Next billing date."""
        return self._parse_date(self._field("next_bill_date"))

    @property
    def premium_paid_to_date(self) -> Optional[date]:
        """Premium paid-to date."""
        return self._parse_date(self._field("premium_paid_to_date"))

    @property
    def forced_premium_indicator(self) -> bool:
        """Whether policy has forced premium."""
        return str(self._field("forced_premium_indicator")) == "1"

    @property
    def mdo_code(self) -> str:
        """MDO (market/distribution) code."""
        return str(self._field("mdo_code") or "")

    @property
    def bill_form_code(self) -> str:
        """Billing form code."""
        return str(self._field("bill_form_code") or "")

    @property
    def is_eft(self) -> bool:
        """True if billing uses electronic funds transfer (PAC/EFT).

        CyberLife BIL_FRM_CD values (via VBA TranslateBillFormCode):
            0 = Direct pay notice  (NOT EFT)
            G = PAC                (EFT)
            H = Salary deduction   (EFT)
            I = Bank deduction     (EFT)
            F = Government allotment (EFT)
        Non-direct-bill forms use the EFT modal factor for monthly billing.
        """
        # Anything other than "0" (direct pay notice) is considered EFT
        return self.bill_form_code not in ("0", "")

    @property
    def short_pay_duration(self) -> Optional[int]:
        """Short pay duration in years from TH_USER_GENERIC."""
        val = self.data_item("TH_USER_GENERIC", "INITIAL_PAY_DUR")
        return int(val) if val and int(val) > 0 else None

    @property
    def short_pay_mode(self) -> Optional[str]:
        """Short pay mode from TH_USER_GENERIC."""
        return str(self.data_item("TH_USER_GENERIC", "INITIAL_MODE") or "") if self.short_pay_duration else None

    @property
    def short_pay_premium(self) -> Optional[Decimal]:
        """Short pay premium amount from LH_POL_TARGET where TAR_TYP_CD = 'VS'."""
        val = self.targets._get_target_amount("VS")
        return val

    @property
    def short_pay_date(self) -> Optional[date]:
        """Short pay billing cease date from LH_POL_TARGET where TAR_TYP_CD = 'VS'."""
        val = self.targets._get_target_date("VS")
        return val

    @property
    def sp_billing_cease_date(self) -> Optional[date]:
        """Short pay billing cease date (alias for short_pay_date)."""
        return self.short_pay_date

    @property
    def sp_prem_cease_age(self) -> Optional[int]:
        """Short pay premium cease age - calculated as duration + issue age of base coverage."""
        if not self.short_pay_duration:
            return None
        # Get issue age of first base coverage (coverage index 1)
        issue_age = self.coverages.cov_issue_age(1)
        if issue_age:
            return self.short_pay_duration + issue_age
        return None
