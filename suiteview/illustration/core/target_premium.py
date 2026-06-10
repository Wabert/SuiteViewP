"""Minimum / Commission Target Premium (vMTP / vCTP) — RERUN CalcEngine JG / KQ.

Computes the annual target premiums from rates, exactly as RERUN does when
``vPolicyChangeIndicator`` fires (and as admin does at issue):

    per coverage segment (HW..HZ / JQ..JT):
        ROUND(SA·rate/1000, 2)
      + ROUND(tableRating·tblRate·SA/1000, 2)        (CTP caps tblRate at 6)
      + ROUND((12·TRUNC(flat/12,2))·SA/1000, 2)
    + benefit targets (CCV: rate·SA/1000; others: units·rate)
    + Premium Waiver (IV): pwRate·(target w/o PW, MTP basis)·(1 + factor·table)
      — the PW component of vCTP is the SAME MTP-basis value, ROUNDed (KP=IV).

    vMTP = MTP components + IV                       (IV at full precision)
    vCTP = CTP components + ROUND(IV, 2)
    vMonthlyMTP = TRUNC(vMTP/12, 2)                  (truncation happens at use)

Validated against the U0688012 fixture: computed vMTP/12 -> 150.13 (DB value)
and vCTP -> 2043.64 (DB value) exactly, and the face-change ratios match the
captured RERUN references (increase 1.7337, decrease 0.9832).

Rate sources (local rates.sqlite / UL_Rates):
    Select_RATE_MTP / Select_RATE_TBL1MTP / Select_RATE_CTP / Select_RATE_TBL1CTP
        keyed by (plancode, segment issue age, sex, rateclass, band)
    Select_RATE_BENMTP / Select_RATE_BENCTP
        keyed by (plancode, benefit key, POLICY issue age, sex, rateclass, band)

Band semantics (RERUN PolicyRates CO: IF(sTarget_BandLock, EY, FD)): when the
plancode does not lock bands, target rates use the band of the CURRENT total
specified amount — a face change re-bands every segment's target rate.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Dict, Optional

from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import IllustrationPolicyData


def _round2(value: float) -> float:
    return float(Decimal(f"{value:.12f}").quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _trunc2(value: float) -> float:
    return float(Decimal(f"{value:.12f}").quantize(Decimal("0.01"), rounding=ROUND_DOWN))


def _active(cease_date: Optional[date], as_of: Optional[date]) -> bool:
    if cease_date is None or as_of is None:
        return True
    return as_of <= cease_date


@dataclass
class TargetPremiumResult:
    """Annual target premiums plus per-component detail for auditing."""

    mtp_annual: float = 0.0
    ctp_annual: float = 0.0
    mtp_by_coverage: Dict[int, float] = field(default_factory=dict)
    ctp_by_coverage: Dict[int, float] = field(default_factory=dict)
    mtp_benefits: Dict[str, float] = field(default_factory=dict)
    ctp_benefits: Dict[str, float] = field(default_factory=dict)
    pw_component: float = 0.0   # IV — full precision, MTP basis
    target_band: int = 0

    @property
    def mtp_monthly(self) -> float:
        """vMonthlyMTP = TRUNC(vMTP/12, 2)."""
        return _trunc2(self.mtp_annual / 12.0)


def _segment_target(
    sa: float,
    rate: float,
    tbl_rate: float,
    table_rating: int,
    flat_extra: float,
    cap_tbl_rate: bool,
) -> float:
    """One coverage segment's target premium (CalcEngine HW / JQ).

    The substandard term multiplies the table RATING (e.g. 2 for Table B) by the
    per-table rate from TBL1MTP/TBL1CTP — the plancode's 25% factor is built into
    that rate, not applied here. CTP caps the per-table rate at 6 (JQ MIN(6,...)).
    """
    tbl = min(6.0, tbl_rate) if cap_tbl_rate else tbl_rate
    flat_monthly = _trunc2(flat_extra / 12.0) if flat_extra else 0.0
    return (
        _round2(sa * rate / 1000.0)
        + _round2(table_rating * tbl * sa / 1000.0)
        + _round2(12.0 * flat_monthly * sa / 1000.0)
    )


def compute_target_premiums(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    as_of: Optional[date] = None,
) -> TargetPremiumResult:
    """Compute annual vMTP / vCTP from rates for the policy's CURRENT coverage state.

    Call after mutating segments for a policy change to get the recomputed
    targets (RERUN recomputes when vPolicyChangeIndicator fires). Reads the
    rates DB (cached at the Rates class level); works offline under
    SUITEVIEW_LOCAL_DATA.
    """
    from suiteview.core.rates import Rates

    rates_db = Rates()
    result = TargetPremiumResult()
    if not policy.segments:
        return result

    base = policy.base_segment
    total_face = policy.total_face

    # Target band: current total-SA band unless the plancode locks bands.
    current_band = rates_db.get_band(policy.plancode, total_face)
    current_band = int(current_band) if current_band is not None else base.band
    result.target_band = current_band

    mtp_cov_sum = 0.0
    ctp_cov_sum = 0.0
    for seg in policy.segments:
        if seg.face_amount <= 0 or seg.status != "A":
            continue
        band = seg.original_band if config.target_band_lock else current_band
        sa = (
            seg.original_face_amount
            if config.target_sa_basis == "OriginalSA"
            else seg.face_amount
        )
        table = (
            seg.table_rating
            if seg.table_rating > 0 and _active(seg.table_cease_date, as_of)
            else 0
        )
        flat = (
            seg.flat_extra
            if seg.flat_extra and seg.flat_extra > 0 and _active(seg.flat_cease_date, as_of)
            else 0.0
        )
        args = (policy.plancode, seg.issue_age, seg.rate_sex, seg.rate_class, band)
        mtp_val = _segment_target(
            sa, rates_db.get_mtp(*args) or 0.0, rates_db.get_tbl1_mtp(*args) or 0.0,
            table, flat, cap_tbl_rate=False,
        )
        ctp_val = _segment_target(
            sa, rates_db.get_ctp(*args) or 0.0, rates_db.get_tbl1_ctp(*args) or 0.0,
            table, flat, cap_tbl_rate=True,
        )
        result.mtp_by_coverage[seg.coverage_phase] = mtp_val
        result.ctp_by_coverage[seg.coverage_phase] = ctp_val
        mtp_cov_sum += mtp_val
        ctp_cov_sum += ctp_val

    # Benefit targets — looked up at the POLICY issue age (RERUN
    # tRates_Benefit_Targets key uses sINPUT_Issue_Age), base sex/rateclass and
    # the target band. PW is applied last against the MTP-without-PW total.
    ben_band = base.original_band if config.target_band_lock else current_band
    pw_rate = 0.0
    mtp_ben_sum = 0.0
    ctp_ben_sum = 0.0
    for ben in policy.benefits:
        ben_type = ben.benefit_type or ""
        if not ben.is_active or ben_type.startswith("#"):
            continue
        if not _active(ben.cease_date, as_of):
            continue
        ben_key = ben_type + (ben.benefit_subtype or "")
        ben_args = (
            policy.plancode, policy.issue_age, base.rate_sex, base.rate_class,
            ben_band, ben_key,
        )
        ben_mtp_rate = rates_db.get_ben_mtp(*ben_args) or 0.0
        ben_ctp_rate = rates_db.get_ben_ctp(*ben_args) or 0.0
        if ben_key in ("39", "3#"):
            pw_rate = ben_mtp_rate
            continue
        if ben_type == "A":
            # CCV (IM/KG): rate x current total SA / 1000.
            mtp_val = ben_mtp_rate * total_face / 1000.0
            ctp_val = ben_ctp_rate * total_face / 1000.0
        else:
            # ADB/CTR/GIO etc. (IO/IQ/IS): units x rate.
            # TODO: verify PWST (stipulated premium waiver) if a case appears —
            # RERUN multiplies its units-x-rate by (1 + factor*table) (IK).
            mtp_val = (ben.units or 0.0) * ben_mtp_rate
            ctp_val = (ben.units or 0.0) * ben_ctp_rate
        result.mtp_benefits[ben_key] = mtp_val
        result.ctp_benefits[ben_key] = ctp_val
        mtp_ben_sum += mtp_val
        ctp_ben_sum += ctp_val

    # Riders: RERUN's rider target tables (tRates_Rider_SigTerm_Targets) are
    # dead references for this product family — UL riders contribute no target
    # premium. Revisit if a product with rider target rates appears.

    mtp_wo_pw = mtp_cov_sum + mtp_ben_sum
    ctp_wo_pw = ctp_cov_sum + ctp_ben_sum

    # PW (IV): pwRate x (MTP w/o PW) x (1 + factor x base table rating).
    pw_component = 0.0
    if pw_rate > 0.0:
        base_table = (
            base.table_rating
            if base.table_rating > 0 and _active(base.table_cease_date, as_of)
            else 0
        )
        pw_component = pw_rate * mtp_wo_pw * (
            1.0 + config.table_rating_factor * base_table
        )
        result.mtp_benefits["39"] = pw_component
        result.ctp_benefits["39"] = _round2(pw_component)

    result.pw_component = pw_component
    result.mtp_annual = mtp_wo_pw + pw_component
    result.ctp_annual = ctp_wo_pw + _round2(pw_component)
    return result


def floor_monthly_cent(value: float) -> float:
    """RERUN's guideline floor: INT(x/12*100)*12/100 (KS/KT).

    Floors an annual amount so the monthly twelfth is an exact cent amount.
    """
    if value <= 0.0:
        return value
    return math.floor(value / 12.0 * 100.0) * 12.0 / 100.0
