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

    # Rate detail for the Values tab (CalcEngine HO..HV / JI..JP / IU).
    mtp_rates_by_coverage: Dict[int, float] = field(default_factory=dict)
    mtp_tbl_rates_by_coverage: Dict[int, float] = field(default_factory=dict)
    ctp_rates_by_coverage: Dict[int, float] = field(default_factory=dict)
    ctp_tbl_rates_by_coverage: Dict[int, float] = field(default_factory=dict)
    pw_rate: float = 0.0        # IU — PW MTPR
    mtp_wo_pw: float = 0.0      # IT
    ctp_wo_pw: float = 0.0      # KN basis (cov + benefit CTPs before PW)

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
    # policy.segments holds only active base coverages (same convention as the
    # deduction path — no status filtering here).
    for seg in policy.segments:
        if seg.face_amount <= 0:
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
        mtp_rate = rates_db.get_mtp(*args) or 0.0
        mtp_tbl_rate = rates_db.get_tbl1_mtp(*args) or 0.0
        ctp_rate = rates_db.get_ctp(*args) or 0.0
        ctp_tbl_rate = rates_db.get_tbl1_ctp(*args) or 0.0
        mtp_val = _segment_target(
            sa, mtp_rate, mtp_tbl_rate, table, flat, cap_tbl_rate=False,
        )
        ctp_val = _segment_target(
            sa, ctp_rate, ctp_tbl_rate, table, flat, cap_tbl_rate=True,
        )
        result.mtp_rates_by_coverage[seg.coverage_phase] = mtp_rate
        result.mtp_tbl_rates_by_coverage[seg.coverage_phase] = mtp_tbl_rate
        result.ctp_rates_by_coverage[seg.coverage_phase] = ctp_rate
        result.ctp_tbl_rates_by_coverage[seg.coverage_phase] = ctp_tbl_rate
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
        # Benefits contribute no target from their payup/cease anniversary on —
        # STRICT, matching the deduction loop's vPW_Active gate (attained age <
        # payup age). Segment table/flat cease stays inclusive (_active).
        if ben.cease_date is not None and as_of is not None and as_of >= ben.cease_date:
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

    result.pw_rate = pw_rate
    result.mtp_wo_pw = mtp_wo_pw
    result.ctp_wo_pw = ctp_wo_pw
    result.pw_component = pw_component
    result.mtp_annual = mtp_wo_pw + pw_component
    result.ctp_annual = ctp_wo_pw + _round2(pw_component)
    return result


def build_target_detail_snapshots(
    policy: IllustrationPolicyData,
    result: TargetPremiumResult,
) -> tuple[Dict[str, object], Dict[str, object]]:
    """MTP / CTP per-component snapshots keyed by the RERUN display names.

    Mirrors CalcEngine HO..JG (MTP) and JI..KQ (CTP). The engine's base
    segments map onto RERUN's Cov 1..3 slots (same convention as the Cov After
    Change snapshot); APB is not modeled, so its slots stay 0. Benefit slots:
    PW = type 39, GIR/GIO = type+subtype 76, CCV = type A; PWSTP/CTR/ADB have
    no target rates for this product family — unmapped benefit targets land in
    "Other Benefits" so nothing silently disappears.
    """
    segments = sorted(
        (s for s in policy.segments if getattr(s, "is_base", True)),
        key=lambda s: s.coverage_phase,
    )
    mtp: Dict[str, object] = {}
    ctp: Dict[str, object] = {}
    for index in (1, 2, 3):
        seg = segments[index - 1] if index - 1 < len(segments) else None
        phase = seg.coverage_phase if seg else None
        mtp[f"MTP Rate Cov {index}"] = result.mtp_rates_by_coverage.get(phase, 0.0)
        mtp[f"MTP Rate Cov {index} Tbl"] = result.mtp_tbl_rates_by_coverage.get(phase, 0.0)
        mtp[f"MTP Cov {index}"] = result.mtp_by_coverage.get(phase, 0.0)
        ctp[f"CTP Rate Cov {index}"] = result.ctp_rates_by_coverage.get(phase, 0.0)
        ctp[f"CTP Rate Cov {index} Tbl"] = result.ctp_tbl_rates_by_coverage.get(phase, 0.0)
        ctp[f"CTP Cov {index}"] = result.ctp_by_coverage.get(phase, 0.0)
    mtp["MTP APB"] = 0.0
    ctp["CTP APB"] = 0.0

    ccv_keys = {k for k in result.mtp_benefits if k.startswith("A")}
    named = {"39": "PW", "76": "GIR"}
    def _ben(values: Dict[str, float], slot: str) -> float:
        if slot == "CCV":
            return sum(values.get(k, 0.0) for k in ccv_keys)
        return sum(v for k, v in values.items() if named.get(k) == slot)
    for label, slot in (("CCV", "CCV"), ("GIR", "GIR")):
        mtp[f"{label} MTP"] = _ben(result.mtp_benefits, slot)
        ctp[f"{label} CTP"] = _ben(result.ctp_benefits, slot)
    other_keys = [
        k for k in result.mtp_benefits
        if k not in named and k not in ccv_keys
    ]
    mtp["Other Benefits MTP"] = sum(result.mtp_benefits[k] for k in other_keys)
    ctp["Other Benefits CTP"] = sum(result.ctp_benefits.get(k, 0.0) for k in other_keys)

    mtp["MTP w/o PW"] = result.mtp_wo_pw          # IT
    mtp["PW MTPR"] = result.pw_rate               # IU
    mtp["PW MTP"] = result.pw_component           # IV
    mtp["vMTP"] = result.mtp_annual               # JG
    ctp["CTP w/o PW"] = result.ctp_wo_pw          # KN basis
    ctp["CTP PW"] = _round2(result.pw_component)  # KP = ROUND(IV, 2)
    ctp["vCTP"] = result.ctp_annual               # KQ
    ctp["Target Band"] = result.target_band
    return mtp, ctp


def floor_monthly_cent(value: float) -> float:
    """RERUN's guideline floor: INT(x/12*100)*12/100 (KS/KT).

    Floors an annual amount so the monthly twelfth is an exact cent amount.
    Decimal arithmetic — binary floats put already-exact values like 52004.28
    a hair below their cent boundary and a raw floor() drops a cent.
    """
    if value <= 0.0:
        return value
    monthly_cents = (Decimal(f"{value:.10f}") * 100 / 12).to_integral_value(rounding=ROUND_DOWN)
    return float(monthly_cents * 12) / 100.0
