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


def seven_pay_backtest(policy, states: list, recalc_index: int, detail: dict) -> dict | None:
    """Retroactively test a recalculated seven-pay level against its window."""
    new_level = float(detail.get("seven_pay_new") or 0.0)
    window_start = detail.get("seven_pay_window_start")
    change_year = int(detail.get("tamra_year_at_change") or 0)
    if new_level <= 0.0 or window_start is None or not (1 <= change_year <= 7):
        return None
    recalc_state = states[recalc_index]

    projected_cum: dict[int, float] = {}
    for state in states[1:recalc_index + 1]:
        if state.tamra_7pay_start_date == window_start and 1 <= state.tamra_year <= 7:
            projected_cum[state.tamra_year] = state.accumulated_7pay
    projected_cum[change_year] = recalc_state.amount_in_7pay

    contributions = list(getattr(policy, "tamra_7year_contributions", None) or [])
    window_is_original = states[0].tamra_7pay_start_date == window_start

    rows: list[dict] = []
    mec_year: int | None = None
    prior_cum = 0.0
    for year in range(1, 8):
        if year > change_year:
            cumulative = None
        elif year in projected_cum:
            cumulative = projected_cum[year]
        elif window_is_original and year <= len(contributions):
            cumulative = sum(contributions[:year])
        else:
            cumulative = None
        limit = year * new_level
        if cumulative is None:
            result = "not reached"
        elif mec_year is not None or cumulative > limit + 0.005:
            result = "MEC"
            if mec_year is None:
                mec_year = year
        else:
            result = "OK"
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
    return {
        "rows": rows,
        "is_mec": mec_year is not None,
        "mec_year": mec_year,
        "new_level": new_level,
        "window_start": window_start,
        "through_date": recalc_state.date,
    }