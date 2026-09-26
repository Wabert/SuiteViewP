"""Workbook specification and writers for ABR quote detail exports.

The calculation viewer and output panel share the same workbook model.  The
interactive writer opens an unsaved Excel workbook through COM; the headless
writer saves an ``.xlsx`` via openpyxl for support-file generation and tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..models.abr_constants import MODAL_LABELS, PLAN_CODE_INFO


@dataclass(frozen=True)
class FieldRow:
    """A label/value row in a workbook section."""

    label: str
    value: Any


@dataclass(frozen=True)
class SectionSpec:
    """A titled field-row section."""

    title: str
    rows: list[FieldRow] = field(default_factory=list)


@dataclass(frozen=True)
class TableSpec:
    """A rectangular table."""

    headers: tuple[str, ...]
    rows: list[tuple[Any, ...]] = field(default_factory=list)


@dataclass(frozen=True)
class SheetSpec:
    """A workbook sheet containing sections or one table."""

    name: str
    title: str = ""
    sections: list[SectionSpec] = field(default_factory=list)
    table: TableSpec | None = None


@dataclass(frozen=True)
class WorkbookSpec:
    """Complete ABR detail workbook specification."""

    sheets: list[SheetSpec]


def _money(value: float | int | None, dash: str = "—") -> str:
    return f"${value:,.2f}" if value else dash


def _date(value) -> str:
    return value.strftime("%m/%d/%Y") if value else "—"


def _plan_description(policy) -> str:
    if not policy or not policy.plan_code:
        return "—"
    info = PLAN_CODE_INFO.get(policy.plan_code.upper())
    return f"{info[1]} ({info[0]}-Year Level)" if info else "—"


def _policy_sheet(policy, result) -> SheetSpec:
    sex_display = {"M": "Male", "F": "Female", "U": "Unisex"}.get(
        policy.sex,
        policy.sex or "—",
    )
    rider_rows = []
    if policy.riders:
        for rider in policy.riders:
            desc = f"{rider.plancode} ({rider.rider_type})"
            if rider.benefit_type:
                desc += f" — BNF {rider.benefit_type}{rider.benefit_subtype or ''}"
            rider_rows.append(FieldRow(desc, f"${rider.fallback_premium:,.2f}/yr"))
    else:
        rider_rows.append(FieldRow("No riders.", ""))
    return SheetSpec(
        name="Policy Info",
        title="ABR Quote — Policy Information",
        sections=[
            SectionSpec("Policy Details", [
                FieldRow("Policy Number:", policy.policy_number),
                FieldRow("Insured:", policy.insured_name or "—"),
                FieldRow("Plancode:", policy.plan_code or "—"),
                FieldRow("Plan Description:", _plan_description(policy)),
                FieldRow("Sex:", sex_display),
                FieldRow("Rate Sex:", policy.rate_sex or "—"),
                FieldRow("Issue Age:", policy.issue_age),
                FieldRow("Attained Age:", policy.attained_age),
                FieldRow("Rate Class:", policy.rate_class or "—"),
                FieldRow("Face Amount:", _money(policy.face_amount)),
                FieldRow("Min Face:", f"${policy.min_face_amount:,.0f}"),
                FieldRow("Issue State:", policy.issue_state or "—"),
                FieldRow("Issue Date:", _date(policy.issue_date)),
                FieldRow("Policy Year:", policy.policy_year),
                FieldRow("Month of Year:", policy.policy_month),
                FieldRow("Base Plancode:", policy.base_plancode or "—"),
                FieldRow("Billing Mode:", MODAL_LABELS.get(policy.billing_mode, str(policy.billing_mode))),
                FieldRow("Modal Premium:", _money(policy.modal_premium)),
                FieldRow("Table Rating:", policy.table_rating),
                FieldRow(
                    "Annual Flat Extra:",
                    f"${policy.flat_extra:.2f}" if policy.flat_extra > 0 else "None",
                ),
                FieldRow("Flat Cease Date:", _date(policy.flat_cease_date)),
                FieldRow("Reinsurers:", policy.reinsurers or "(none)"),
            ]),
            SectionSpec("Quote Parameters", [
                FieldRow("Quote Date:", _date(result.quote_date)),
                FieldRow("ABR Interest Rate:", f"{result.abr_interest_rate * 100:.2f}%"),
                FieldRow("Per Diem (Daily):", f"${result.per_diem_daily:,.2f}"),
                FieldRow("Per Diem (Annual):", f"${result.per_diem_annual:,.2f}"),
            ]),
            SectionSpec("Riders / Coverages", rider_rows),
        ],
    )


def _assessment_sheet(
    assessment,
    result,
    derived_values: dict[str, str],
    accel_amount: float,
    min_face_amount: float,
    after_partial_override: str,
) -> SheetSpec:
    input_rows = [FieldRow("Rider Type:", assessment.rider_type if assessment else "—")]
    if assessment:
        if assessment.use_five_year:
            input_rows.append(FieldRow("5-Year Survival Rate:", f"{assessment.five_year_survival}"))
            input_rows.append(FieldRow("  Return to Normal:", "Yes" if assessment.use_return_5yr else "No"))
        if assessment.use_ten_year:
            input_rows.append(FieldRow("10-Year Survival Rate:", f"{assessment.ten_year_survival}"))
            input_rows.append(FieldRow("  Return to Normal:", "Yes" if assessment.use_return_10yr else "No"))
        if assessment.use_le:
            input_rows.append(FieldRow("Life Expectancy:", f"{assessment.life_expectancy_years} years"))
        if assessment.use_increased_decrement:
            input_rows.append(FieldRow("Increased Decrement:", f"{assessment.direct_increased_decrement:.0f}%"))
            input_rows.append(FieldRow(
                "  Start/Stop Year:",
                f"{assessment.incr_decrement_start_year} — {assessment.incr_decrement_stop_year}",
            ))
        if assessment.use_table:
            input_rows.append(FieldRow("Table (rating):", f"{assessment.direct_table_rating}"))
            input_rows.append(FieldRow(
                "  Start/Stop Year:",
                f"{assessment.table_start_year} — {assessment.table_stop_year}",
            ))
        if assessment.use_flat:
            input_rows.append(FieldRow("Flat ($/1000):", f"${assessment.direct_flat_extra:.2f}"))
            input_rows.append(FieldRow(
                "  Start/Stop Year:",
                f"{assessment.flat_start_year} — {assessment.flat_stop_year}",
            ))
        input_rows.append(FieldRow("In Lieu Of:", "Yes" if assessment.in_lieu_of else "No (In Addition To)"))

    derived_rows = []
    if derived_values:
        for label, key in (
            ("5-Year Survival:", "mod_survival_5yr"),
            ("10-Year Survival:", "mod_survival_10yr"),
            ("Life Expectancy:", "mod_le"),
            ("Table Ratings:", "table_rating"),
            ("Flat Extras:", "flat_extra"),
        ):
            derived_rows.append(FieldRow(label, derived_values.get(key, "—")))
    elif assessment:
        derived_rows.append(FieldRow("Derived Table Rating:", f"{assessment.derived_table_rating:.4f}"))
        derived_rows.append(FieldRow("Life Expectancy (rounded):", f"{assessment.life_expectancy_rounded}"))

    after_partial = after_partial_override or result.premium_after_partial
    return SheetSpec(
        name="Assessment",
        title="ABR Quote — Assessment",
        sections=[
            SectionSpec("Rider Configuration", input_rows[:1]),
            SectionSpec("Assessment Inputs", input_rows[1:]),
            SectionSpec("Derived Substandard Values", derived_rows),
            SectionSpec("Results Summary", [
                FieldRow("Acceleration Amount Input:", f"${accel_amount:,.2f}" if accel_amount else "—"),
                FieldRow("Eligible Death Benefit:", f"${result.full_eligible_db:,.2f}"),
                FieldRow("Actuarial Discount:", f"${result.full_actuarial_discount:,.2f}"),
                FieldRow("Administrative Fee:", f"${result.full_admin_fee:,.2f}"),
                FieldRow("Calculated Benefit:", f"${max(0.0, result.full_accel_benefit):,.2f}"),
                FieldRow("Benefit Ratio:", f"{result.full_benefit_ratio * 100:.2f}%"),
                FieldRow("Min Face Amount Input:", f"${min_face_amount:,.0f}"),
                FieldRow("Partial Eligible Death Benefit:", f"${result.partial_eligible_db:,.2f}"),
                FieldRow("After (Partial):", after_partial),
                FieldRow("APV_FB:", f"${result.apv_fb:,.2f}"),
                FieldRow("APV_FP:", f"${result.apv_fp:,.2f}"),
                FieldRow("APV_FD:", f"${result.apv_fd:,.2f}"),
            ]),
        ],
    )


def _mortality_sheet(rows: list[dict]) -> SheetSpec:
    headers = (
        "Quote Month", "Policy Year", "Mo/Yr", "Att Age",
        "qx VBT", "qx Multiplied", "qx Improved", "Table Rating",
        "qx Table Rated", "Flat Extra", "qx Flat Extra", "qx Capped",
        "qx Monthly", "px Monthly", "Cum Survival",
    )
    data = [
        (
            row.get("quote_month"),
            row.get("duration_year"),
            row.get("month_in_year"),
            row.get("attained_age"),
            row.get("qx_vbt"),
            row.get("qx_multiplied"),
            row.get("qx_improved"),
            row.get("table_rating_applied"),
            row.get("qx_table_rated"),
            row.get("flat_extra_applied"),
            row.get("qx_flat_extra"),
            row.get("qx_capped"),
            row.get("qx_monthly"),
            row.get("px_monthly"),
            row.get("cum_survival"),
        )
        for row in rows
    ]
    return SheetSpec("Mortality Derivation", table=TableSpec(headers, data))


def _life_expectancy_sheet(rows: list[dict]) -> SheetSpec:
    headers = ("Month", "Policy Year", "Att Age", "qx Monthly", "px Monthly", "tPx")
    tp = 1.0
    data = []
    for index, row in enumerate(rows, start=1):
        data.append((
            index,
            row.get("duration_year"),
            row.get("attained_age"),
            row.get("qx_monthly"),
            row.get("px_monthly"),
            tp,
        ))
        tp *= row.get("px_monthly", 1.0)
    return SheetSpec("Life Expectancy", table=TableSpec(headers, data))


def _apv_sheet(rows: list[dict], apv_sheet_name: str) -> SheetSpec:
    headers = (
        "Month", "t", "qx Monthly", "px Monthly", "tpx (cum surv)",
        "v^(t+1)", "v^t", "Death Benefit", "PVDB(t)", "PVDB Cum",
        "Prem Rate", "PVFP(t)", "PVFP Cum", "tpx End",
    )
    data = [
        (
            row.get("month"),
            row.get("t"),
            row.get("qx_monthly"),
            row.get("px_monthly"),
            row.get("tp_x"),
            row.get("v_benefit"),
            row.get("v_premium"),
            row.get("death_benefit", 0.0),
            row.get("pvdb_t"),
            row.get("pvdb_cum"),
            row.get("prem_rate"),
            row.get("pvfp_t"),
            row.get("pvfp_cum"),
            row.get("tp_x_end"),
        )
        for row in rows
    ]
    return SheetSpec(apv_sheet_name, table=TableSpec(headers, data))


def build_detail_workbook_spec(
    policy,
    result,
    assessment,
    mortality_rows: list[dict],
    apv_rows: list[dict],
    apv_summary: dict | None = None,
    derived_values: dict[str, str] | None = None,
    accel_amount: float = 0.0,
    min_face_amount: float = 0.0,
    after_partial_override: str = "",
    apv_sheet_name: str = "APV - Present Value",
) -> WorkbookSpec:
    """Build the five-sheet ABR detail workbook model."""
    del apv_summary
    return WorkbookSpec([
        _policy_sheet(policy, result),
        _assessment_sheet(
            assessment,
            result,
            derived_values or {},
            accel_amount,
            min_face_amount,
            after_partial_override,
        ),
        _mortality_sheet(mortality_rows),
        _life_expectancy_sheet(mortality_rows),
        _apv_sheet(apv_rows, apv_sheet_name),
    ])


def _write_openpyxl_sheet(workbook, sheet: SheetSpec, active: bool = False) -> None:
    if active:
        ws = workbook.active
        ws.title = sheet.name
    else:
        ws = workbook.create_sheet(sheet.name)
    if sheet.table:
        ws.append(sheet.table.headers)
        for row in sheet.table.rows:
            ws.append(row)
        return
    row_number = 1
    if sheet.title:
        ws.cell(row=row_number, column=1, value=sheet.title)
        row_number += 2
    for section in sheet.sections:
        ws.cell(row=row_number, column=1, value=section.title)
        row_number += 1
        for field in section.rows:
            ws.cell(row=row_number, column=1, value=field.label)
            ws.cell(row=row_number, column=2, value=field.value)
            row_number += 1
        row_number += 1


def write_openpyxl(spec: WorkbookSpec, path: str) -> str:
    """Write an ABR detail workbook to ``path`` with openpyxl."""
    import openpyxl
    from openpyxl.styles import Font

    workbook = openpyxl.Workbook()
    for index, sheet in enumerate(spec.sheets):
        _write_openpyxl_sheet(workbook, sheet, active=index == 0)
    for ws in workbook.worksheets:
        for cell in ws[1]:
            cell.font = Font(bold=True)
        ws.column_dimensions["A"].width = 28
        ws.column_dimensions["B"].width = 35
    workbook.save(path)
    return path


def _com_write_table(ws, table: TableSpec) -> None:
    data = [table.headers, *table.rows]
    if not data:
        return
    col_count = len(table.headers)
    ws.Range(ws.Cells(1, 1), ws.Cells(len(data), col_count)).Value = data


def _com_write_sections(ws, sheet: SheetSpec) -> None:
    row = 1
    if sheet.title:
        ws.Cells(row, 1).Value = sheet.title
        ws.Cells(row, 1).Font.Bold = True
        row += 2
    for section in sheet.sections:
        ws.Cells(row, 1).Value = section.title
        ws.Cells(row, 1).Font.Bold = True
        row += 1
        for field in section.rows:
            ws.Cells(row, 1).Value = field.label
            ws.Cells(row, 1).Font.Bold = True
            ws.Cells(row, 2).Value = field.value
            row += 1
        row += 1


def write_excel_com(spec: WorkbookSpec):
    """Open an unsaved Excel workbook and populate it from ``spec``."""
    from win32com.client import dynamic

    excel = dynamic.Dispatch("Excel.Application")
    excel.Visible = True
    excel.ScreenUpdating = False
    workbook = excel.Workbooks.Add()
    previous = None
    for index, sheet in enumerate(spec.sheets):
        if index == 0:
            ws = workbook.Worksheets(1)
        else:
            ws = workbook.Worksheets.Add(After=previous)
        ws.Name = sheet.name
        if sheet.table:
            _com_write_table(ws, sheet.table)
        else:
            _com_write_sections(ws, sheet)
        ws.Columns.AutoFit()
        previous = ws
    workbook.Worksheets(1).Activate()
    workbook.Worksheets(1).Range("A1").Select()
    excel.ScreenUpdating = True
    return workbook
