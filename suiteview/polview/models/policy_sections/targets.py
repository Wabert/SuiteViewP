"""PolicyInformation targets section."""

from __future__ import annotations

from .base import PolicySection
from ..cl_polrec.policy_data_classes import CoverageTargetInfo
from ..cl_polrec.policy_translations import translate_coverage_target_type
from datetime import date
from decimal import Decimal
from typing import List
from typing import Optional


class TargetsSection(PolicySection):
    """Cohesive PolicyInformation targets view."""

    TABLES = frozenset(('COV_PHA_NBR', 'DIAL_TO_PREM_AGE', 'GDL_PRM_AMT', 'LH_COM_TARGET', 'LH_COV_INS_GDL_PRM', 'LH_COV_TARGET', 'LH_POL_TARGET', 'PRM_RT_TYP_CD', 'TAR_DT', 'TAR_PRM_AMT', 'TAR_TYP_CD', 'TAR_VAL_AMT', 'TH_USER_GENERIC',))
    CACHE_ATTRS = ()

    def _get_target_amount(self, target_type: str) -> Optional[Decimal]:
        """Get target premium amount by type code using data_item_where pattern."""
        val = self.data_item_where("LH_POL_TARGET", "TAR_PRM_AMT", "TAR_TYP_CD", target_type)
        return Decimal(str(val)) if val is not None else None

    def _get_target_date(self, target_type: str) -> Optional[date]:
        """Get target date by type code using data_item_where pattern."""
        val = self.data_item_where("LH_POL_TARGET", "TAR_DT", "TAR_TYP_CD", target_type)
        return self._parse_date(val)

    @property
    def mtp(self) -> Optional[Decimal]:
        """Minimum Target Premium (TAR_TYP_CD = 'MT')."""
        return self._get_target_amount("MT")

    @property
    def accumulated_mtp_target(self) -> Optional[Decimal]:
        """Accumulated MTP from targets (TAR_TYP_CD = 'MA')."""
        return self._get_target_amount("MA")

    @property
    def map_date(self) -> Optional[date]:
        """MAP (SafetyNet) cease date (TAR_TYP_CD = 'MA')."""
        return self._get_target_date("MA")

    @property
    def accumulated_glp_target(self) -> Optional[Decimal]:
        """Accumulated GLP from targets (TAR_TYP_CD = 'TA')."""
        return self._get_target_amount("TA")

    @property
    def plt(self) -> Optional[Decimal]:
        """Premium Limit Target (TAR_TYP_CD = 'LT')."""
        return self._get_target_amount("LT")

    @property
    def gav(self) -> Optional[Decimal]:
        """GAV (Guaranteed Account Value) from Index target (TAR_TYP_CD = 'IX')."""
        return self._get_target_amount("IX")

    @property
    def dial_to_premium(self) -> Optional[Decimal]:
        """Dial-to premium amount (TAR_TYP_CD = 'DT')."""
        return self._get_target_amount("DT")

    @property
    def nsp_base(self) -> Optional[Decimal]:
        """NSP Base target (TAR_TYP_CD = 'NS')."""
        return self._get_target_amount("NS")

    @property
    def nsp_other(self) -> Optional[Decimal]:
        """NSP Other target (TAR_TYP_CD = 'NT')."""
        return self._get_target_amount("NT")

    @property
    def ctp(self) -> Optional[Decimal]:
        """Commission Target Premium - sum of all CT entries."""
        # CTP can have multiple records, so we sum them
        amounts = self.data_items_where("LH_COM_TARGET", "TAR_PRM_AMT", "TAR_TYP_CD", "CT")
        if not amounts:
            return None
        total = Decimal("0")
        for val in amounts:
            if val is not None:
                total += Decimal(str(val))
        return total if total > 0 else None

    @property
    def db_dial_to_age(self) -> Optional[int]:
        """Death benefit dial-to premium age from TH_USER_GENERIC."""
        val = self.data_item("TH_USER_GENERIC", "DIAL_TO_PREM_AGE")
        return int(val) if val and int(val) > 0 else None

    @property
    def glp(self) -> Optional[Decimal]:
        """Guideline Level Premium (PRM_RT_TYP_CD = 'A')."""
        val = self.data_item_where("LH_COV_INS_GDL_PRM", "GDL_PRM_AMT", "PRM_RT_TYP_CD", "A")
        return Decimal(str(val)) if val is not None else None

    @property
    def gsp(self) -> Optional[Decimal]:
        """Guideline Single Premium (PRM_RT_TYP_CD = 'S')."""
        val = self.data_item_where("LH_COV_INS_GDL_PRM", "GDL_PRM_AMT", "PRM_RT_TYP_CD", "S")
        return Decimal(str(val)) if val is not None else None

    def get_coverage_targets(self, cov_pha_nbr: int = None) -> List[CoverageTargetInfo]:
        """Get coverage-level targets, optionally filtered by coverage."""
        targets = []
        for row in self.fetch_table("LH_COV_TARGET"):
            phase = int(row.get("COV_PHA_NBR", 0) or 0)
            if cov_pha_nbr is not None and phase != cov_pha_nbr:
                continue

            target_type = str(row.get("TAR_TYP_CD", "") or "")
            target = CoverageTargetInfo(
                coverage_phase=phase,
                target_type=target_type,
                target_type_desc=translate_coverage_target_type(target_type),
                target_amount=Decimal(str(row.get("TAR_PRM_AMT") or row.get("TAR_VAL_AMT") or 0)) or None,
                target_date=self._parse_date(row.get("TAR_DT")),
                raw_data=row
            )
            targets.append(target)
        return targets

    @property
    def ccv_target(self) -> Optional[Decimal]:
        """CCV (Coverage Continuation Value) target from LH_COV_TARGET (TAR_TYP_CD = 'CV')."""
        val = self.data_item_where("LH_COV_TARGET", "TAR_VAL_AMT", "TAR_TYP_CD", "CV")
        return Decimal(str(val)) if val else None

    @property
    def shadow_account_value(self) -> Optional[Decimal]:
        """Current shadow account value from segment 58 (premium type XP)."""
        val = self.data_item_where(
            "LH_COV_TARGET", "TAR_PRM_AMT", "TAR_TYP_CD", "XP"
        )
        return Decimal(str(val)) if val is not None else None

    @property
    def surrender_target(self) -> Optional[Decimal]:
        """Surrender target from LH_COV_TARGET (TAR_TYP_CD = 'SU')."""
        val = self.data_item_where("LH_COV_TARGET", "TAR_VAL_AMT", "TAR_TYP_CD", "SU")
        return Decimal(str(val)) if val else None
