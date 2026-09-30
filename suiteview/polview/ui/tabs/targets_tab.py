"""
Targets & Accumulators tab – Definition of Life Insurance, Accumulators,
TAMRA Values, Commission Target Premium, and Minimum Premium widgets.
"""

from typing import TYPE_CHECKING, Dict, List, Any

from PyQt6.QtWidgets import (
    QWidget, QGridLayout, QLabel,
)
from PyQt6.QtCore import Qt

from ..formatting import format_currency, format_date
from ..widgets import StyledInfoTableGroup
from . import targets_tooltips as tips
from ..styles import (
    BLUE_BG, GRAY_TEXT, GRAY_MID, WHITE,
    BLUE_PRIMARY, BLUE_DARK, GOLD_TEXT
)
from ...services.targets_view_model import build_targets_view_model

if TYPE_CHECKING:
    from ...models.policy_information import PolicyInformation


# ─── N/A interior background style ───────────────────────────────────────────
# Overrides just the background-color of the GroupBox interior to match the
# window background. Border, radius, and title pill remain identical.
_NA_GROUPBOX_STYLE = f"""
    QGroupBox {{
        font-size: 11px;
        font-weight: bold;
        color: {BLUE_DARK};
        border: 2px solid {BLUE_PRIMARY};
        border-radius: 8px;
        margin-top: 3px;
        margin-bottom: 0px;
        padding: 0px;
        background-color: {BLUE_BG};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 1px 10px;
        background-color: {BLUE_PRIMARY};
        color: {GOLD_TEXT};
        border-radius: 4px;
        left: 10px;
    }}
    QGroupBox QLabel {{
        font-size: 10px;
        color: {GRAY_TEXT};
        border: none;
        background: transparent;
    }}
"""

_NA_LABEL_STYLE = (
    f"color: {GRAY_TEXT}; font-size: 11px; font-style: italic; "
    "background: transparent; border: none;"
)

# Greyed-out "data not available" style — same border/pill shape but with
# muted grey tones to indicate no DB2 rows were found for this policy.
_UNAVAILABLE_GROUPBOX_STYLE = f"""
    QGroupBox {{
        font-size: 11px;
        font-weight: bold;
        color: {BLUE_DARK};
        border: 2px solid {GRAY_MID};
        border-radius: 8px;
        margin-top: 3px;
        margin-bottom: 0px;
        padding: 0px;
        background-color: {BLUE_BG};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 1px 10px;
        background-color: {GRAY_MID};
        color: {WHITE};
        border-radius: 4px;
        left: 10px;
    }}
    QGroupBox QLabel {{
        font-size: 10px;
        color: {GRAY_TEXT};
        border: none;
        background: transparent;
    }}
"""

_UNAVAILABLE_LABEL_STYLE = (
    f"color: {GRAY_TEXT}; font-size: 11px; font-style: italic; "
    "background: transparent; border: none;"
)


# ─── N/A-capable group base (used by TAMRA, Commission, MinPrem) ─────────────

