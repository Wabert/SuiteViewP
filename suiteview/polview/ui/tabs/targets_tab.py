"""
Targets & Accumulators tab – Definition of Life Insurance, Accumulators,
TAMRA Values, Commission Target Premium, and Minimum Premium widgets.
"""

from typing import TYPE_CHECKING, Dict, List, Any

from PyQt6.QtWidgets import (
    QWidget, QGridLayout, QLabel, QVBoxLayout, QSizePolicy, QStackedWidget
)
from PyQt6.QtCore import Qt

from suiteview.core.db2_connection import DB2Connection
from ..formatting import format_currency, format_date
from ..widgets import StyledInfoTableGroup
from ..styles import (
    BLUE_BG, GRAY_TEXT, GRAY_MID, WHITE,
    BLUE_PRIMARY, BLUE_DARK, BLUE_GRADIENT_TOP, BLUE_GRADIENT_BOT,
    GOLD_TEXT, GOLD_PRIMARY
)

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

    def load_data(self, totals: Dict[str, Any]):
        self.set_value("premiums_paid_label", format_currency(totals.get("premiums_paid")))
        self.set_value("reg_prem_label", format_currency(totals.get("reg_prem")))
        self.set_value("additional_prem_label", format_currency(totals.get("additional_prem")))
        self.set_value("prem_ytd_label", format_currency(totals.get("prem_ytd")))
        self.set_value("cost_basis_label", format_currency(totals.get("cost_basis")))
        self.set_value("accum_wds_label", format_currency(totals.get("accum_wds")))


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
        accum_mtp = 0
        map_date = ""

        for pt in pol_targets:
            tar_typ = str(pt.get("TAR_TYP_CD", "")).strip()
            tar_amt = pt.get("TAR_PRM_AMT", 0) or 0
            tar_dt = pt.get("TAR_DT", "")
            if tar_typ == "MT":
                mtp_monthly += float(tar_amt)
            elif tar_typ == "MA":
                accum_mtp = tar_amt
                map_date = tar_dt

        face_by_cov: Dict = {}
        plancode_by_cov: Dict = {}
        base_plancode = None
        for cov in cov_data:
            cov_phs = cov.get("COV_PHA_NBR")
            units = float(cov.get("COV_UNT_QTY", 0) or 0)
            vpu = float(cov.get("COV_VPU_AMT", 0) or 0)
            face_by_cov[cov_phs] = units * vpu
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
        for cov in cov_data:
            cov_phs = cov.get("COV_PHA_NBR", "")
            face = face_by_cov.get(cov_phs, 0)
            plancode = plancode_by_cov.get(cov_phs, "")
            cov_type = "BASE" if plancode == base_plancode else "RIDER"
            rate = rate_by_cov.get(cov_phs)
            if rate:
                rate_display = f"{float(rate)/1000:.3f}"
                target_display = format_currency(face / 1000 * float(rate) / 1000)
            else:
                rate_display = ""
                target_display = ""
            table_rows.append([str(cov_phs), cov_type, format_currency(face),
                                target_display, rate_display])

        annual_min = mtp_monthly * 12 if mtp_monthly else 0
        self.set_value("annual_min_label", format_currency(annual_min))
        self.set_value("monthly_min_label", format_currency(mtp_monthly))
        self.set_value("accum_min_label", format_currency(accum_mtp))
        self.set_value("map_date_label", format_date(map_date))
        self.load_table_data(table_rows)


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

        face_by_cov: Dict = {}
        for cov in cov_data:
            cov_phs = cov.get("COV_PHA_NBR")
            units = float(cov.get("COV_UNT_QTY", 0) or 0)
            vpu = float(cov.get("COV_VPU_AMT", 0) or 0)
            face_by_cov[cov_phs] = units * vpu

        rate_by_cov: Dict = {}
        for rnl in rnl_data:
            if str(rnl.get("PRM_RT_TYP_CD", "")).strip() == "T":
                cov_phs = rnl.get("COV_PHA_NBR")
                rate_by_cov[cov_phs] = rnl.get("RNL_RT", 0)

        rows = []
        for ct in ct_records:
            cov_phs = ct.get("AGT_COM_PHA_NBR", "")
            face = face_by_cov.get(cov_phs, 0)
            rate = rate_by_cov.get(cov_phs, "")
            if rate:
                rate_display = f"{float(rate)/1000:.3f}"
                face_display = format_currency(face / 1000 * float(rate) / 1000)
            else:
                rate_display = ""
                face_display = format_currency(face)
            rows.append([
                str(cov_phs),
                face_display,
                format_currency(ct.get("TAR_PRM_AMT")),
                format_date(ct.get("TAR_DT")),
                rate_display,
            ])
        self.load_table_data(rows)


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
        layout.addWidget(self.accum_widget, 0, 1,
                         Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        note_label = QLabel(
            "<-- Accumulators come from LH_POL_TOTALS table and in a few cases "
            "may not match the sum of transaction history on the Activity sheet"
        )
        note_label.setWordWrap(True)
        note_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(note_label, 0, 2,
                         Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        # Row 1 — fixed height for all three bottom widgets
        bottom_row_height = 320

        self.tamra_widget = TamraValuesWidget()
        self.tamra_widget.setFixedHeight(bottom_row_height)
        layout.addWidget(self.tamra_widget, 1, 0,
                         Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self.commission_widget = CommissionTargetWidget()
        self.commission_widget.setFixedHeight(bottom_row_height)
        layout.addWidget(self.commission_widget, 1, 1, Qt.AlignmentFlag.AlignTop)

        self.min_prem_widget = MinimumPremiumWidget()
        self.min_prem_widget.setFixedHeight(bottom_row_height)
        layout.addWidget(self.min_prem_widget, 1, 2, Qt.AlignmentFlag.AlignTop)

        layout.setRowStretch(2, 1)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 1)
        layout.setColumnStretch(3, 1)

    # TODO: Dead code – never called; main_window uses load_data_from_policy() exclusively.
    def load_data(self, db: DB2Connection, where_clause: str):
        """Load all data for this tab using direct DB2 queries."""
        try:
            cols, rows = db.execute_query_with_headers(
                f"SELECT * FROM DB2TAB.LH_BAS_POL WHERE {where_clause}"
            )
            bas_pol = dict(zip(cols, rows[0])) if rows else {}
            is_advanced = str(bas_pol.get("NON_TRD_POL_IND", "")) == "1"

            if is_advanced:
                non_trd = {}
                try:
                    cols2, rows2 = db.execute_query_with_headers(
                        f"SELECT * FROM DB2TAB.LH_NON_TRD_POL WHERE {where_clause}"
                    )
                    non_trd = dict(zip(cols2, rows2[0])) if rows2 else {}
                except Exception:
                    pass

                gdl_prm = []
                try:
                    cols2, rows2 = db.execute_query_with_headers(
                        f"SELECT * FROM DB2TAB.LH_COV_INS_GDL_PRM WHERE {where_clause}"
                    )
                    gdl_prm = [dict(zip(cols2, r)) for r in rows2] if rows2 else []
                except Exception:
                    pass

                gsp_val = None
                glp_val = None
                for gp in gdl_prm:
                    typ = str(gp.get("PRM_RT_TYP_CD", "")).strip()
                    if typ == "S":
                        gsp_val = gp.get("GDL_PRM_AMT")
                    elif typ == "A":
                        glp_val = gp.get("GDL_PRM_AMT")

                tfdf = str(non_trd.get("TFDF_CD", "")).strip()
                tefra_defra = {"1": "TEFRA", "2": "DEFRA", "3": "DEFRA", "5": "DEFRA"}.get(tfdf, tfdf)
                gpt_cvat = {"1": "GP", "2": "GP", "4": "GP", "3": "CVAT", "5": "CVAT"}.get(tfdf, tfdf)

                corr_pct = non_trd.get("CDR_PCT")
                corr_display = ""
                if corr_pct is not None:
                    try:
                        corr_display = f"{float(corr_pct) / 100:.2f}"
                    except Exception:
                        corr_display = str(corr_pct)

                nsp_base = None
                nsp_other = None
                accum_glp = None
                try:
                    cols3, rows3 = db.execute_query_with_headers(
                        f"SELECT * FROM DB2TAB.LH_POL_TARGET WHERE {where_clause}"
                    )
                    for row in rows3 or []:
                        target = dict(zip(cols3, row))
                        typ = str(target.get("TAR_TYP_CD", "")).strip()
                        if typ == "NS":
                            nsp_base = target.get("TAR_PRM_AMT")
                        elif typ == "NT":
                            nsp_other = target.get("TAR_PRM_AMT")
                        elif typ == "TA":
                            accum_glp = target.get("TAR_PRM_AMT")
                except Exception:
                    pass

                doli_data = {
                    "is_advanced": True,
                    "tefra_defra": tefra_defra,
                    "gpt_cvat": gpt_cvat,
                    "gsp": gsp_val,
                    "glp": glp_val,
                    "accum_glp": accum_glp,
                    "corr_pct": corr_display,
                    "base_nsp": nsp_base,
                    "other_nsp": nsp_other,
                }
            else:
                doli_data = {"is_advanced": False}

            self.doli_widget.load_data(doli_data)

            totals = {}
            try:
                cols, rows = db.execute_query_with_headers(
                    f"SELECT * FROM DB2TAB.LH_POL_TOTALS WHERE {where_clause}"
                )
                totals = dict(zip(cols, rows[0])) if rows else {}
            except Exception:
                pass

            ytd_total = 0.0
            try:
                cols, rows = db.execute_query_with_headers(
                    f"SELECT * FROM DB2TAB.LH_POL_YR_TOT WHERE {where_clause}"
                )
                if rows:
                    last_row = dict(zip(cols, rows[-1]))
                    ytd_total = (float(last_row.get("YTD_TOT_PMT_AMT", 0) or 0)
                                 + float(last_row.get("YTD_ADD_PRM_AMT", 0) or 0))
            except Exception:
                pass

            reg_prem = float(totals.get("TOT_REG_PRM_AMT", 0) or 0)
            add_prem = float(totals.get("TOT_ADD_PRM_AMT", 0) or 0)
            accum_data = {
                "premiums_paid": reg_prem + add_prem,
                "reg_prem": reg_prem,
                "additional_prem": add_prem,
                "prem_ytd": ytd_total,
                "cost_basis": totals.get("POL_CST_BSS_AMT"),
                "accum_wds": totals.get("TOT_WTD_AMT"),
            }
            self.accum_widget.load_data(accum_data)

            tamra_per = {}
            try:
                cols, rows = db.execute_query_with_headers(
                    f"SELECT * FROM DB2TAB.LH_TAMRA_7_PY_PER WHERE {where_clause}"
                )
                tamra_per = dict(zip(cols, rows[0])) if rows else {}
            except Exception:
                pass

            tamra_yr_list = []
            try:
                cols, rows = db.execute_query_with_headers(
                    f"SELECT * FROM DB2TAB.LH_TAMRA_7_PY_YR WHERE {where_clause}"
                )
                tamra_yr_list = [dict(zip(cols, row)) for row in rows] if rows else []
            except Exception:
                pass

            self.tamra_widget.load_data(tamra_per, tamra_yr_list)

            pol_targets, cov_data, rnl_data, com_targets = [], [], [], []
            for tbl, lst in [
                ("LH_POL_TARGET", pol_targets),
                ("LH_COV_PHA", cov_data),
                ("LH_COV_INS_RNL_RT", rnl_data),
                ("LH_COM_TARGET", com_targets),
            ]:
                try:
                    cols, rows = db.execute_query_with_headers(
                        f"SELECT * FROM DB2TAB.{tbl} WHERE {where_clause}"
                    )
                    lst.extend([dict(zip(cols, r)) for r in rows] if rows else [])
                except Exception:
                    pass

            self.commission_widget.set_not_applicable(not is_advanced)
            self.min_prem_widget.set_not_applicable(not is_advanced)
            self.commission_widget.load_data(com_targets, cov_data, rnl_data)
            self.min_prem_widget.load_data(pol_targets, cov_data, rnl_data)

        except Exception:
            pass

    def load_data_from_policy(self, policy: 'PolicyInformation'):
        """Load all data for this tab using PolicyInformation."""
        try:
            is_advanced = policy.is_advanced_product

            # ── Definition of Life Insurance ──────────────────────────────
            if is_advanced:
                gsp_val = policy.gsp
                glp_val = policy.glp
                accum_glp_val = policy.accumulated_glp_target

                corr_pct = policy.corridor_percent
                corr_pct_display = ""
                if corr_pct is not None:
                    try:
                        corr_pct_display = f"{float(corr_pct) / 100:.2f}"
                    except Exception:
                        corr_pct_display = str(corr_pct)

                prem_pay_years = ""
                max_annual = None
                min_qual_glp = None

                gpt_cvat = policy.gpt_cvat
                tefra_defra = policy.tefra_defra
                gpt_cvat_display = "GP" if gpt_cvat == "GPT" else gpt_cvat

                if gpt_cvat in ("GP", "GPT"):
                    try:
                        status_code = int(policy.status_code or "99")
                        val_date = policy.valuation_date
                        if (status_code < 97 and val_date is not None
                                and accum_glp_val is not None and glp_val is not None
                                and str(accum_glp_val) != "Null" and str(glp_val) != "Null"):
                            age_at_mat = policy.age_at_maturity
                            att_age = policy.attained_age
                            if age_at_mat is not None and att_age is not None:
                                ins_def_mat_age = min(100, age_at_mat)
                                prem_pay_yrs = max(0, ins_def_mat_age - att_age - 1)
                                prem_pay_years = str(prem_pay_yrs)
                                accum_glp_at_mat = (float(glp_val) * prem_pay_yrs
                                                    + float(accum_glp_val))
                                premium_td_f = float(policy.premium_td)
                                accum_wds_f = float(policy.total_withdrawals)
                                if prem_pay_yrs > 0:
                                    max_annual = (accum_glp_at_mat
                                                  - (premium_td_f - accum_wds_f)) / prem_pay_yrs
                                    min_qual = -(float(accum_glp_val)
                                                 - (premium_td_f - accum_wds_f)) / prem_pay_yrs
                                    if min_qual < 0:
                                        min_qual_glp = min_qual
                                else:
                                    max_annual = 0
                    except Exception:
                        pass

                doli_data = {
                    "is_advanced": True,
                    "tefra_defra": tefra_defra,
                    "gpt_cvat": gpt_cvat_display,
                    "gsp": gsp_val,
                    "glp": glp_val,
                    "accum_glp": accum_glp_val,
                    "corr_pct": corr_pct_display,
                    "prem_pay_years": prem_pay_years,
                    "max_annual_level_qual_prem": max_annual,
                    "min_qualifying_glp": min_qual_glp,
                    "base_nsp": policy.nsp_base,
                    "other_nsp": policy.nsp_other,
                }
            else:
                doli_data = {"is_advanced": False}

            self.doli_widget.load_data(doli_data)

            # ── Accumulators ──────────────────────────────────────────────
            reg_prem = float(policy.total_regular_premium or 0)
            add_prem = float(policy.total_additional_premium or 0)
            prem_ytd = float(policy.premium_ytd or 0)
            cost_basis_val = (float(policy.cost_basis or 0)
                              if policy.policy_totals_count > 0 else None)
            accum_wds_val = (float(policy.total_withdrawals or 0)
                             if policy.policy_totals_count > 0 else None)
            accum_data = {
                "premiums_paid": reg_prem + add_prem,
                "reg_prem": reg_prem,
                "additional_prem": add_prem,
                "prem_ytd": prem_ytd,
                "cost_basis": cost_basis_val,
                "accum_wds": accum_wds_val,
            }
            self.accum_widget.load_data(accum_data)

            # ── TAMRA Values ──────────────────────────────────────────────
            tamra_per_rows = policy.fetch_table("LH_TAMRA_7_PY_PER")
            tamra_per = tamra_per_rows[0] if tamra_per_rows else {}
            tamra_yr_list = policy.fetch_table("LH_TAMRA_7_PY_YR")
            self.tamra_widget.load_data(tamra_per, tamra_yr_list)

            # ── Commission Target & Minimum Premium ───────────────────────
            # Traditional products: show sections as N/A (green bg, single label)
            self.commission_widget.set_not_applicable(not is_advanced)
            self.min_prem_widget.set_not_applicable(not is_advanced)

            cov_data = policy.fetch_table("LH_COV_PHA")
            rnl_data = policy.fetch_table("LH_COV_INS_RNL_RT")
            com_targets = policy.fetch_table("LH_COM_TARGET")
            pol_targets = policy.fetch_table("LH_POL_TARGET")

            if is_advanced:
                # Advanced product but no target rows found in DB2 tables
                # → show greyed-out 'Data not available' instead of empty tables
                com_data_unavailable = len(com_targets) == 0
                pol_data_unavailable = len(pol_targets) == 0
                self.commission_widget.set_data_unavailable(com_data_unavailable)
                self.min_prem_widget.set_data_unavailable(pol_data_unavailable)

            self.commission_widget.load_data(com_targets, cov_data, rnl_data)
            self.min_prem_widget.load_data(pol_targets, cov_data, rnl_data)

        except Exception:
            import traceback
            traceback.print_exc()
