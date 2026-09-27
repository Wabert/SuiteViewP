"""PolicyInformation support section."""

from __future__ import annotations

from .base import PolicySection
from typing import Any
from typing import Dict
from typing import Optional


class SupportSection(PolicySection):
    """Cohesive PolicyInformation support view."""

    TABLES = frozenset(('DECREASE_CHARGE_RULE', 'FUZGREIN_IND', 'TH_USER_GENERIC',))
    CACHE_ATTRS = ()

    @property
    def is_ffs(self) -> bool:
        """Whether policy is Fee-for-Service (IMG with specific branch)."""
        return self.agents.servicing_market_org == "IMG" and self.agents.agency_branch_code == "0B4Q"

    @property
    def decrease_charge_rule(self) -> str:
        """Decrease Charge Rule code (TH_NON_TRD_POL.DECR_CHRG_ALLOW, FULDRRUL).

        Live values are ``"1"`` (specified decreases assess a partial surrender
        charge) and ``"0"`` (they do not). Blank/NUL-padded rows are unset and
        return ``""``.
        """
        return str(self._field("decrease_charge_rule") or "").strip(" \x00")

    @property
    def decrease_charge_allowed(self) -> Optional[bool]:
        """Whether a specified-amount decrease assesses a partial surrender charge.

        ``None`` when the Decrease Charge Rule is unset or unrecognized, so
        callers keep their plan-level rule rather than guessing.
        """
        return {"1": True, "0": False}.get(self.decrease_charge_rule)

    @property
    def reins_partner(self) -> str:
        """Reinsurance partner indicator from TH_USER_GENERIC.FUZGREIN_IND.

        Originally created 11/13/2024 to identify policies in the RGA Orion deal.
        """
        return str(self.data_item("TH_USER_GENERIC", "FUZGREIN_IND") or "").strip()

    def to_inforce_dict(self) -> Dict[str, Any]:
        """
        Export policy data as an inforce dictionary - similar to VBA InforceDictionary.
        Useful for integration with external systems.
        """
        return {
            "Policy": {
                "Policynumber": self.identity.policy_number,
                "CompanyCode": self.identity.company_code,
                "Company": self.identity.company_name,
                "StatusCode": self.status.status_code,
                "MarketOrg": self.agents.servicing_market_org,
                "ProductType": self.product.product_type,
                "IsFFS": self.is_ffs,
                "BillablePremium": float(self.billing.regular_premium or 0),
                "BillingMode": self.billing.billing_mode,
                "GPEDate": str(self.status.grace_period_expiry_date) if self.status.grace_period_expiry_date else "",
                "IssueState": self.product.issue_state,
                "DBOption": self.product.db_option_code,
                "MTP": float(self.targets.mtp or 0),
                "CTP": float(self.targets.ctp or 0),
                "GLP": float(self.targets.glp or 0),
                "GSP": float(self.targets.gsp or 0),
                "AccumGLP": float(self.targets.accumulated_glp_target or 0),
                "AccumMTP": float(self.targets.accumulated_mtp_target or 0),
                "RegLoanPrincipal": float(self.loans.total_regular_loan_principal),
                "RegLoanAccrued": float(self.loans.total_regular_loan_accrued),
                "PrefLoanPrincipal": float(self.loans.total_preferred_loan_principal),
                "PrefLoanAccrued": float(self.loans.total_preferred_loan_accrued),
                "VarLoanPrincipal": float(self.loans.total_variable_loan_principal),
                "VarLoanAccrued": float(self.loans.total_variable_loan_accrued),
                "CostBasis": float(self.values.cost_basis or 0),
                "IsMEC": self.values.is_mec,
                "ValuationDate": str(self.values.valuation_date) if self.values.valuation_date else "",
                "MVAV": float(self.values.mv_av() or 0),
                "TotalAV": float(self.values.total_fund_value),
                "TotalSpecifiedAmount": float(self.coverages.total_specified_amount),
            },
            "Funds": self.values.get_fund_values_dict(),
            "PremAllocation": self.values.get_premium_allocation_dict(),
            "BaseCovs": [c.raw_data for c in self.coverages.get_coverages() if c.is_base],
            "RiderCovs": [c.raw_data for c in self.coverages.get_coverages() if not c.is_base],
            "Benefits": [b.raw_data for b in self.benefits.get_benefits()],
        }