class _NaCapableGroup(StyledInfoTableGroup):
    """
    Base class that adds two alternative display modes on top of
    StyledInfoTableGroup:

    set_not_applicable(True):
      - Green interior + 'Not applicable for this product'
        (product has no TAMRA/target data by design).

    set_data_unavailable(True):
      - Greyed-out interior + 'Data not available'
        (product should have data but none found in DB2 for this policy).

    Size never changes — the widget always occupies the same space.
    """

    def __init__(self, title: str, parent=None):
        super().__init__(title, columns=1, parent=parent)
        self._na_mode = False
        self._unavailable_mode = False
        self._build_na_label()
        self._build_unavailable_label()

    def _build_na_label(self):
        self._na_label = QLabel("Not applicable for this product", self)
        self._na_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._na_label.setWordWrap(True)
        self._na_label.setStyleSheet(_NA_LABEL_STYLE)
        self._na_label.hide()

    def _build_unavailable_label(self):
        self._unavailable_label = QLabel("Data not available", self)
        self._unavailable_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._unavailable_label.setWordWrap(True)
        self._unavailable_label.setStyleSheet(_UNAVAILABLE_LABEL_STYLE)
        self._unavailable_label.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._na_mode:
            self._position_na_label()
        elif self._unavailable_mode:
            self._position_unavailable_label()

    def _position_na_label(self):
        self._na_label.setGeometry(4, 20, self.width() - 8, self.height() - 24)

    def _position_unavailable_label(self):
        self._unavailable_label.setGeometry(4, 20, self.width() - 8, self.height() - 24)

    def _hide_normal_content(self, keep_visible=None):
        for child in self.findChildren(QWidget):
            if child is not keep_visible:
                child.hide()

    def _restore_normal_content(self):
        from ..styles import POLICY_INFO_FRAME_STYLE
        self.setStyleSheet(POLICY_INFO_FRAME_STYLE)
        self._na_label.hide()
        self._unavailable_label.hide()
        for child in self.findChildren(QWidget):
            if child is not self._na_label and child is not self._unavailable_label:
                child.show()
        if hasattr(self, 'table') and self.table is not None:
            self.table._data_table.verticalHeader().setVisible(False)

    def set_not_applicable(self, na: bool):
        self._na_mode = na
        self._unavailable_mode = False
        if na:
            self.setStyleSheet(_NA_GROUPBOX_STYLE)
            self._hide_normal_content(keep_visible=self._na_label)
            self._na_label.show()
            self._position_na_label()
        else:
            self._restore_normal_content()

    def set_data_unavailable(self, unavailable: bool):
        """Show a greyed-out 'Data not available' overlay when no DB2 rows found."""
        self._unavailable_mode = unavailable
        self._na_mode = False
        if unavailable:
            self.setStyleSheet(_UNAVAILABLE_GROUPBOX_STYLE)
            self._hide_normal_content(keep_visible=self._unavailable_label)
            self._unavailable_label.show()
            self._position_unavailable_label()
        else:
            self._restore_normal_content()


# ─── helper widgets ──────────────────────────────────────────────────────────


