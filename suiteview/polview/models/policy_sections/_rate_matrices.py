"""Fixed-premium and matrix helpers for the PolicyInformation rates section."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

from ..cl_polrec.policy_data_classes import CoverageInfo
from ..rate_matrices import (
    MatrixColumn,
    build_rate_matrix,
    duration_rows,
    metadata_value,
    rate_value_or_na,
)

try:
    from suiteview.core.rates import RatesError
except ImportError:
    RatesError = RuntimeError  # type: ignore[assignment,misc]


class RateMatrixMixin:
    """WL/fixed-premium and rendered matrix methods for ``RatesSection``."""

    _CV_RATE_FIELD_NAMES = ("stored_cv_0", "stored_cv_1", "stored_cv_2", "stored_cv_3")
    _NSP_RATE_FIELD_NAMES = ("stored_nsp_0", "stored_nsp_1", "stored_nsp_2")
    _NONFORFEITURE_STATUS = {"44": "ETI", "45": "RPU"}

    def cov_cash_value_key(self, cov_index: int) -> str:
        """CVF class/base/sub key from the coverage's valuation codes (1-based)."""
        if not 1 <= cov_index <= self.coverages.coverage_count:
            raise ValueError(f"Coverage index {cov_index} is out of range.")
        parts = []
        for column, width in (
            ("INS_CLS_CD", 1), ("PLN_BSE_SRE_CD", 3), ("LIF_PLN_SUB_SRE_CD", 2),
        ):
            value = self.data_item("LH_COV_PHA", column, cov_index - 1)
            if value is None:
                raise ValueError(f"Coverage {cov_index} is missing {column} for its CVF key.")
            text = str(value).strip().upper()
            if len(text) > width or (not text and column != "LIF_PLN_SUB_SRE_CD"):
                raise ValueError(f"Coverage {cov_index} has an invalid {column} for its CVF key.")
            parts.append(text.ljust(width))
        return "".join(parts)

    @property
    def cyberlife_rate_user_code(self) -> str:
        """CyberLife rate-file user for source-keyed WL/ISWL rates (01 -> 00)."""
        from suiteview.core.rates import cyberlife_rate_user
        return cyberlife_rate_user(self.policy.company_code)

    @property
    def has_fixed_premium_rates(self) -> bool:
        """ISWL or traditional WL: IAF premiums, CVF cash values and mode factors apply."""
        return self.product.product_rules.rate_family in {"ISWL", "WL"}

    def cov_rate_sex_code(self, cov_index: int) -> str:
        """CyberLife sex code (1/2/3) for rate keys: the 67 segment, else LH_COV_PHA."""
        code = self.renewal_cov_sex_code(cov_index)
        if not code:
            code = str(self.data_item("LH_COV_PHA", "INS_SEX_CD", cov_index - 1) or "")
        return code.strip()

    def rates_wl_cv(self, cov_index: int, user_defined: str = "") -> Dict[int, Decimal]:
        """Whole Life cash values by actual source duration, not a one-based array."""
        key = self.cov_cash_value_key(cov_index)
        age = self.coverages.cov_issue_age(cov_index)
        if age is None:
            raise ValueError(f"Coverage {cov_index} is missing its cash-value issue age.")
        rates = self._get_rates()
        if rates is None:
            raise RuntimeError("The shared rates service is not available.")
        return rates.get_wl_cash_values(self.cyberlife_rate_user_code, key, age, user_defined)

    def rates_wl_premium(self, plancode: str, issue_age: int, issue_date: Optional[date]) -> Dict[str, Any]:
        """IAF premium cells (WL_RATE_PREM) for a plancode at an issue age."""
        rates = self._get_rates()
        if rates is None:
            raise RuntimeError("The shared rates service is not available.")
        return rates.get_wl_premium_rates(self.cyberlife_rate_user_code, plancode, issue_age, issue_date)

    def rates_modal_factors(self) -> Dict[str, Any]:
        """Base plan mode factors and policy fee (POINT_MODEFACT -> RATE_MODEFACT)."""
        rates = self._get_rates()
        if rates is None:
            raise RuntimeError("The shared rates service is not available.")
        return rates.get_modal_factors(self.coverages.cov_plancode(1))

    def build_premium_rate_matrix(self, cov_index: int) -> List[List]:
        """IAF base and benefit premium rates for a fixed-premium coverage."""
        from ..fixed_premium_rates import build_premium_rate_matrix
        return build_premium_rate_matrix(self, cov_index)

    def build_modal_premium_matrix(self) -> List[List]:
        """Modal premium from IAF rates and RATE_MODEFACT, beside POL_PRM_AMT."""
        from ..fixed_premium_rates import build_modal_premium_matrix
        return build_modal_premium_matrix(self)

    def cov_cash_value_rates(self, cov_index: int) -> Dict[str, Any]:
        """Stored 02-segment cash value rates in play for a coverage (1-based).

        Uses the CV rates when present; otherwise the NSP rates, which CyberLife
        carries for nonforfeiture (ETI/RPU) and paid-up coverages. Rates are per
        coverage unit, keyed by the policy duration where each value applies.
        """
        if not 1 <= cov_index <= self.coverages.coverage_count:
            raise ValueError(f"Coverage index {cov_index} is out of range.")
        idx = cov_index - 1

        def values(field_names):
            return [self._parse_optional_decimal(self._field(name, idx)) for name in field_names]

        cv = values(self._CV_RATE_FIELD_NAMES)
        nsp = values(self._NSP_RATE_FIELD_NAMES)
        if any(v for v in cv):
            basis, rates = "CV", cv
        elif any(v for v in nsp):
            basis, rates = "NSP", nsp
        else:
            basis, rates = None, []

        low_duration = self._parse_optional_int(self._field("stored_cv_low_duration", idx))
        schedule: Dict[int, Decimal] = {}
        if basis and low_duration is not None:
            schedule = {low_duration + k: v for k, v in enumerate(rates) if v is not None}

        return {
            "cov_index": cov_index,
            "cov_pha_nbr": self._parse_optional_int(self.data_item("LH_COV_PHA", "COV_PHA_NBR", idx)),
            "basis": basis,
            "nonforfeiture": self._NONFORFEITURE_STATUS.get(self.status.premium_pay_status_code, ""),
            "low_duration": low_duration,
            "rates": schedule,
            "units": self._parse_optional_decimal(self.data_item("LH_COV_PHA", "COV_UNT_QTY", idx)),
            "vpu": self._parse_optional_decimal(self.data_item("LH_COV_PHA", "COV_VPU_AMT", idx)),
        }

    def _guaranteed_cash_value_date(self) -> Optional[date]:
        """Last processed monthliversary; the stored monthly value date can be
        stale for advanced policies on nonforfeiture."""
        from dateutil.relativedelta import relativedelta

        candidates = []
        next_mv = self.activity.next_monthliversary_date
        if next_mv and next_mv.year < 9999:
            candidates.append(next_mv - relativedelta(months=1))
        if self.values.valuation_date:
            candidates.append(self.values.valuation_date)
        return max(candidates) if candidates else None

    def _guaranteed_cash_value_detail(
        self,
        cov_index: int,
        info: Dict[str, Any],
        coverages: Dict[int, CoverageInfo],
        as_of: date,
    ):
        from dateutil.relativedelta import relativedelta

        if not info["basis"]:
            return None, None, None, None
        label = f"Cov {info['cov_pha_nbr'] or cov_index}"
        cov = coverages.get(info["cov_pha_nbr"])
        if cov is None:
            return None, None, f"{label}: coverage record unavailable", None
        if not self.coverages._coverage_is_active(cov, as_of):
            return None, None, None, f"{label}: coverage not active"
        issue = cov.issue_date
        if issue is None or info["units"] is None:
            return None, None, f"{label}: missing issue date or units", None
        if as_of < issue:
            return None, None, f"{label}: as-of date precedes issue date", None

        duration = self.activity._completed_date_parts_years(issue, as_of)
        anniversary = issue + relativedelta(years=duration)
        months = 0
        while months < 12 and anniversary + relativedelta(months=months + 1) <= as_of:
            months += 1
        boy = info["rates"].get(duration)
        eoy = info["rates"].get(duration + 1)
        if boy is None or eoy is None:
            available = sorted(info["rates"])
            span = f"{available[0]}-{available[-1]}" if available else "none"
            return (
                None,
                None,
                f"{label}: stored {info['basis']} rates cover durations "
                f"{span}, not {duration}-{duration + 1}",
                None,
            )
        value = (info["units"] * (boy * (12 - months) + eoy * months) / 12).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP)
        detail = {
            "cov_index": cov_index, "cov_pha_nbr": info["cov_pha_nbr"],
            "basis": info["basis"], "nonforfeiture": info["nonforfeiture"],
            "duration": duration, "months": months, "boy_rate": boy, "eoy_rate": eoy,
            "units": info["units"], "value": value,
        }
        return detail, value, None, None

    def guaranteed_cash_value(self, as_of: Optional[date] = None) -> Dict[str, Any]:
        """Interpolated guaranteed cash value from the stored 02-segment rates.

        For each active coverage with stored CV (or nonforfeiture NSP) rates:
        units x (BOY rate x months remaining + EOY rate x months elapsed) / 12,
        where BOY/EOY are the rates at the completed policy duration and the next
        one, and months are completed months since the anniversary on or before
        ``as_of`` (default: the last processed monthliversary). Coverages that are
        not active are excluded; if any active coverage with stored rates cannot
        be valued, ``value`` is None with a ``reason`` rather than a partial total.
        """
        as_of = as_of or self._guaranteed_cash_value_date()
        result: Dict[str, Any] = {"value": None, "as_of": as_of, "details": [], "reason": ""}
        if as_of is None:
            result["reason"] = "No valuation date"
            return result
        coverages = {cov.cov_pha_nbr: cov for cov in self.coverages.get_coverages()}
        total = Decimal("0")
        excluded, blockers = [], []
        for cov_index in range(1, self.coverages.coverage_count + 1):
            info = self.cov_cash_value_rates(cov_index)
            detail, value, blocker, excluded_reason = self._guaranteed_cash_value_detail(
                cov_index, info, coverages, as_of)
            if blocker:
                blockers.append(blocker)
                continue
            if excluded_reason:
                excluded.append(excluded_reason)
                continue
            if detail is None:
                continue
            total += value
            result["details"].append(detail)
        if result["details"] and not blockers:
            result["value"] = total
        reasons = blockers + excluded
        if not reasons and not result["details"]:
            reasons.append("No stored cash value or NSP rates")
        result["reason"] = "; ".join(reasons)
        return result

    def _stored_cv_check(self, cov_index: int, cash_values: Dict[int, Decimal]) -> str:
        """Compare the 02 segment's stored LOW_DUR CV window with the CVF schedule."""
        stored = self.cov_cash_value_rates(cov_index)
        if stored["basis"] != "CV" or not stored["rates"]:
            return f"Stored rates are {stored['basis']} (not compared)" if stored["basis"] else "None stored"
        durations = sorted(stored["rates"])
        differences = [
            f"dur {d}: {stored['rates'][d]} vs {cash_values.get(d, 'none')}"
            for d in durations if cash_values.get(d) != stored["rates"][d]
        ]
        span = f"Durations {durations[0]}-{durations[-1]}"
        return f"{span} match" if not differences else "Differs: " + "; ".join(differences)

    def build_whole_life_coverage_rate_matrix(self, cov_index: int) -> Optional[List[List]]:
        """Source-keyed WL rates; other WL rate families can add independent schedules."""
        from dateutil.relativedelta import relativedelta

        cash_values = self.rates_wl_cv(cov_index)
        if not cash_values:
            return None
        issue_date = self.coverages.cov_issue_date(cov_index)
        issue_age = self.coverages.cov_issue_age(cov_index)
        coverage = self.coverages.get_coverages()[cov_index - 1]
        metadata = [
            ("Policy", self.policy.policy_number), ("Company", self.policy.company_code),
            ("Rate User", self.cyberlife_rate_user_code),
            ("Cov Index", cov_index), ("Plancode", coverage.plancode),
            ("Rate Key", self.cov_cash_value_key(cov_index)),
            ("User Defined", "(blank)"), ("Issue Age", issue_age),
            ("CV Basis", "Per coverage unit"),
            ("Value per Unit", coverage.vpu if coverage.vpu is not None else "Unknown"),
            ("Source", "WL_RATE_CV"), ("02 Stored CV", self._stored_cv_check(cov_index, cash_values)),
            ("NSP / PUI / Div", "Not yet available"),
        ]
        matrix = [["RateFields", "RateInfo", "Date", "Age", "Duration", "CV"]]
        schedule = sorted(cash_values.items())
        for row in range(max(len(metadata), len(schedule))):
            fields = list(metadata[row]) if row < len(metadata) else ["", ""]
            if row < len(schedule):
                duration, value = schedule[row]
                anniversary = issue_date + relativedelta(years=duration) if issue_date else None
                fields.extend([
                    anniversary.strftime("%m/%d/%Y") if anniversary else "",
                    issue_age + duration, duration, value,
                ])
            else:
                fields.extend(["", "", "", ""])
            matrix.append(fields)
        return matrix

    def build_coverage_rate_matrix(self, cov_index: int, scale: int = 1) -> Optional[List[List]]:
        """
        Build Whole Life cash values or the existing UL coverage-rate matrix.

        Returns a 2D list where:
          - Row 0 = column headers (RateFields, RateInfo, Date, Age, Year, COI, EPU, SCR, GuarCOI, GuarEPU)
          - Rows 1..N = data rows by policy year
          - RateFields/RateInfo columns contain metadata in early rows and blanks in data rows

        Args:
            cov_index: Coverage index (1-based)
            scale: Rate scale (default 1)

        Returns:
            2D list suitable for table display, or None if rates unavailable
        """
        rules = self.product._product_rules_for_rate_display()
        if rules.rate_family == "WL" and not rules.is_advanced:
            return self.build_whole_life_coverage_rate_matrix(cov_index)

        issue_date = self.coverages.cov_issue_date(cov_index)
        maturity_date = self.coverages.cov_maturity_date(cov_index)
        issue_age = self.coverages.cov_issue_age(cov_index)

        if issue_date is None or issue_age is None:
            return None

        # Calculate max years from issue to maturity
        if maturity_date and maturity_date > issue_date:
            xmax = (maturity_date.year - issue_date.year)
        else:
            xmax = 100 - issue_age  # fallback

        # Get single-value rates
        mtp = self.rates_mtp(cov_index)
        ctp = self.rates_ctp(cov_index)
        tbl1_mtp = self.rates_tbl1_mtp(cov_index)
        tbl1_ctp = self.rates_tbl1_ctp(cov_index)

        # Get rate arrays
        coi = self.rates_coi(cov_index, scale)
        epu = self.rates_epu(cov_index, scale)
        scr = self.rates_scr(cov_index, scale)
        guar_coi = self.rates_coi(cov_index, 0)  # Guaranteed (scale=0)
        guar_epu = self.rates_epu(cov_index, 0)  # Guaranteed (scale=0)

        # Calculate flat duration
        flat_extra = self.coverages.cov_flat_extra(cov_index)
        flat_duration = 0
        if flat_extra and float(flat_extra) > 0:
            flat_cease = self.coverages.cov_flat_cease_date(cov_index)
            if flat_cease and issue_date:
                flat_duration = flat_cease.year - issue_date.year

        # Get sex code for display (M/F)
        sex_code = self.renewal_cov_sex_code(cov_index)
        sex_display = self._translate_sex_for_rates(sex_code)

        # Get band
        band = self.cov_band(cov_index)
        band_display = band if band is not None else "Not Found"

        # Build metadata columns
        rate_fields = [
            " ", "Policy", "Cov Index", "Plancode", "IssueDate", "IssueAge",
            "Sex", "Rateclass", "Amount", "OrigAmount", "Band", "Table",
            "Flat", "Flat Duration", " ", "MTP", "CTP", "TBL1MTP", "TBL1CTP",
            " ", "Substandard is not", "included in rates"
        ]

        rate_info = [
            " ", self.policy.policy_number, cov_index, self.coverages.cov_plancode(cov_index),
            issue_date.strftime("%Y-%m-%d") if issue_date else "",
            issue_age, sex_display,
            self.renewal_cov_rateclass_by_cov(cov_index),
            self._whole_dollars(self.coverages.cov_amount(cov_index) or None),
            self._whole_dollars(self.coverages.cov_orig_amount(cov_index) or None),
            band_display, self.coverages.cov_table_rating(cov_index),
            str(flat_extra or 0), flat_duration,
            " ", mtp, ctp, tbl1_mtp, tbl1_ctp,
            " ", " ", " "
        ]

        # Ensure metadata lists are same length
        extra_columns: Dict[str, Optional[list]] = {}
        if rules.rate_family == "ISWL":
            iswl_meta, extra_columns = self._iswl_coverage_rate_extras(cov_index)
            rate_fields += [name for name, _ in iswl_meta]
            rate_info += [value for _, value in iswl_meta]
        max_meta = max(len(rate_fields), len(rate_info))
        xmax = max(xmax, max_meta)

        columns = [
            MatrixColumn("RateFields", lambda row: metadata_value(rate_fields, row.index)),
            MatrixColumn("RateInfo", lambda row: metadata_value(rate_info, row.index)),
            MatrixColumn("Date", lambda row: row.date_text),
            MatrixColumn("Age", lambda row: row.age),
            MatrixColumn("Year", lambda row: row.year),
            MatrixColumn("COI", lambda row: rate_value_or_na(coi, row.index)),
            MatrixColumn("EPU", lambda row: rate_value_or_na(epu, row.index)),
            MatrixColumn("SCR", lambda row: rate_value_or_na(scr, row.index)),
            MatrixColumn("GuarCOI", lambda row: rate_value_or_na(guar_coi, row.index)),
            MatrixColumn("GuarEPU", lambda row: rate_value_or_na(guar_epu, row.index)),
        ]
        columns.extend(
            MatrixColumn(name, lambda row, values=values: rate_value_or_na(values, row.index))
            for name, values in extra_columns.items()
        )
        return build_rate_matrix(columns, duration_rows(issue_date, issue_age, xmax))

    @staticmethod
    def _whole_dollars(amount) -> str:
        """Face amount for the rates grid: commas, no decimals; blank if unknown."""
        if amount is None or amount == "":
            return ""
        return f"{Decimal(str(amount)).quantize(Decimal('1'), rounding=ROUND_HALF_UP):,}"

    def _iswl_coverage_rate_extras(self, cov_index: int) -> Tuple[List[tuple], Dict[str, Optional[list]]]:
        """ISWL plan rates beside the UL view: GINT, CVR, premium, cease ages, loans.

        COI stays the current scale (1) only; older SCALE_COI windows are not shown.
        """
        rates = self._get_rates()
        if rates is None:
            raise RuntimeError("The shared rates service is not available.")
        plancode = self.coverages.cov_plancode(cov_index)
        calendar = sorted(
            ((row[0].date() if hasattr(row[0], "date") else row[0], int(row[1]))
             for row in (rates.get_rates("COI_SCALE", plancode) or [])),
            key=lambda entry: entry[0],
        )
        current = next((start for start, scale in calendar if scale == 1), None)
        ages = rates.get_age_limits(plancode)
        meta: List[tuple] = [
            (" ", " "),
            ("COI", f"Scale 1 (current from {current:%Y-%m-%d})" if current else "Scale 1 (current)"),
            ("GuarCOI", "Scale 0"),
            ("Prem Cease Age", ages["premium_cease"] if ages["premium_cease"] is not None else "Not loaded"),
            ("Ben Cease Age", ages["benefit_cease"] if ages["benefit_cease"] is not None else "Not loaded"),
        ]
        extra: Dict[str, Optional[list]] = {}
        extra["GINT"] = rates.get_gint(plancode)
        cvr_meta, extra["CVR"] = self._iswl_cash_value_column(cov_index)
        prem_meta, extra["Prem Rate"] = self._iswl_premium_rate_column(cov_index)
        meta += [(" ", " "), cvr_meta, prem_meta, (" ", " "), ("Loan rates", "RATE_LOAN")]
        for rate_type in ("PLNCRG", "PLNCRD", "RLNCRG", "RLNCRD"):
            values = rates.get_rates(rate_type, plancode)
            rate = values[1] if values and len(values) > 1 else None
            meta.append((f"  {rate_type}", f"{rate:g}%" if rate is not None else "Not loaded"))
        meta += [(" ", " "), ("Rider premiums", "See Fixed Premium")]
        return meta, extra

    def _iswl_cash_value_column(self, cov_index: int) -> Tuple[tuple, Optional[list]]:
        """Per-unit CVF value at each row's Date: Year n is duration n - 1."""
        if self.status.premium_pay_status_code.strip() in ("44", "45"):
            return ("CVR", "Not available on ETI/RPU"), None
        try:
            values = self.rates_wl_cv(cov_index)
        except (RatesError, ValueError) as exc:
            return ("CVR", f"Error: {exc}"), None
        if not values:
            return ("CVR", f"Not loaded (WL_RATE_CV {self.cov_cash_value_key(cov_index)})"), None
        last = max(values)
        column = [None] + [values.get(year - 1, "") for year in range(1, last + 2)]
        return ("CVR", f"WL_RATE_CV {self.cov_cash_value_key(cov_index)} at Date"), column

    def _iswl_premium_rate_column(self, cov_index: int) -> Tuple[tuple, Optional[list]]:
        """Annual base premium per unit (WL_RATE_PREM type N) through the pay age."""
        from ..fixed_premium_rates import _rate, premium_items

        try:
            base = premium_items(self, cov_index)[0]
        except (RatesError, ValueError) as exc:
            return ("Prem Rate", f"Error: {exc}"), None
        row = base.rate_row
        if row is None:
            return ("Prem Rate", base.reason), None
        pay_age, pay_use = row.get("PAY_AGE"), row.get("PAY_AGE_USE")
        issue_age = self.coverages.cov_issue_age(cov_index)
        if pay_age is None or pay_use not in (0, 1) or issue_age is None:
            return ("Prem Rate", f"Pay age {pay_age} (use {pay_use}) is not verified"), None
        years = pay_age - issue_age if pay_use == 1 else pay_age
        rate = _rate(row["RATE"])
        column = [None] + [rate] * max(years, 0)
        return ("Prem Rate", f"WL_RATE_PREM ** to {'age' if pay_use == 1 else 'year'} {pay_age}"), column

    def build_benefit_rate_matrix(self, ben_index: int, scale: int = 1) -> Optional[List[List]]:
        """
        Build rate matrix for a benefit, matching VBA LoadULBenefitRatesToRecordset.

        Returns a 2D list where:
          - Row 0 = column headers (RateFields, RateInfo, Date, Age, Year, COI)
          - Rows 1..N = data rows by policy year

        Args:
            ben_index: Benefit index (1-based)
            scale: Rate scale (default 1)

        Returns:
            2D list suitable for table display, or None if rates unavailable
        """
        # Benefits use Cov 1 for many params
        issue_date_cov1 = self.coverages.cov_issue_date(1)
        maturity_date_cov1 = self.coverages.cov_maturity_date(1)

        benefits = self.benefits.get_benefits()
        if ben_index < 1 or ben_index > len(benefits):
            return None
        ben = benefits[ben_index - 1]
        ben_iss_age = ben.issue_age
        ben_iss_date = ben.issue_date

        if issue_date_cov1 is None or ben_iss_age is None:
            return None

        # xmax based on cov 1 dates
        if maturity_date_cov1 and maturity_date_cov1 > issue_date_cov1:
            xmax = (maturity_date_cov1.year - issue_date_cov1.year)
        else:
            xmax = 100 - (self.coverages.cov_issue_age(1) or 30)

        # Get single-value rates
        mtp = self.rates_ben_mtp(ben_index)
        ctp = self.rates_ben_ctp(ben_index)

        # Get rate array
        ben_coi = self.rates_ben_coi(ben_index, scale)

        # Get sex/rateclass/band from Cov 1
        sex_code = self.renewal_cov_sex_code(1)
        sex_display = self._translate_sex_for_rates(sex_code)
        band = self.cov_band(1)
        band_display = band if band is not None else "Not Found"

        rate_fields = [
            " ", "Policy", "Ben Index", "Benefit Code", "Benefit",
            "IssueAge", "Sex", "Rateclass", "Band", "Scale",
            " ", "MTP", "CTP"
        ]

        rate_info = [
            " ", self.policy.policy_number, ben_index,
            ben.benefit_code,
            ben.benefit_type_cd,
            ben_iss_age, sex_display,
            self.renewal_cov_rateclass_by_cov(1),
            band_display, scale,
            " ", mtp if mtp else "", ctp if ctp else ""
        ]

        max_meta = max(len(rate_fields), len(rate_info))
        xmax = max(xmax, max_meta)

        columns = [
            MatrixColumn("RateFields", lambda row: metadata_value(rate_fields, row.index)),
            MatrixColumn("RateInfo", lambda row: metadata_value(rate_info, row.index)),
            MatrixColumn("Date", lambda row: row.date_text),
            MatrixColumn("Age", lambda row: row.age),
            MatrixColumn("Year", lambda row: row.year),
            MatrixColumn("COI", lambda row: rate_value_or_na(ben_coi, row.index)),
        ]
        return build_rate_matrix(
            columns,
            duration_rows(ben_iss_date or issue_date_cov1, ben_iss_age if ben_iss_age else None, xmax),
        )

    def build_policy_rate_matrix(self, scale: int = 1) -> Optional[List[List]]:
        """
        Build rate matrix for policy-level rates, matching VBA LoadULPolicyRatesToRecordset.

        Returns a 2D list where:
          - Row 0 = column headers (RateFields, RateInfo, Date, Year, AttainedAge, TPP, EPP, MFEE, CORR)
          - Rows 1..N = data rows by policy year

        Args:
            scale: Rate scale (default 1)

        Returns:
            2D list suitable for table display, or None if rates unavailable
        """
        issue_date = self.coverages.cov_issue_date(1)
        maturity_date = self.coverages.cov_maturity_date(1)
        issue_age = self.coverages.cov_issue_age(1)

        if issue_date is None or issue_age is None:
            return None

        if maturity_date and maturity_date > issue_date:
            xmax = (maturity_date.year - issue_date.year)
        else:
            xmax = 100 - issue_age

        # Get rate arrays
        tpp = self.rates_tpp(scale)
        epp = self.rates_epp(scale)
        mfee = self.rates_mfee(scale)
        corr = self.rates_corr()

        # Get sex/rateclass/band from Cov 1
        sex_code = self.renewal_cov_sex_code(1)
        sex_display = self._translate_sex_for_rates(sex_code)
        band = self.cov_band(1)
        band_display = band if band is not None else "Not Found"

        rate_fields = [
            " ", "Policy", "Product", "Plancode", "IssueDate",
            "IssueAge", "Sex", "Rateclass", "Band", "Scale"
        ]

        rate_info = [
            " ", self.policy.policy_number, self.product.product_type,
            self.coverages.cov_plancode(1),
            issue_date.strftime("%Y-%m-%d") if issue_date else "",
            issue_age, sex_display,
            self.renewal_cov_rateclass_by_cov(1),
            band_display, scale
        ]

        max_meta = max(len(rate_fields), len(rate_info))
        xmax = max(xmax, max_meta)

        columns = [
            MatrixColumn("RateFields", lambda row: metadata_value(rate_fields, row.index)),
            MatrixColumn("RateInfo", lambda row: metadata_value(rate_info, row.index)),
            MatrixColumn("Date", lambda row: row.date_text),
            MatrixColumn("Year", lambda row: row.year),
            MatrixColumn("AttainedAge", lambda row: row.age),
            MatrixColumn("TPP", lambda row: rate_value_or_na(tpp, row.index)),
            MatrixColumn("EPP", lambda row: rate_value_or_na(epp, row.index)),
            MatrixColumn("MFEE", lambda row: rate_value_or_na(mfee, row.index)),
            MatrixColumn("CORR", lambda row: rate_value_or_na(corr, row.index)),
        ]
        return build_rate_matrix(columns, duration_rows(issue_date, issue_age, xmax))
