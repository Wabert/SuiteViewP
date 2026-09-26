"""TAMRA seven-pay back-testing and permanent MEC determination."""
from __future__ import annotations

from suiteview.illustration.models.calc_state import MonthlyState


def seven_pay_limit_exceeded(state: MonthlyState) -> bool:
    """Test accepted contributions against the active seven-pay year's limit."""
    return (
        1 <= state.tamra_year <= 7
        and state.tamra_7pay_level >= 0.0
        and state.accumulated_7pay
        > state.tamra_year * state.tamra_7pay_level + 0.005
    )


def _add_years(value, years: int):
    if value is None:
        return None
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(year=value.year + years, day=28)


def _fmt_date(value) -> str:
    return f"{value:%m/%d/%Y}" if value else ""


def _projected_cumulative_by_year(
    states: list,
    recalc_index: int,
    window_start,
    change_year: int,
    amount_in_7pay: float,
) -> dict[int, float]:
    projected = {}
    for state in states[1:recalc_index + 1]:
        if state.tamra_7pay_start_date == window_start and 1 <= state.tamra_year <= 7:
            projected[state.tamra_year] = state.accumulated_7pay
    projected[change_year] = amount_in_7pay
    return projected


def _cumulative_for_backtest_year(
    year: int,
    *,
    change_year: int,
    projected_cum: dict[int, float],
    window_is_original: bool,
    contributions: list,
):
    if year > change_year:
        return None
    if year in projected_cum:
        return projected_cum[year]
    if window_is_original and year <= len(contributions):
        return sum(contributions[:year])
    return None


def _backtest_result(
    cumulative,
    limit: float,
    mec_year: int | None,
    year: int,
) -> tuple[str, int | None]:
    if cumulative is None:
        return "not reached", mec_year
    if mec_year is not None or cumulative > limit + 0.005:
        return "MEC", mec_year or year
    return "OK", mec_year


def _seven_pay_backtest_rows(
    *,
    new_level: float,
    window_start,
    change_year: int,
    projected_cum: dict[int, float],
    window_is_original: bool,
    contributions: list,
) -> tuple[list[dict], int | None]:
    rows: list[dict] = []
    mec_year: int | None = None
    prior_cum = 0.0
    for year in range(1, 8):
        cumulative = _cumulative_for_backtest_year(
            year,
            change_year=change_year,
            projected_cum=projected_cum,
            window_is_original=window_is_original,
            contributions=contributions,
        )
        limit = year * new_level
        result, mec_year = _backtest_result(cumulative, limit, mec_year, year)
        rows.append({
            "TAMRA Year": year,
            "Year Begins": _fmt_date(_add_years(window_start, year - 1)),
            "Net Prems (Year)": None if cumulative is None else cumulative - prior_cum,
            "Net Prems (Cum)": cumulative,
            "7-Pay Limit (Cum)": limit,
            "Margin": None if cumulative is None else limit - cumulative,
            "Result": result,
        })
        if cumulative is not None:
            prior_cum = cumulative
    return rows, mec_year


def seven_pay_backtest(policy, states: list, recalc_index: int, detail: dict) -> dict | None:
    """Retroactively test a recalculated seven-pay level against its window."""
    new_level = float(detail.get("seven_pay_new") or 0.0)
    window_start = detail.get("seven_pay_window_start")
    change_year = int(detail.get("tamra_year_at_change") or 0)
    if new_level <= 0.0 or window_start is None or not (1 <= change_year <= 7):
        return None
    recalc_state = states[recalc_index]

    projected_cum = _projected_cumulative_by_year(
        states,
        recalc_index,
        window_start,
        change_year,
        recalc_state.amount_in_7pay,
    )
    contributions = list(getattr(policy, "tamra_7year_contributions", None) or [])
    window_is_original = states[0].tamra_7pay_start_date == window_start
    rows, mec_year = _seven_pay_backtest_rows(
        new_level=new_level,
        window_start=window_start,
        change_year=change_year,
        projected_cum=projected_cum,
        window_is_original=window_is_original,
        contributions=contributions,
    )
    return {
        "rows": rows,
        "is_mec": mec_year is not None,
        "mec_year": mec_year,
        "new_level": new_level,
        "window_start": window_start,
        "through_date": recalc_state.date,
    }