class DefinitionOfLifeInsuranceWidget(StyledInfoTableGroup):
    """Widget for Definition of Life Insurance section.

    - Non-advanced: shows only 'Guideline/CVAT: CVAT'; widget keeps full size.
    - Advanced GP:  TEFRA/DEFRA + GP-specific fields.
    - Advanced CVAT: TEFRA/DEFRA + Base NSP, Other NSP.
    """

    def __init__(self, parent=None):
        super().__init__("Definition of Life Insurance", columns=1, show_table=False, parent=parent)
        self._setup_fields()
        self.setMaximumWidth(250)

    def _setup_fields(self):
        self.add_field("TEFRA/DEFRA", "tefra_label", 130, 100)
        self.add_field("Guideline/CVAT", "guideline_label", 130, 100)
        self.add_field("GSP", "gsp_label", 130, 100)
        self.add_field("GLP", "glp_label", 130, 100)
        self.add_field("Accum GLP", "accum_glp_label", 130, 100)
        self.add_field("Corr Pct", "corr_pct_label", 130, 100)
        self.add_field("Prem paying years left", "prem_pay_years_label", 130, 100)
        self.add_field("MaxAnnualLevelQualPrem", "max_annual_label", 130, 100)
        self.add_field("MinQualifyingGLP", "min_qual_glp_label", 130, 100)
        self.add_field("Base NSP", "base_nsp_label", 130, 100)
        self.add_field("Other NSP", "other_nsp_label", 130, 100)

        self._gp_fields = [
            "gsp_label", "glp_label", "accum_glp_label", "corr_pct_label",
            "prem_pay_years_label", "max_annual_label", "min_qual_glp_label",
        ]
        self._cvat_fields = ["base_nsp_label", "other_nsp_label"]

    def _set_field_visibility(self, attr_name: str, visible: bool):
        if attr_name in self._fields:
            self._fields[attr_name].setVisible(visible)
        if hasattr(self, '_labels') and attr_name in self._labels:
            self._labels[attr_name].setVisible(visible)

    def load_data(self, data: Dict[str, Any]):
        is_advanced = data.get("is_advanced", True)

        if not is_advanced:
            # Show only Guideline/CVAT = CVAT; hide everything else.
            self._set_field_visibility("tefra_label", False)
            self._set_field_visibility("guideline_label", True)
            for field in self._gp_fields + self._cvat_fields:
                self._set_field_visibility(field, False)
            self.set_value("guideline_label", "CVAT")
            # Fix: constrain height to just the one visible row so the group
            # box doesn't expand to fill the grid cell.
            self.setFixedHeight(52)
            return

        # Advanced product — full display
        self._set_field_visibility("tefra_label", True)
        self._set_field_visibility("guideline_label", True)
        self.set_value("tefra_label", str(data.get("tefra_defra", "")))
        self.set_value("guideline_label", str(data.get("gpt_cvat", "")))

        gpt_cvat = str(data.get("gpt_cvat", "")).upper()
        is_gp = gpt_cvat in ("GP", "GPT")

        for field in self._gp_fields:
            self._set_field_visibility(field, is_gp)
        for field in self._cvat_fields:
            self._set_field_visibility(field, not is_gp)

        if is_gp:
            self.set_value("gsp_label", format_currency(data.get("gsp")))
            self.set_value("glp_label", format_currency(data.get("glp")))
            self.set_value("accum_glp_label", format_currency(data.get("accum_glp")))
            self.set_value("corr_pct_label", str(data.get("corr_pct", "")))
            self.set_value("prem_pay_years_label", str(data.get("prem_pay_years", "")))
            self.set_value("max_annual_label", format_currency(data.get("max_annual_level_qual_prem")))
            self.set_value("min_qual_glp_label", format_currency(data.get("min_qualifying_glp")))
            inputs = data.get("calc_inputs")
            self._fields["prem_pay_years_label"].setToolTip(
                tips.prem_pay_years_tip(inputs) if inputs else "")
            self._fields["max_annual_label"].setToolTip(
                tips.max_annual_level_qual_prem_tip(inputs, data.get("max_annual_level_qual_prem"))
                if inputs else "")
            self._fields["min_qual_glp_label"].setToolTip(
                tips.min_qualifying_glp_tip(inputs, data.get("min_qualifying_glp"))
                if inputs else "")
            # GP has 2 base rows + 7 GP-specific rows = 9 total visible rows
            self.setMaximumHeight(16777215)  # remove any previous fixed height
            self.setFixedHeight(210)
        else:
            self.set_value("base_nsp_label", format_currency(data.get("base_nsp")))
            other_nsp = data.get("other_nsp")
            self.set_value("other_nsp_label",
                           format_currency(other_nsp) if other_nsp is not None else "0.00")
            # CVAT has 2 base rows + 2 CVAT-specific rows = 4 total visible rows
            self.setMaximumHeight(16777215)  # remove any previous fixed height
            self.setFixedHeight(100)


