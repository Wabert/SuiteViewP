"""Read-only access to the UL_Rates schema ``rates`` (the four-structure rate tables).

The schema is built and loaded by ``Cyberlife_Rates\\Rates_Database`` (DDL in its
``sql\\rates_schema.sql``). SuiteView only reads it. The four ways to find a rate:

* **CELL** ``RATE_ASSIGN_CELL`` (plan, benefit, sex, class, band, state, sub-series,
  rate type) -> ``SCHEDULE_ID`` -> ``RATE_SCHEDULE_DATE`` (scale C/G/S, effective
  window) -> ``RATE_SET_ID`` -> ``RATE_VALUE`` (issue age, duration).
* **PLAN** ``RATE_ASSIGN_PLAN`` (plan, state, rate type, scale) -> ``RATE_SET_ID``.
* **FUND** ``RATE_ASSIGN_FUND`` (plan, fund, reinsurance block) -> ``FUND_KEY`` ->
  ``RATE_VALUE_FUND`` (dated rates).
* **DIV** ``RATE_ASSIGN_DIV`` -> ``RATE_SCHEDULE_DATE_DIV`` -> ``RATE_VALUE_DIV``.

``RATE_TYPE.STRUCTURE`` says which structure holds a rate type and
``RATE_TYPE.DATE_MEANING`` whether a lookup passes the issue date or a calendar date.
This module returns plain frozen rows; choosing the rows that apply to a policy is
the caller's job. Failures raise ``RatesError``; nothing is turned into "no rate".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable, Optional, Sequence

from .data_access.connections import connection_factory
from .data_access.errors import ConnectionUnavailable
from .local_dev import local_data_enabled
from .rates_errors import RatesError, is_query_timeout

logger = logging.getLogger(__name__)

SCHEMA = "rates"
SCALE_LABELS = {"C": "current", "G": "guaranteed", "S": "shadow account"}
_IN_CHUNK = 500


@dataclass(frozen=True)
class RateTypeDef:
    rate_type: str
    description: str
    structure: str      # CELL / PLAN / FUND / DIV
    unit: str
    date_meaning: str   # ISSUE / CALENDAR / NONE
    product_family: str


@dataclass(frozen=True)
class PlanDef:
    company: str
    plancode: str
    user_code: str
    product_family: str
    coverage_role: str
    description: str
    facts: tuple  # (column, value) pairs of the remaining PLAN_DEF columns, in table order


@dataclass(frozen=True)
class BandSpec:
    band: str
    issue_date_from: date
    band_structure: str
    upper_limit: Optional[Decimal]
    source_band: str


@dataclass(frozen=True)
class SubseriesRow:
    sex: str
    rate_class: str
    subseries: str
    cvf_key: str


@dataclass(frozen=True)
class CellAssignment:
    benefit: str
    sex: str
    rate_class: str
    band: str
    state: str
    subseries: str
    rate_type: str
    schedule_id: int


@dataclass(frozen=True)
class ScheduleWindow:
    schedule_id: int
    scale: str
    effective_from: date
    effective_to: Optional[date]   # exclusive; None = still in effect
    rate_set_id: int

    def covers(self, on: date) -> bool:
        return self.effective_from <= on and (self.effective_to is None or on < self.effective_to)


@dataclass(frozen=True)
class RateSetInfo:
    rate_set_id: int
    rate_type: str
    grain: str          # IA_DUR / IA / DUR / AA / SCALAR / DIV
    description: str
    source_ref: str


@dataclass(frozen=True)
class PlanAssignment:
    state: str
    rate_type: str
    scale: str
    rate_set_id: int


@dataclass(frozen=True)
class FundAssignment:
    fund: str
    rein_block: str
    fund_key: str
    fund_type: str
    source_key: str
    description: str


@dataclass(frozen=True)
class FundRate:
    fund_key: str
    rate_type: str
    scale: str
    rate_start: date
    period: int
    guarantee_months: Optional[int]
    guarantee_end_date: Optional[date]
    rate: Decimal


@dataclass(frozen=True)
class DivAssignment:
    sex: str
    rate_class: str
    band: str
    state: str
    rein: str
    div_key: str
    user_key: str


@dataclass(frozen=True)
class DivSchedule:
    div_key: str
    user_key: str
    record_type: str
    issue_date_from: date
    effective_from: date
    effective_to: Optional[date]
    rate_set_id: int
    pua_participating: Optional[str]
    pua_key: Optional[str]
    pua_user_key: Optional[str]

    def covers(self, on: date) -> bool:
        return self.effective_from <= on and (self.effective_to is None or on < self.effective_to)


@dataclass(frozen=True)
class DivValue:
    div_rate: Optional[Decimal]
    pua_rate: Optional[Decimal]
    oyt_rate: Optional[Decimal]


@dataclass(frozen=True)
class ModeFactor:
    market_org: str
    billing_form: str
    fee_amount_from: Decimal
    fee_amount_to: Optional[Decimal]
    mode: str
    prem_factor: Decimal
    fee_factor: Decimal
    policy_fee_annual: Decimal
    policy_fee_add: str
    policy_fee_rule: str
    collection_fee: Decimal
    collection_fee_add: str
    multiply_order: str
    rating_order: str
    rounding_rule: str


@dataclass(frozen=True)
class PlanAttr:
    attr: str
    value: str


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _key(value) -> str:
    """Key column text: trailing blanks removed, inner blanks kept (DIV user keys)."""
    return "" if value is None else str(value).rstrip()


def _date(value) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _chunks(values: Sequence, size: int = _IN_CHUNK) -> Iterable[Sequence]:
    for start in range(0, len(values), size):
        yield values[start:start + size]


def _placeholders(count: int) -> str:
    return ", ".join("?" for _ in range(count))


_PLAN_DEF_FACT_COLUMNS = (
    "FEMALE_AGE_FIRST", "FEMALE_AGE_LAST", "MALE_AGE_FIRST", "MALE_AGE_LAST",
    "PREMIUM_CEASE_AGE", "PREMIUM_CEASE_DUR", "MATURITY_AGE", "MATURITY_DUR",
    "LEVEL_PERIOD", "RENEWAL_START_DUR", "RENEWAL_PERIOD", "VALUE_PER_UNIT",
    "BAND_STRUCTURE", "MODE_PREM_TABLE", "PREMLOAD_TABLE", "PREMLOAD_RULES",
    "SCR_TABLE", "SCR_RULES", "EXPENSE_TABLE", "CIRF_USER", "CIRF_KEY",
    "CIRF_INV_TYPE", "MORTALITY_CODE", "CVF_KEY",
)


class RatesSchemaRepository:
    """Read-only queries against UL_Rates schema ``rates``; use as a context manager."""

    QUERY_TIMEOUT = 15
    _rate_types: Optional[dict[str, RateTypeDef]] = None  # reference data, loaded once per process

    def __init__(self, connection: Any = None):
        self._connection = connection
        self._owns_connection = connection is None

    def __enter__(self) -> "RatesSchemaRepository":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if self._connection is not None and self._owns_connection:
            try:
                self._connection.close()
            except Exception:
                logger.debug("Closing the rates-schema connection failed", exc_info=True)
            self._connection = None

    def _get_connection(self):
        if self._connection is None:
            if local_data_enabled():
                raise ConnectionUnavailable(
                    "UL_Rates schema 'rates' is not part of the local development data; "
                    "unset SUITEVIEW_LOCAL_DATA to read the new rate tables."
                )
            self._connection = connection_factory.connect_ul_rates(
                autocommit=True, timeout=self.QUERY_TIMEOUT,
            )
            self._connection.timeout = self.QUERY_TIMEOUT
        return self._connection

    def _query(self, sql: str, params: Sequence = ()) -> list:
        from .sql_permissions import guard_query_sql

        guard_query_sql(sql)
        try:
            cursor = self._get_connection().cursor()
            try:
                cursor.execute(sql, list(params))
                return cursor.fetchall()
            finally:
                cursor.close()
        except ConnectionUnavailable:
            raise
        except Exception as exc:
            logger.error("Rates-schema query failed: %s | SQL: %s | params: %r", exc, sql, params)
            if is_query_timeout(exc):
                raise RatesError(
                    "UL_Rates did not answer within the query timeout. Schema 'rates' is "
                    "probably locked by a rate load in progress; try again when it finishes."
                ) from exc
            raise RatesError(f"Rates-schema lookup failed: {exc}") from exc

    def _query_in(self, sql_template: str, ids: Sequence, params_before: Sequence = (),
                  params_after: Sequence = ()) -> list:
        """Run ``sql_template`` (with one ``{ids}`` placeholder list) over chunks of ``ids``."""
        rows: list = []
        unique = list(dict.fromkeys(ids))
        for chunk in _chunks(unique):
            sql = sql_template.format(ids=_placeholders(len(chunk)))
            rows.extend(self._query(sql, [*params_before, *chunk, *params_after]))
        return rows

    # -- reference ---------------------------------------------------------------

    def rate_types(self) -> dict[str, RateTypeDef]:
        cls = type(self)
        if cls._rate_types is None:
            rows = self._query(
                "SELECT RATE_TYPE, DESCRIPTION, STRUCTURE, UNIT, DATE_MEANING, PRODUCT_FAMILY "
                "FROM rates.RATE_TYPE"
            )
            cls._rate_types = {
                _text(r[0]): RateTypeDef(_text(r[0]), _text(r[1]), _text(r[2]), _text(r[3]),
                                         _text(r[4]), _text(r[5]))
                for r in rows
            }
        return cls._rate_types

    # -- plan facts --------------------------------------------------------------

    def plan_defs(self, plancode: str) -> list[PlanDef]:
        columns = ", ".join(_PLAN_DEF_FACT_COLUMNS)
        rows = self._query(
            "SELECT COMPANY, PLANCODE, USER_CODE, PRODUCT_FAMILY, COVERAGE_ROLE, DESCRIPTION, "
            f"{columns} FROM rates.PLAN_DEF WHERE PLANCODE = ? ORDER BY COMPANY",
            [plancode],
        )
        plans = []
        for r in rows:
            facts = tuple(
                (name, value) for name, value in zip(_PLAN_DEF_FACT_COLUMNS, r[6:])
                if value is not None and _text(value) != ""
            )
            plans.append(PlanDef(_text(r[0]), _text(r[1]), _text(r[2]), _text(r[3]),
                                 _text(r[4]), _text(r[5]), facts))
        return plans

    def plan_attrs(self, company: str, plancode: str) -> list[PlanAttr]:
        rows = self._query(
            "SELECT ATTR, VALUE FROM rates.PLAN_ATTR WHERE COMPANY = ? AND PLANCODE = ? ORDER BY ATTR",
            [company, plancode],
        )
        return [PlanAttr(_text(r[0]), _text(r[1])) for r in rows]

    def plan_bands(self, company: str, plancode: str) -> list[BandSpec]:
        rows = self._query(
            "SELECT BAND, ISSUE_DATE_FROM, BAND_STRUCTURE, UPPER_LIMIT, SOURCE_BAND FROM rates.PLAN_BAND "
            "WHERE COMPANY = ? AND PLANCODE = ? ORDER BY ISSUE_DATE_FROM, UPPER_LIMIT",
            [company, plancode],
        )
        return [BandSpec(_text(r[0]), _date(r[1]), _text(r[2]), r[3], _text(r[4])) for r in rows]

    def plan_subseries(self, company: str, plancode: str) -> list[SubseriesRow]:
        rows = self._query(
            "SELECT SEX, RATE_CLASS, SUBSERIES, CVF_KEY FROM rates.PLAN_SUBSERIES "
            "WHERE COMPANY = ? AND PLANCODE = ?",
            [company, plancode],
        )
        return [SubseriesRow(_text(r[0]), _text(r[1]), _text(r[2]), _text(r[3])) for r in rows]

    def modal_factors(self, company: str, plancode: str) -> list[ModeFactor]:
        rows = self._query(
            "SELECT MARKET_ORG, BILLING_FORM, FEE_AMOUNT_FROM, FEE_AMOUNT_TO, MODE, PREM_FACTOR, FEE_FACTOR, "
            "POLICY_FEE_ANNUAL, POLICY_FEE_ADD, POLICY_FEE_RULE, COLLECTION_FEE, COLLECTION_FEE_ADD, "
            "MULTIPLY_ORDER, RATING_ORDER, ROUNDING_RULE FROM rates.PLAN_MODEFACT "
            "WHERE COMPANY = ? AND PLANCODE = ? ORDER BY MARKET_ORG, BILLING_FORM, FEE_AMOUNT_FROM, MODE",
            [company, plancode],
        )
        return [ModeFactor(_text(r[0]), _text(r[1]), r[2], r[3], _text(r[4]), r[5], r[6], r[7],
                           _text(r[8]), _text(r[9]), r[10], _text(r[11]), _text(r[12]),
                           _text(r[13]), _text(r[14])) for r in rows]

    def modal_factor_plancodes(self, company: str, prefix: str) -> list[str]:
        """Plancodes starting with ``prefix`` that have ``PLAN_MODEFACT`` rows for ``company``."""
        rows = self._query(
            "SELECT DISTINCT PLANCODE FROM rates.PLAN_MODEFACT WHERE COMPANY = ? AND PLANCODE LIKE ? "
            "ORDER BY PLANCODE",
            [company, f"{prefix}%"],
        )
        return [_text(r[0]) for r in rows]

    # -- 1 CELL ------------------------------------------------------------------

    def cell_assignments(self, company: str, plancode: str) -> list[CellAssignment]:
        rows = self._query(
            "SELECT BENEFIT, SEX, RATE_CLASS, BAND, STATE, SUBSERIES, RATE_TYPE, SCHEDULE_ID "
            "FROM rates.RATE_ASSIGN_CELL WHERE COMPANY = ? AND PLANCODE = ?",
            [company, plancode],
        )
        return [CellAssignment(_text(r[0]), _text(r[1]), _text(r[2]), _text(r[3]), _text(r[4]),
                               _text(r[5]), _text(r[6]), int(r[7])) for r in rows]

    def schedule_windows(self, schedule_ids: Sequence[int]) -> list[ScheduleWindow]:
        if not schedule_ids:
            return []
        rows = self._query_in(
            "SELECT SCHEDULE_ID, SCALE, EFFECTIVE_FROM, EFFECTIVE_TO, RATE_SET_ID "
            "FROM rates.RATE_SCHEDULE_DATE WHERE SCHEDULE_ID IN ({ids})",
            schedule_ids,
        )
        return [ScheduleWindow(int(r[0]), _text(r[1]), _date(r[2]), _date(r[3]), int(r[4])) for r in rows]

    def rate_sets(self, rate_set_ids: Sequence[int]) -> dict[int, RateSetInfo]:
        if not rate_set_ids:
            return {}
        rows = self._query_in(
            "SELECT RATE_SET_ID, RATE_TYPE, GRAIN, DESCRIPTION, SOURCE_REF FROM rates.RATE_SET "
            "WHERE RATE_SET_ID IN ({ids})",
            rate_set_ids,
        )
        return {int(r[0]): RateSetInfo(int(r[0]), _text(r[1]), _text(r[2]), _text(r[3]), _text(r[4]))
                for r in rows}

    def rate_values(self, rate_set_ids: Sequence[int], issue_age: Optional[int]) -> dict[int, dict]:
        """``{rate_set_id: {(issue_age, duration): rate}}``.

        Issue-age grains (IA, IA_DUR) are read for ``issue_age`` only; DUR, AA and
        SCALAR sets are read whole (AA holds the attained age in ISSUE_AGE).
        """
        if not rate_set_ids:
            return {}
        age = -1 if issue_age is None else int(issue_age)
        rows = self._query_in(
            "SELECT v.RATE_SET_ID, v.ISSUE_AGE, v.DURATION, v.RATE FROM rates.RATE_VALUE v "
            "JOIN rates.RATE_SET s ON s.RATE_SET_ID = v.RATE_SET_ID "
            "WHERE v.RATE_SET_ID IN ({ids}) AND (s.GRAIN NOT IN ('IA', 'IA_DUR') OR v.ISSUE_AGE = ?)",
            rate_set_ids, params_after=[age],
        )
        values: dict[int, dict] = {int(i): {} for i in rate_set_ids}
        for r in rows:
            values[int(r[0])][(int(r[1]), int(r[2]))] = r[3]
        return values

    # -- 2 PLAN ------------------------------------------------------------------

    def plan_assignments(self, company: str, plancode: str) -> list[PlanAssignment]:
        rows = self._query(
            "SELECT STATE, RATE_TYPE, SCALE, RATE_SET_ID FROM rates.RATE_ASSIGN_PLAN "
            "WHERE COMPANY = ? AND PLANCODE = ?",
            [company, plancode],
        )
        return [PlanAssignment(_text(r[0]), _text(r[1]), _text(r[2]), int(r[3])) for r in rows]

    # -- 3 FUND ------------------------------------------------------------------

    def fund_assignments(self, company: str, plancode: str) -> list[FundAssignment]:
        rows = self._query(
            "SELECT a.FUND, a.REIN_BLOCK, a.FUND_KEY, f.FUND_TYPE, f.SOURCE_KEY, f.DESCRIPTION "
            "FROM rates.RATE_ASSIGN_FUND a JOIN rates.FUND f ON f.FUND_KEY = a.FUND_KEY "
            "WHERE a.COMPANY = ? AND a.PLANCODE = ? ORDER BY a.FUND, a.REIN_BLOCK",
            [company, plancode],
        )
        return [FundAssignment(_text(r[0]), _text(r[1]), _text(r[2]), _text(r[3]), _text(r[4]),
                               _text(r[5])) for r in rows]

    def fund_rates(self, fund_keys: Sequence[str]) -> list[FundRate]:
        if not fund_keys:
            return []
        rows = self._query_in(
            "SELECT FUND_KEY, RATE_TYPE, SCALE, RATE_START, PERIOD, GUARANTEE_MONTHS, GUARANTEE_END_DATE, RATE "
            "FROM rates.RATE_VALUE_FUND WHERE FUND_KEY IN ({ids})",
            fund_keys,
        )
        return [FundRate(_text(r[0]), _text(r[1]), _text(r[2]), _date(r[3]), int(r[4]),
                         None if r[5] is None else int(r[5]), _date(r[6]), r[7]) for r in rows]

    # -- 4 DIV -------------------------------------------------------------------

    def div_assignments(self, company: str, plancode: str) -> list[DivAssignment]:
        rows = self._query(
            "SELECT SEX, RATE_CLASS, BAND, STATE, REIN, DIV_KEY, USER_KEY FROM rates.RATE_ASSIGN_DIV "
            "WHERE COMPANY = ? AND PLANCODE = ?",
            [company, plancode],
        )
        return [DivAssignment(_text(r[0]), _text(r[1]), _text(r[2]), _text(r[3]), _text(r[4]),
                              _text(r[5]), _key(r[6])) for r in rows]

    def div_schedules(self, div_keys: Sequence[str]) -> list[DivSchedule]:
        if not div_keys:
            return []
        rows = self._query_in(
            "SELECT DIV_KEY, USER_KEY, RECORD_TYPE, ISSUE_DATE_FROM, EFFECTIVE_FROM, EFFECTIVE_TO, RATE_SET_ID, "
            "PUA_PARTICIPATING, PUA_KEY, PUA_USER_KEY FROM rates.RATE_SCHEDULE_DATE_DIV WHERE DIV_KEY IN ({ids})",
            div_keys,
        )
        return [DivSchedule(_text(r[0]), _key(r[1]), _text(r[2]), _date(r[3]), _date(r[4]), _date(r[5]),
                            int(r[6]), None if r[7] is None else _text(r[7]),
                            None if r[8] is None else _text(r[8]),
                            None if r[9] is None else _key(r[9])) for r in rows]

    def div_values(self, rate_set_ids: Sequence[int], issue_ages: Sequence[int]) -> dict[int, dict]:
        """``{rate_set_id: {(issue_age, duration): DivValue}}`` for the given issue ages."""
        if not rate_set_ids or not issue_ages:
            return {}
        ages = [int(a) for a in dict.fromkeys(issue_ages)]
        rows = self._query_in(
            "SELECT RATE_SET_ID, ISSUE_AGE, DURATION, DIV_RATE, PUA_RATE, OYT_RATE FROM rates.RATE_VALUE_DIV "
            "WHERE RATE_SET_ID IN ({ids}) AND ISSUE_AGE IN (" + _placeholders(len(ages)) + ")",
            rate_set_ids, params_after=ages,
        )
        values: dict[int, dict] = {int(i): {} for i in rate_set_ids}
        for r in rows:
            values[int(r[0])][(int(r[1]), int(r[2]))] = DivValue(r[3], r[4], r[5])
        return values
