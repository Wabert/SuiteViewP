"""Joint survivor (second-to-die) UL rates for PolicyInformation's rates section.

The 12 company-26 FFL joint plans have no base COI: CyberLife charges the
blended VP/MS JSURVCOI rate of both insureds. These read both insureds, their
extras and CyberLife's stored rate by coverage, and build PolView's joint rate
view (``suiteview.core.joint_survivor_coi`` does the calculation).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from suiteview.core.joint_survivor_coi import (
    VPMS_UNAVAILABLE_TEXT, Insured, JointSurvivorError, JointSurvivorRates, Rating,
    anniversary_year, calculate_joint_survivor_rates, rate_sex, ymd,
)


class JointSurvivorMixin:
    """Mixed into RatesSection; relies on its sections and ``_get_rates``."""
    def cov_is_joint_survivor(self, cov_index: int) -> bool:
        """Joint survivor UL: phase NBR_OF_LIVES_CD '3' and rates.PLAN_ATTR LIVES '3'.

        Only lives-3 phases query PLAN_ATTR, so ordinary UL rate views never
        depend on schema ``rates``. A lives-3 phase whose plan is not defined
        as joint in PLAN_ATTR keeps the ordinary (single-life) view.
        """
        if not self.product.is_advanced_product:
            return False
        covs = self.coverages.get_coverages()
        if not 0 < cov_index <= len(covs) or covs[cov_index - 1].number_of_lives_code != "3":
            return False
        rates = self._get_rates()
        if rates is None:
            raise RuntimeError("The shared rates service is not available.")
        plancode = covs[cov_index - 1].plancode
        return rates.get_plan_attributes(self.policy.company_code, plancode).get("LIVES") == "3"

    def _cov_joint_renewal_row(self, cov_index: int, joint_ind: str) -> Dict[str, Any]:
        """The phase's single type-C LH_COV_INS_RNL_RT row for JT_INS_IND 0 or 1."""
        phase = self.coverages.get_coverages()[cov_index - 1].cov_pha_nbr
        rows = [
            row for row in self.fetch_table("LH_COV_INS_RNL_RT")
            if int(row.get("COV_PHA_NBR") or 0) == phase
            and str(row.get("PRM_RT_TYP_CD") or "").strip() == "C"
            and str(row.get("JT_INS_IND") or "").strip() == joint_ind
        ]
        if len(rows) != 1:
            raise JointSurvivorError(
                f"Coverage phase {phase}: expected one type C renewal rate row with "
                f"JT_INS_IND {joint_ind}, found {len(rows)}"
            )
        return rows[0]

    def cov_joint_insureds(self, cov_index: int) -> Tuple[Insured, Insured]:
        """(primary person 00, joint person 01) rate keys for a joint phase.

        Sex/class come from the type C renewal rows (JT_INS_IND 0/1); issue ages
        from LH_COV_PHA INS_ISS_AGE / JNT_ISU_ISS_AGE.
        """
        cov = self.coverages.get_coverages()[cov_index - 1]
        if cov.issue_age is None or cov.joint_issue_age is None:
            raise JointSurvivorError(
                f"Coverage phase {cov.cov_pha_nbr}: missing INS_ISS_AGE or JNT_ISU_ISS_AGE"
            )
        lives = []
        for joint_ind, age in (("0", cov.issue_age), ("1", cov.joint_issue_age)):
            row = self._cov_joint_renewal_row(cov_index, joint_ind)
            rate_class = str(row.get("RT_CLS_CD") or "").strip()
            if not rate_class:
                raise JointSurvivorError(
                    f"Coverage phase {cov.cov_pha_nbr}: blank RT_CLS_CD for JT_INS_IND {joint_ind}"
                )
            lives.append(Insured(rate_sex(str(row.get("RT_SEX_CD") or "")), rate_class, age))
        return lives[0], lives[1]

    def cov_joint_stored_coi(self, cov_index: int) -> Optional[float]:
        """CyberLife's blended current monthly COI per $1,000 (JT_INS_IND 0 RNL_RT / 100000)."""
        raw = self._cov_joint_renewal_row(cov_index, "0").get("RNL_RT")
        if raw is None:
            return None
        return float(Decimal(str(raw)) / Decimal(100000))

    @staticmethod
    def _joint_ymd(value) -> int:
        """YYYYMMDD for the model's f_anniversary; a blank date is 9999-12-31."""
        if value is None or (isinstance(value, str) and not value.strip()):
            return 99991231
        if isinstance(value, date):
            return ymd(value)
        try:
            return ymd(date.fromisoformat(str(value).strip()[:10]))
        except ValueError as exc:
            raise JointSurvivorError(f"Unreadable extra-rating date {value!r}") from exc

    def cov_joint_ratings(self, cov_index: int) -> List[Rating]:
        """LH_SST_XTR_CRG extras on the phase in the model's terms (per insured PRS_CD)."""
        cov = self.coverages.get_coverages()[cov_index - 1]
        if cov.issue_date is None:
            raise JointSurvivorError(f"Coverage phase {cov.cov_pha_nbr}: missing ISSUE_DT")
        issue_ymd = ymd(cov.issue_date)
        ratings = []
        for row in self.fetch_table("LH_SST_XTR_CRG"):
            if int(row.get("COV_PHA_NBR") or 0) != cov.cov_pha_nbr:
                continue
            person = str(row.get("PRS_CD") or "").strip()
            type_code = str(row.get("SST_XTR_TYP_CD") or "").strip()
            if person not in ("00", "01"):
                raise JointSurvivorError(
                    f"Coverage phase {cov.cov_pha_nbr}: extra rating for person {person!r}"
                )
            if type_code not in ("0", "1", "2", "3", "4"):
                raise JointSurvivorError(
                    f"Coverage phase {cov.cov_pha_nbr}: unsupported extra type {type_code!r}"
                )
            ratings.append(Rating(
                person=person,
                type_code=type_code,
                table_code=str(row.get("SST_XTR_RT_TBL_CD") or "").strip(),
                percent=float(row.get("SST_XTR_PCT") or 0) * 100,
                flat_per_1000=float(row.get("XTR_PER_1000_AMT") or 0),
                effective_year=anniversary_year(self._joint_ymd(row.get("SST_XTR_EFF_DT")), issue_ymd),
                cease_year=anniversary_year(self._joint_ymd(row.get("SST_XTR_CEA_DT")), issue_ymd),
            ))
        return ratings

    def rates_joint_survivor(self, cov_index: int, as_of: Optional[date] = None) -> JointSurvivorRates:
        """Blended joint COI for a joint survivor phase, compared with CyberLife.

        ``as_of`` defaults to the valuation date (last processed monthliversary),
        so the compared policy year is the one CyberLife has rated.
        """
        cov = self.coverages.get_coverages()[cov_index - 1]
        if cov.issue_date is None:
            raise JointSurvivorError(f"Coverage phase {cov.cov_pha_nbr}: missing ISSUE_DT")
        rates = self._get_rates()
        if rates is None:
            raise RuntimeError("The shared rates service is not available.")
        primary, joint = self.cov_joint_insureds(cov_index)
        return calculate_joint_survivor_rates(
            rates, self.policy.company_code, cov.plancode, cov.issue_date, primary, joint,
            self.cov_joint_ratings(cov_index), as_of or self.values.valuation_date or date.today(),
            self.cov_joint_stored_coi(cov_index),
        )

    def joint_survivor_fields(self, cov_index: int, js: JointSurvivorRates) -> List[Tuple[str, Any]]:
        """Joint metadata rows (lives, rules, CyberLife check, VP/MS targets) for the rate grids."""
        cov = self.coverages.get_coverages()[cov_index - 1]
        attrs = js.attributes

        def life_text(life: Insured) -> str:
            return f"{life.sex} / class {life.rate_class} / age {life.issue_age}"

        def extras_text(person: str) -> str:
            return "; ".join(r.description for r in js.ratings_for(person)) or "None"

        calculated = js.calculated_current
        fields: List[Tuple[str, Any]] = [
            ("Lives", "3 - Joint survivor (second-to-die)"),
            ("Primary (00)", life_text(js.primary)), ("  Extras 00", extras_text("00")),
            ("Joint (01)", life_text(js.joint)), ("  Extras 01", extras_text("01")),
            ("Joint Mort Tbl", cov.joint_mortality_table_code or "(blank)"),
            (" ", " "),
            ("Base COI", "Not IAF: see JointCOI (VP/MS)"),
            ("Method C / G", f"{attrs.get('JS_METHOD_C', '')} / {attrs.get('JS_METHOD_G', '')}"),
            ("Sex basis", attrs.get("JS_SEX_BASIS", "")),
            ("Cap curr at guar", "Y" if js.rules.cap_curr_at_guar else "N"),
            ("Zero guar at q=1", "Y" if js.rules.zero_guar_at_q1 else "N"),
            ("Zero curr at q=0", "Y" if js.rules.zero_curr_at_q0 else "N"),
            ("Flat factor", js.rules.flat_factor),
            ("Horizon", f"{js.horizon} years ({js.horizon_note})"),
            (" ", " "),
            ("As of", js.as_of.strftime("%Y-%m-%d")),
            ("Policy year", js.policy_year),
            ("CyberLife RNL_RT", f"{js.stored_rate:.5f}" if js.stored_rate is not None else "NULL"),
            ("Calculated", f"{calculated:.5f}" if calculated is not None else "N/A"),
            ("Check", js.comparison_text),
            (" ", " "),
        ]
        unavailable = js.vpms_unavailable
        if unavailable is None:
            fields.append(("Targets / SCR", "VP/MS target availability unknown for this plan"))
        else:
            fields.extend((rate_type, VPMS_UNAVAILABLE_TEXT) for rate_type in unavailable)
        fields.extend([
            (" ", " "),
            ("Source", "UL_Rates rates JS_Q + PLAN_ATTR"),
            ("COI units", "Monthly per $1,000; JS_Q annual q per $1"),
        ])
        return fields

    def build_joint_survivor_rate_matrix(self, cov_index: int) -> List[List]:
        """Legacy-view joint survivor grid: both insureds' JS_Q and the blended joint COI.

        Columns follow the other rate matrices (metadata in RateFields/RateInfo,
        one row per policy year). ``CyberLife`` / ``Check`` are populated only on
        the current policy year row, which the UI highlights.
        """
        from dateutil.relativedelta import relativedelta

        cov = self.coverages.get_coverages()[cov_index - 1]
        js = self.rates_joint_survivor(cov_index)
        fields: List[Tuple[str, Any]] = [
            (" ", " "),
            ("Policy", self.policy.policy_number), ("Cov Index", cov_index),
            ("Phase", cov.cov_pha_nbr), ("Plancode", js.plancode),
            ("Description", js.plan_description),
            ("IssueDate", js.issue_date.strftime("%Y-%m-%d")),
            *self.joint_survivor_fields(cov_index, js),
        ]

        rated = bool(js.ratings)
        columns = ["RateFields", "RateInfo", "Date", "Year", "Age 00", "Age 01",
                   "JS_Q 00 C", "JS_Q 01 C", "JS_Q 00 G", "JS_Q 01 G"]
        if rated:
            columns += ["Rated q 00 C", "Rated q 01 C", "Rated q 00 G", "Rated q 01 G"]
        columns += ["JointCOI", "GuarJointCOI", "CyberLife", "Check"]

        (qx_c, qy_c), (qx_g, qy_g) = js.js_q["C"], js.js_q["G"]
        matrix: List[List] = [columns]
        for row in range(1, max(js.horizon, len(fields) - 1) + 1):
            label, info = fields[row] if row < len(fields) else ("", "")
            values: List[Any] = [label, info]
            if row <= js.horizon:
                t = row - 1
                values += [
                    (js.issue_date + relativedelta(years=t)).strftime("%m/%d/%Y"), row,
                    js.primary.issue_age + t, js.joint.issue_age + t,
                    qx_c[t], qy_c[t], qx_g[t], qy_g[t],
                ]
                if rated:
                    cy, gy = js.schedule.current_years[t], js.schedule.guaranteed_years[t]
                    # Display-only rounding of float noise (e.g. 0.0372626999999…).
                    values += [round(q, 9) for q in (cy.qx, cy.qy, gy.qx, gy.qy)]
                values += [js.schedule.current[t], js.schedule.guaranteed[t]]
                if row == js.policy_year:
                    values += [js.stored_rate if js.stored_rate is not None else "NULL",
                               js.comparison_text]
                else:
                    values += ["", ""]
            else:
                values += [""] * (len(columns) - 2)
            matrix.append(values)
        return matrix