class AccumulatorsWidget(StyledInfoTableGroup):
    """Widget for Accumulators section."""

    def __init__(self, parent=None):
        super().__init__("Accumulators", columns=1, show_table=False, parent=parent)
        self._setup_fields()
        self.setMaximumWidth(250)

    def _setup_fields(self):
        self.add_field("Premiums Paid", "premiums_paid_label", 100, 100)
        self.add_field("Reg Prem", "reg_prem_label", 100, 100)
        self.add_field("Additional Prem", "additional_prem_label", 100, 100)
        self.add_field("Prem YTD", "prem_ytd_label", 100, 100)
        self.add_field("Cost Basis", "cost_basis_label", 100, 100)
        self.add_field("Accum WDs", "accum_wds_label", 100, 100)
        # Calculated field — shown in italics to indicate it is derived,
        # not read directly from DB2.
        self.add_field("Prem Allowed by GPT", "prem_allowed_gpt_label", 130, 100)
        self._make_field_italic("prem_allowed_gpt_label")
        self.add_field("Guaranteed Cash Value", "gcv_label", 130, 100)
        self._make_field_italic("gcv_label")

    def _make_field_italic(self, attr_name: str):
        """Italicize a field's label and value to flag it as a calculated value."""
        if attr_name in self._labels:
            lbl = self._labels[attr_name]
            lbl.setStyleSheet(lbl.styleSheet() + " font-style: italic;")
        if attr_name in self._fields:
            val = self._fields[attr_name]
            val.setStyleSheet(val.styleSheet() + " font-style: italic;")

    def load_data(self, totals: Dict[str, Any]):
        self.set_value("premiums_paid_label", format_currency(totals.get("premiums_paid")))
        self.set_value("reg_prem_label", format_currency(totals.get("reg_prem")))
        self.set_value("additional_prem_label", format_currency(totals.get("additional_prem")))
        self.set_value("prem_ytd_label", format_currency(totals.get("prem_ytd")))
        self.set_value("cost_basis_label", format_currency(totals.get("cost_basis")))
        self.set_value("accum_wds_label", format_currency(totals.get("accum_wds")))
        self._fields["premiums_paid_label"].setToolTip(tips.premiums_paid_tip(
            totals.get("reg_prem"), totals.get("additional_prem"), totals.get("premiums_paid")))
        prem_allowed = totals.get("prem_allowed_gpt")
        self.set_value(
            "prem_allowed_gpt_label",
            prem_allowed if prem_allowed == "N/A" else format_currency(prem_allowed),
        )
        inputs = totals.get("prem_allowed_gpt_inputs")
        self._fields["prem_allowed_gpt_label"].setToolTip(
            tips.prem_allowed_gpt_tip(inputs, prem_allowed) if inputs else
            "N/A: not a guideline premium test (GPT) policy, or its GPT values could not be read.")
        gcv = totals.get("gcv") or {}
        value = gcv.get("value")
        text = "N/A"
        if value is not None:
            nsp = any(d["basis"] == "NSP" for d in gcv.get("details", []))
            text = format_currency(value) + (" (NSP)" if nsp else "")
        self.set_value("gcv_label", text)
        if "gcv_label" in self._fields:
            self._fields["gcv_label"].setToolTip(self._gcv_tooltip(gcv))

    @staticmethod
    def _gcv_tooltip(gcv: Dict[str, Any]) -> str:
        lines = ["Interpolated from the stored 02-segment CV rates (NSP rates when on "
                 "nonforfeiture):",
                 "units x (BOY rate x months remaining + EOY rate x months elapsed) / 12"]
        as_of = gcv.get("as_of")
        if as_of:
            lines.append(f"As of {format_date(as_of)}")
        for d in gcv.get("details", []):
            basis = d["basis"] + (f" ({d['nonforfeiture']})" if d["nonforfeiture"] else "")
            lines.append(
                f"Cov {d.get('cov_pha_nbr') or d['cov_index']} {basis}: "
                f"dur {d['duration']} {d['boy_rate']:,.2f} -> "
                f"dur {d['duration'] + 1} {d['eoy_rate']:,.2f}, {d['months']} mo, "
                f"{d['units']:,} units = {d['value']:,.2f}"
            )
        if any(d["basis"] == "NSP" for d in gcv.get("details", [])):
            lines.append("NSP-basis value is not reconciled to a CyberLife nonforfeiture quote.")
        if gcv.get("reason"):
            lines.append(gcv["reason"])
        return "\n".join(lines)


class TamraValuesWidget(_NaCapableGroup):
    """Widget for TAMRA Values section using the hybrid StyledInfoTableGroup."""

    def __init__(self, parent=None):
        # Call _NaCapableGroup.__init__ which will call StyledInfoTableGroup.__init__
        # with show_table=True (default), then we add our extra fields.
        super().__init__("TAMRA Values", parent=parent)
        self._setup_fields()
        self.setMaximumWidth(250)

    def _setup_fields(self):
        self.add_field("7 Pay Prem", "seven_pay_prem_label", 90, 70)
        self.add_field("7 Pay Start Date", "seven_pay_start_label", 90, 70)
        self.add_field("7 Pay Start AV", "seven_pay_av_label", 90, 70)
        self.add_field("1035 Payments", "payments_1035_label", 90, 70)

        self.setup_table(["Year", "Premium", "Withdrawal"])

        self.mec_label = QLabel("")
        self.mec_label.setStyleSheet(
            "font-weight: bold; color: red; background: transparent; border: none;"
        )
        self.layout().insertWidget(1, self.mec_label)

    def load_data(self, tamra_per: Dict[str, Any], tamra_yr_list: List[Dict[str, Any]]):
        if not tamra_per:
            # No TAMRA data found — show green 'not available' state
            self._na_label.setText("Not available for this policy")
            self.set_not_applicable(True)
            return

        # Data found — restore normal display
        self.set_not_applicable(False)
        self.setVisible(True)

        self.set_value("seven_pay_prem_label", format_currency(tamra_per.get("SVPY_LVL_PRM_AMT")))
        self.set_value("seven_pay_start_label", format_date(tamra_per.get("SVPY_PER_STR_DT")))

        av_val = tamra_per.get("SVPY_BEG_CSV_AMT")
        if av_val is None or str(av_val).strip() in ("", "None"):
            self.set_value("seven_pay_av_label", "Null")
        else:
            self.set_value("seven_pay_av_label", format_currency(av_val))

        count_1035 = tamra_per.get("XCG_1035_PMT_QTY", tamra_per.get("SVPY_1035_PMT_CNT", "0"))
        self.set_value("payments_1035_label", str(count_1035 or "0"))

        mec_ind = str(tamra_per.get("MEC_STA_CD", tamra_per.get("MEC_IND", ""))).strip()
        if mec_ind.upper() in ("Y", "1"):
            self.mec_label.setText("Policy is a MEC.")
        else:
            self.mec_label.setText("Plan is subject to the 7-pay test" if tamra_per else "")

        rows = []
        for yr_data in tamra_yr_list:
            seq = yr_data.get("SVPY_YR_NBR", len(rows) + 1)
            premium = format_currency(yr_data.get("SVPY_PRM_PAY_AMT"))
            withdrawal = format_currency(yr_data.get("SVPY_WTD_AMT"))
            rows.append([str(seq), premium, withdrawal])
        self.load_table_data(rows)


class MinimumPremiumWidget(_NaCapableGroup):
    """Widget for Minimum Premium section."""

    def __init__(self, parent=None):
        super().__init__("Minimum Premium", parent=parent)
        self.setMinimumWidth(300)
        self._setup_section_fields()

    def _setup_section_fields(self):
        self.add_field("Annual Min", "annual_min_label", 70, 70)
        self.add_field("Monthly Min", "monthly_min_label", 70, 70)
        self.add_field("Accum Min", "accum_min_label", 70, 70)
        self.add_field("MAP Date", "map_date_label", 70, 80)
        self.setup_table(["Phs", "CovType", "Face", "Target", "Rate"])

    def load_data(self, pol_targets: List[Dict[str, Any]],
                  cov_data: List[Dict[str, Any]] = None,
                  rnl_data: List[Dict[str, Any]] = None):
        cov_data = cov_data or []
        rnl_data = rnl_data or []

        mtp_monthly = 0.0
        mt_amounts = []
        accum_mtp = 0
        map_date = ""

        for pt in pol_targets:
            tar_typ = str(pt.get("TAR_TYP_CD", "")).strip()
            tar_amt = pt.get("TAR_PRM_AMT", 0) or 0
            tar_dt = pt.get("TAR_DT", "")
            if tar_typ == "MT":
                mtp_monthly += float(tar_amt)
                mt_amounts.append(float(tar_amt))
            elif tar_typ == "MA":
                accum_mtp = tar_amt
                map_date = tar_dt

        face_by_cov: Dict = {}
        units_by_cov: Dict = {}
        plancode_by_cov: Dict = {}
        base_plancode = None
        for cov in cov_data:
            cov_phs = cov.get("COV_PHA_NBR")
            units = float(cov.get("COV_UNT_QTY", 0) or 0)
            vpu = float(cov.get("COV_VPU_AMT", 0) or 0)
            face_by_cov[cov_phs] = units * vpu
            units_by_cov[cov_phs] = (units, vpu)
            plancode = str(cov.get("PLN_DES_SER_CD", "")).strip()
            plancode_by_cov[cov_phs] = plancode
            if base_plancode is None:
                base_plancode = plancode

        rate_by_cov: Dict = {}
        for rnl in rnl_data:
            if str(rnl.get("PRM_RT_TYP_CD", "")).strip() == "M":
                cov_phs = rnl.get("COV_PHA_NBR")
                rate_by_cov[cov_phs] = rnl.get("RNL_RT", 0) or 0

        table_rows = []
        cell_tips = []
        for cov in cov_data:
            cov_phs = cov.get("COV_PHA_NBR", "")
            face = face_by_cov.get(cov_phs, 0)
            plancode = plancode_by_cov.get(cov_phs, "")
            cov_type = "BASE" if plancode == base_plancode else "RIDER"
            rate = rate_by_cov.get(cov_phs)
            if rate:
                rate_display = f"{float(rate)/1000:.3f}"
                target = face / 1000 * float(rate) / 1000
                target_display = format_currency(target)
                target_tip = tips.rate_target_tip(face, rate, target, "Target")
            else:
                rate_display = ""
                target_display = ""
                target_tip = ""
            table_rows.append([str(cov_phs), cov_type, format_currency(face),
                                target_display, rate_display])
            cell_tips.append((tips.face_tip(*units_by_cov.get(cov_phs, (0.0, 0.0)), face), target_tip))

        annual_min = mtp_monthly * 12 if mtp_monthly else 0
        self.set_value("annual_min_label", format_currency(annual_min))
        self.set_value("monthly_min_label", format_currency(mtp_monthly))
        self.set_value("accum_min_label", format_currency(accum_mtp))
        self.set_value("map_date_label", format_date(map_date))
        self._fields["annual_min_label"].setToolTip(tips.annual_min_tip(mtp_monthly, annual_min))
        self._fields["monthly_min_label"].setToolTip(tips.monthly_min_tip(mt_amounts))
        self.load_table_data(table_rows)
        for row, (face_tip, target_tip) in enumerate(cell_tips):
            self.table.item(row, 2).setToolTip(face_tip)
            self.table.item(row, 3).setToolTip(target_tip)


class CommissionTargetWidget(_NaCapableGroup):
    """Widget for Commission Target section."""

    def __init__(self, parent=None):
        super().__init__("Commission Target Premium", parent=parent)
        self.setMinimumWidth(300)
        self._setup_section_fields()

    def _setup_section_fields(self):
        self.add_field("Commission Target", "target_label", 110, 80)
        self.setup_table(["Phs", "Face", "Target", "Date", "Rate"])

    def load_data(self, com_targets: List[Dict[str, Any]],
                  cov_data: List[Dict[str, Any]],
                  rnl_data: List[Dict[str, Any]]):
        ctp_total = 0.0
        ct_records = []
        for ct in com_targets:
            tar_typ = str(ct.get("TAR_TYP_CD", "")).strip()
            if tar_typ == "CT":
                tar_amt = ct.get("TAR_PRM_AMT", 0) or 0
                ctp_total += float(tar_amt)
                ct_records.append(ct)

        self.set_value("target_label", format_currency(ctp_total))
        self._fields["target_label"].setToolTip(tips.commission_target_tip(
            (float(ct.get("TAR_PRM_AMT", 0) or 0) for ct in ct_records), ctp_total))

        face_by_cov: Dict = {}
        units_by_cov: Dict = {}
        for cov in cov_data:
            cov_phs = cov.get("COV_PHA_NBR")
            units = float(cov.get("COV_UNT_QTY", 0) or 0)
            vpu = float(cov.get("COV_VPU_AMT", 0) or 0)
            face_by_cov[cov_phs] = units * vpu
            units_by_cov[cov_phs] = (units, vpu)

        rate_by_cov: Dict = {}
        for rnl in rnl_data:
            if str(rnl.get("PRM_RT_TYP_CD", "")).strip() == "T":
                cov_phs = rnl.get("COV_PHA_NBR")
                rate_by_cov[cov_phs] = rnl.get("RNL_RT", 0)

        rows = []
        face_tips = []
        for ct in ct_records:
            cov_phs = ct.get("AGT_COM_PHA_NBR", "")
            face = face_by_cov.get(cov_phs, 0)
            rate = rate_by_cov.get(cov_phs, "")
            if rate:
                rate_display = f"{float(rate)/1000:.3f}"
                shown = face / 1000 * float(rate) / 1000
                face_display = format_currency(shown)
                face_tips.append(tips.rate_target_tip(face, rate, shown, "Shown value"))
            else:
                rate_display = ""
                face_display = format_currency(face)
                face_tips.append(
                    tips.face_tip(*units_by_cov[cov_phs], face) if cov_phs in units_by_cov else "")
            rows.append([
                str(cov_phs),
                face_display,
                format_currency(ct.get("TAR_PRM_AMT")),
                format_date(ct.get("TAR_DT")),
                rate_display,
            ])
        self.load_table_data(rows)
        for row, tip in enumerate(face_tips):
            self.table.item(row, 1).setToolTip(tip)


# ─── main tab ────────────────────────────────────────────────────────────────


class TargetsAccumulatorsTab(QWidget):
    """Tab for Targets & Accumulators view."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QGridLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setHorizontalSpacing(4)
        layout.setVerticalSpacing(4)

        # Row 0
        self.doli_widget = DefinitionOfLifeInsuranceWidget()
        layout.addWidget(self.doli_widget, 0, 0,
                         Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self.accum_widget = AccumulatorsWidget()
        self.accum_widget.setTitle("Accumulators ⓘ")
        self.accum_widget.setToolTip(
            "Accumulators come from the LH_POL_TOTALS table and, in a few cases, "
            "may not match the sum of transaction history on the Activity tab."
        )
        layout.addWidget(self.accum_widget, 0, 1,
                         Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        # Row 1 — three expandable bottom widgets
        self.tamra_widget = TamraValuesWidget()
        self.tamra_widget.setMinimumHeight(200)
        layout.addWidget(self.tamra_widget, 1, 0)

        self.commission_widget = CommissionTargetWidget()
        self.commission_widget.setMinimumHeight(200)
        layout.addWidget(self.commission_widget, 1, 1)

        self.min_prem_widget = MinimumPremiumWidget()
        self.min_prem_widget.setMinimumHeight(200)
        layout.addWidget(self.min_prem_widget, 1, 2)
        self._grid = layout

        layout.setRowStretch(1, 1)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 1)
        layout.setColumnStretch(3, 1)

    def _compact_when_empty(self, widget, empty: bool, message: str = ""):
        """Empty/not-applicable panels stay visible and greyed, but only as tall as their note."""
        if empty:
            widget.setMinimumHeight(64)
            widget.setMaximumHeight(64)
            self._grid.setAlignment(widget, Qt.AlignmentFlag.AlignTop)
            if message:
                widget._unavailable_label.setText(message)
        else:
            widget.setMaximumHeight(16777215)
            widget.setMinimumHeight(200)
            self._grid.setAlignment(widget, Qt.AlignmentFlag(0))

    def load_data_from_policy(self, policy: 'PolicyInformation'):
        """Load all data for this tab using PolicyInformation."""
        try:
            view_model = build_targets_view_model(policy)
            self.doli_widget.load_data(view_model.doli_data)
            self.accum_widget.load_data(view_model.accum_data)
            self.tamra_widget.load_data(view_model.tamra_period, view_model.tamra_years)
            self.commission_widget.set_not_applicable(not view_model.is_advanced)
            self.min_prem_widget.set_not_applicable(not view_model.is_advanced)

            if view_model.is_advanced:
                self.commission_widget.set_data_unavailable(view_model.commission_unavailable)
                self.min_prem_widget.set_data_unavailable(view_model.minimum_premium_unavailable)
                self._compact_when_empty(
                    self.commission_widget, view_model.commission_unavailable,
                    "No commission target rows (LH_COM_TARGET) for this policy")
                self._compact_when_empty(
                    self.min_prem_widget, view_model.minimum_premium_unavailable,
                    "No minimum premium target rows (LH_POL_TARGET) for this policy")
            else:
                self._compact_when_empty(self.commission_widget, True)
                self._compact_when_empty(self.min_prem_widget, True)

            self.commission_widget.load_data(
                view_model.commission_targets, view_model.coverages, view_model.renewal_rates)
            self.min_prem_widget.load_data(
                view_model.policy_targets, view_model.coverages, view_model.renewal_rates)

        except Exception:
            import traceback
            traceback.print_exc()
            raise
