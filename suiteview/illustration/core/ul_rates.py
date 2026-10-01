"""RERUN's UL/IUL rates from UL_Rates schema ``rates``.

``ULRates`` answers every rate the UL/IUL illustration engine loads, in the engine's
own vocabulary and shapes (1-indexed schedules by coverage year, single values),
from the four-structure tables in schema ``rates`` (``RatesSchemaRepository``). The
legacy dbo ``Select_RATE_*`` views are never read. ISWL, par whole life and term load
their own schema rates (``iswl_rates``, ``parwl.rates``, ``term.rates``).

Engine name -> schema rate type:

======================  ==========================================================
``COI`` / ``BENCOI``    CELL ``COI`` (benefit ``''`` / the benefit's type+subtype)
``EPU``                 CELL ``EPU``
``MFEE``                CELL ``MFEE``
``TPP``                 CELL ``PREMLOAD_PCT`` (load up to the load target)
``EPP``                 CELL ``PREMLOAD_EXS`` (load above target); plans without
                        an excess load charge ``PREMLOAD_PCT`` on every premium
``SCR``                 CELL ``SCR`` (the issue state's cell, else ``**``)
``SHADOW_INT``          CELL ``SHADOW_INT`` (shadow account only)
``MTP`` / ``BENMTP``    CELL ``MTP``
``CTP`` / ``BENCTP``    CELL ``CTP``
``TBL1MTP``/``TBL1CTP`` CELL ``MTP_TBL1`` / ``CTP_TBL1`` (``None`` = not loaded)
``GINT``                PLAN ``GINT``
``DBD``                 PLAN or CELL ``DB_DISCOUNT``
======================  ==========================================================

Scales: ``scale=1`` is current (``C``), ``0`` guaranteed (``G``) and ``SHADOW``
(``"S"``) the shadow account's rates on the *base* plancode (schema ``rates`` keeps
them there; the legacy ``CCV*`` plancodes are only ``PLAN_ATTR
SHADOW_LEGACY_PLANCODE``). Issue-dated kinds (targets, SCR) have one scale ``G``.

Dates: a rate type whose ``RATE_TYPE.DATE_MEANING`` is ``CALENDAR`` (COI, EPU, MFEE,
premium loads) takes each coverage year's rate from the schedule window in effect on
that year's start; ``ISSUE`` rates use the window on the issue date. A schedule with
several windows therefore needs the coverage issue date (``RatesError`` otherwise).

Cells: exact first, then the schema's "does not vary" keys (unisex ``U``, class
``0``/``*``, band ``0``, state ``**``) via PolView's ``schema_rates.choose_cell``; a
unisex (``U``) policy on a plan loaded under a single sex uses that sex's cells.
Bands come from ``PLAN_BAND`` (``rates.fn_BAND``: latest spec on/before the policy
issue date, lowest upper limit at or above the amount).

A plancode that schema ``rates`` does not load, like a rate a loaded plan does not
carry, answers ``None`` ("not available") so the engine's own required/optional rules
apply: a missing COI raises ``RateLookupError`` naming the lookup. ``ULRates.plan``
raises for an unloaded plancode when a caller needs the plan itself.
"""
from __future__ import annotations

import threading
from dataclasses import replace
from datetime import date, datetime
from decimal import ROUND_CEILING, Decimal
from typing import Dict, List, Optional, Sequence

from dateutil.relativedelta import relativedelta

from suiteview.core.joint_survivor_rates import JointSurvivorRateSource
from suiteview.core.rates_errors import RatesError
from suiteview.core.rates_schema import PlanDef, RatesSchemaRepository, ScheduleWindow
from suiteview.illustration.core.schema_reader import SchemaReader, shared_schema_reader
from suiteview.polview.models.schema_rates import (
    UNISEX,
    RateKey,
    band_for_amount,
    choose_cell,
    last_year,
    rate_at,
    rates_sex,
    resolve_plan,
)

CURRENT = 1
GUARANTEED = 0
SHADOW = "S"

_CELL_SCHEDULE_TYPES = {
    "COI": "COI",
    "BENCOI": "COI",
    "EPU": "EPU",
    "MFEE": "MFEE",
    "TPP": "PREMLOAD_PCT",
    "EPP": "PREMLOAD_EXS",
    "SCR": "SCR",
    "SHADOW_INT": "SHADOW_INT",
    "DBD": "DB_DISCOUNT",
}
_CELL_SINGLE_TYPES = {
    "MTP": "MTP",
    "BENMTP": "MTP",
    "CTP": "CTP",
    "BENCTP": "CTP",
    "TBL1MTP": "MTP_TBL1",
    "TBL1CTP": "CTP_TBL1",
}
_PLAN_SCHEDULE_TYPES = {"GINT": "GINT", "DBD": "DB_DISCOUNT"}
_BENEFIT_KINDS = frozenset({"BENCOI", "BENMTP", "BENCTP"})
# Kinds with one stored scale: G (or S for the shadow account).
_SINGLE_SCALE_KINDS = frozenset({"SCR", "MTP", "BENMTP", "CTP", "BENCTP", "TBL1MTP", "TBL1CTP"})
_INDEX_PARAMETERS = {
    "IDX_FLOOR": "floor",
    "IDX_CAP": "cap",
    "IDX_PART": "participation",
    "IDX_SPREAD": "int_rate_spread",
    "IDX_SPEC": "specified_rate",
    "IDX_MULT": "multiplier",
    "IDX_ASSET": "asset_fee",
}
_INDEX_FUND_TYPE = "INDEX"
_CACHE_LOCK = threading.Lock()


def _as_date(value) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _scale_code(kind: str, scale) -> str:
    if scale == SHADOW:
        return SHADOW
    if kind in _SINGLE_SCALE_KINDS:
        return "G"
    if scale == CURRENT:
        return "C"
    if scale == GUARANTEED:
        return "G"
    raise RatesError(f"{kind} scale must be 1 (current), 0 (guaranteed) or 'S' (shadow), not {scale!r}.")


def _band_text(band) -> str:
    return "" if band is None else str(int(band))


def _rate_class(rateclass) -> str:
    text = str(rateclass or "").strip().upper()
    # RERUN rate class 0 is the nonsmoker class N.
    return "N" if text == "0" else text


class ULRates(JointSurvivorRateSource):
    """UL/IUL illustration rates from schema ``rates`` (see the module docstring).

    ``company`` is the policy company; it only matters for a plancode loaded under
    several companies (``resolve_plan``). Reads share the process-wide schema cache
    unless a ``repository`` is supplied (tests, tools).
    """

    _cache: Dict[tuple, object] = {}

    def __init__(self, company: str = "", repository: Optional[RatesSchemaRepository] = None):
        self._company = str(company or "").strip()
        if repository is None:
            self._schema_repo = RatesSchemaRepository()
            self._results = ULRates._cache
            self._reader = shared_schema_reader(self._schema_repo)
        else:
            self._schema_repo = repository
            self._results = {}
            self._reader = SchemaReader(repository, {})
        # The joint survivor lookups (JointSurvivorRateSource) memoize in ``_cache``.
        self._cache = self._results

    def __enter__(self) -> "ULRates":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self._close_schema()

    @classmethod
    def clear_cache(cls) -> None:
        """Forget cached schedules and schema reads (e.g. after a rate load)."""
        from suiteview.illustration.core.schema_reader import clear_schema_rate_cache

        with _CACHE_LOCK:
            cls._cache.clear()
        clear_schema_rate_cache()
        JointSurvivorRateSource._joint_companies.clear()

    def _memo(self, key: tuple, compute):
        with _CACHE_LOCK:
            if key in self._results:
                return self._results[key]
        value = compute()
        with _CACHE_LOCK:
            return self._results.setdefault(key, value)

    # -- plan ------------------------------------------------------------------

    def plan(self, plancode: str) -> PlanDef:
        """The plancode's ``PLAN_DEF`` row; raises when schema ``rates`` does not load it."""
        plancode = (plancode or "").strip().upper()
        plans = self._reader.plan_defs(plancode)
        if self._company:
            plan, note = resolve_plan(plans, self._company)
        elif len(plans) == 1:
            plan, note = plans[0], ""
        else:
            plan = None
            note = (f"loaded under companies {', '.join(sorted(p.company for p in plans))}; "
                    "a policy company is needed") if plans else ""
        if plan is None:
            detail = f" ({note})" if note else ""
            raise RatesError(f"Plancode {plancode or '<blank>'} is not loaded in UL_Rates schema rates{detail}.")
        return plan

    def _loaded_plan(self, plancode: str) -> Optional[PlanDef]:
        """The plan behind a rate lookup, or None when schema ``rates`` does not load the
        plancode at all (its rates are then "not available", as for a missing cell)."""
        if not self.is_loaded(plancode):
            return None
        return self.plan(plancode)

    def is_loaded(self, plancode: str) -> bool:
        """Whether schema ``rates`` loads the plancode (``PLAN_DEF``) under any company."""
        return bool(self._reader.plan_defs((plancode or "").strip().upper()))

    # -- schedules and single values ----------------------------------------------

    def get_rates(
        self,
        rate_type: str,
        plancode: str,
        issue_age: int = None,
        sex: str = None,
        rateclass: str = None,
        scale=CURRENT,
        band: int = None,
        benefit_type: str = "",
        state: str = None,
        issue_date=None,
    ) -> Optional[List]:
        """A 1-indexed schedule by coverage year (``None`` when the plan has no such rate).

        ``issue_date`` is the coverage's issue date: it dates CALENDAR windows and
        ISSUE-dated schedules. ``state`` selects a state-specific cell (surrender
        charges); ``benefit_type`` is the benefit's type + subtype for ``BENCOI``.
        """
        kind = (rate_type or "").strip().upper()
        plancode = (plancode or "").strip().upper()
        issue_date = _as_date(issue_date)
        if kind in _PLAN_SCHEDULE_TYPES and not (
            kind == "DBD" and issue_age is not None
        ):
            scale_code = SHADOW if scale == SHADOW else "G"
            key = ("PLAN", kind, plancode, scale_code, (state or "").strip().upper())
            return self._memo(key, lambda: self._plan_schedule(kind, plancode, scale_code, state))
        if kind not in _CELL_SCHEDULE_TYPES:
            raise RatesError(f"Unknown RERUN rate kind {rate_type!r}.")
        if issue_age is None:
            raise RatesError(f"{plancode} {kind} lookup needs an issue age.")
        benefit = (benefit_type or "").strip() if kind in _BENEFIT_KINDS else ""
        if kind in _BENEFIT_KINDS and not benefit:
            raise RatesError(f"{plancode} {kind} lookup needs a benefit type.")
        scale_code = _scale_code(kind, scale)
        cell = RateKey(rates_sex(sex or ""), _rate_class(rateclass), _band_text(band),
                       (state or "").strip().upper())
        key = ("CELL", kind, plancode, int(issue_age), cell, scale_code, benefit, issue_date)
        schedule = self._memo(key, lambda: self._cell_schedule(
            kind, plancode, int(issue_age), cell, scale_code, benefit, issue_date))
        if schedule is None and kind == "DBD":
            plan_scale = SHADOW if scale == SHADOW else "G"
            plan_key = ("PLAN", kind, plancode, plan_scale, (state or "").strip().upper())
            return self._memo(plan_key, lambda: self._plan_schedule(kind, plancode, plan_scale, state))
        return schedule

    def _single(self, kind: str, plancode: str, issue_age, sex, rateclass, band,
                benefit_type: str = "", issue_date=None, scale=None) -> Optional[float]:
        plancode = (plancode or "").strip().upper()
        if issue_age is None:
            raise RatesError(f"{plancode} {kind} lookup needs an issue age.")
        benefit = (benefit_type or "").strip() if kind in _BENEFIT_KINDS else ""
        if kind in _BENEFIT_KINDS and not benefit:
            raise RatesError(f"{plancode} {kind} lookup needs a benefit type.")
        scale_code = _scale_code(kind, scale)
        issue_date = _as_date(issue_date)
        cell = RateKey(rates_sex(sex or ""), _rate_class(rateclass), _band_text(band), "")
        key = ("SINGLE", kind, plancode, int(issue_age), cell, scale_code, benefit, issue_date)
        return self._memo(key, lambda: self._cell_single(
            kind, plancode, int(issue_age), cell, scale_code, benefit, issue_date))

    def get_mtp(self, plancode, issue_age, sex, rateclass, band, issue_date=None,
                scale=None) -> Optional[float]:
        """Minimum target premium per unit (``scale=SHADOW`` for the shadow account)."""
        return self._single("MTP", plancode, issue_age, sex, rateclass, band,
                            issue_date=issue_date, scale=scale)

    def get_ctp(self, plancode, issue_age, sex, rateclass, band, issue_date=None,
                scale=None) -> Optional[float]:
        """Commission target premium per unit."""
        return self._single("CTP", plancode, issue_age, sex, rateclass, band,
                            issue_date=issue_date, scale=scale)

    def get_tbl1_mtp(self, plancode, issue_age, sex, rateclass, band, issue_date=None,
                     scale=None) -> Optional[float]:
        """MTP add-on per table rating; ``None`` means not available (never zero)."""
        return self._single("TBL1MTP", plancode, issue_age, sex, rateclass, band,
                            issue_date=issue_date, scale=scale)

    def get_tbl1_ctp(self, plancode, issue_age, sex, rateclass, band, issue_date=None,
                     scale=None) -> Optional[float]:
        """CTP add-on per table rating; ``None`` means not available (never zero)."""
        return self._single("TBL1CTP", plancode, issue_age, sex, rateclass, band,
                            issue_date=issue_date, scale=scale)

    def get_ben_mtp(self, plancode, issue_age, sex, rateclass, band, benefit_type,
                    issue_date=None) -> Optional[float]:
        """A benefit's minimum target premium rate."""
        return self._single("BENMTP", plancode, issue_age, sex, rateclass, band, benefit_type, issue_date)

    def get_ben_ctp(self, plancode, issue_age, sex, rateclass, band, benefit_type,
                    issue_date=None) -> Optional[float]:
        """A benefit's commission target premium rate."""
        return self._single("BENCTP", plancode, issue_age, sex, rateclass, band, benefit_type, issue_date)

    def _assignment(self, plan: PlanDef, schema_type: str, benefit: str, cell: RateKey):
        rows = [a for a in self._reader.cell_assignments(plan.company, plan.plancode) if a.benefit == benefit]
        assignment, _notes = choose_cell(rows, schema_type, cell)
        if assignment is None and cell.sex == UNISEX:
            # A unisex policy on a plan whose rates are loaded under one sex only (the
            # rates do not vary by sex): that sex's cells are the plan's rates.
            sexes = {a.sex for a in rows if a.rate_type == schema_type}
            if len(sexes) == 1:
                assignment, _notes = choose_cell(rows, schema_type, replace(cell, sex=sexes.pop()))
        return assignment

    def _windows(self, assignment, scale_code: str) -> List[ScheduleWindow]:
        return sorted((w for w in self._reader.schedule_windows(assignment.schedule_id)
                       if w.scale == scale_code), key=lambda w: w.effective_from)

    @staticmethod
    def _window_for(windows: Sequence[ScheduleWindow], on: Optional[date], label: str) -> ScheduleWindow:
        if len(windows) == 1:
            return windows[0]
        if on is None:
            raise RatesError(f"{label} has several dated schedules; the lookup needs the coverage issue date.")
        window = next((w for w in windows if w.covers(on)), None)
        if window is None:
            raise RatesError(f"{label}: no schedule window covers {on:%m/%d/%Y}.")
        return window

    def _cell_schedule(self, kind: str, plancode: str, issue_age: int, cell: RateKey, scale_code: str,
                       benefit: str, issue_date: Optional[date]) -> Optional[List]:
        plan = self._loaded_plan(plancode)
        if plan is None:
            return None
        schema_type = _CELL_SCHEDULE_TYPES[kind]
        assignment = self._assignment(plan, schema_type, benefit, cell)
        windows = self._windows(assignment, scale_code) if assignment is not None else []
        if not windows and kind == "EPP":
            # No excess load on this scale: the premium load applies to every premium.
            schema_type = "PREMLOAD_PCT"
            assignment = self._assignment(plan, schema_type, benefit, cell)
            windows = self._windows(assignment, scale_code) if assignment is not None else []
        if not windows:
            return None
        label = f"{plancode} {schema_type}{' ' + benefit if benefit else ''} scale {scale_code}"
        calendar = self._reader.rate_types().get(schema_type) is not None and \
            self._reader.rate_types()[schema_type].date_meaning == "CALENDAR"
        set_ids = tuple(sorted({w.rate_set_id for w in windows}))
        sets = self._reader.rate_sets(set_ids)
        values = self._reader.rate_values(set_ids, issue_age)
        missing_sets = [i for i in set_ids if i not in sets]
        if missing_sets:
            raise RatesError(f"{label}: rate set {missing_sets[0]} is missing.")
        years = max(last_year(sets[i].grain, values.get(i, {}), issue_age) for i in set_ids)
        schedule: List = [None]
        for year in range(1, years + 1):
            on = issue_date + relativedelta(years=year - 1) if (calendar and issue_date) else issue_date
            window = self._window_for(windows, on, label)
            rate = rate_at(sets[window.rate_set_id].grain, values.get(window.rate_set_id, {}), issue_age, year)
            schedule.append(None if rate is None else float(rate))
        while len(schedule) > 1 and schedule[-1] is None:
            schedule.pop()
        if any(rate is None for rate in schedule[1:]):
            gap = schedule.index(None, 1)
            raise RatesError(f"{label} has no rate for coverage year {gap} (issue age {issue_age}).")
        return schedule if len(schedule) > 1 else None

    def _cell_single(self, kind: str, plancode: str, issue_age: int, cell: RateKey, scale_code: str,
                     benefit: str, issue_date: Optional[date]) -> Optional[float]:
        plan = self._loaded_plan(plancode)
        if plan is None:
            return None
        schema_type = _CELL_SINGLE_TYPES[kind]
        assignment = self._assignment(plan, schema_type, benefit, cell)
        if assignment is None:
            return None
        windows = self._windows(assignment, scale_code)
        if not windows:
            return None
        label = f"{plancode} {schema_type}{' ' + benefit if benefit else ''} scale {scale_code}"
        window = self._window_for(windows, issue_date, label)
        info = self._reader.rate_sets((window.rate_set_id,)).get(window.rate_set_id)
        if info is None:
            raise RatesError(f"{label}: rate set {window.rate_set_id} is missing.")
        values = self._reader.rate_values((window.rate_set_id,), issue_age).get(window.rate_set_id, {})
        rate = rate_at(info.grain, values, issue_age, 1)
        return None if rate is None else float(rate)

    def _plan_schedule(self, kind: str, plancode: str, scale_code: str, state) -> Optional[List]:
        plan = self._loaded_plan(plancode)
        if plan is None:
            return None
        schema_type = _PLAN_SCHEDULE_TYPES[kind]
        state = (state or "").strip().upper()
        rows = [a for a in self._reader.plan_assignments(plan.company, plan.plancode)
                if a.rate_type == schema_type and a.scale == scale_code and a.state in (state, "**")]
        if not rows:
            return None
        exact = [a for a in rows if a.state == state] or rows
        if len({a.rate_set_id for a in exact}) > 1:
            raise RatesError(f"{plancode} has several {schema_type} scale {scale_code} plan rate sets.")
        rate_set_id = exact[0].rate_set_id
        info = self._reader.rate_sets((rate_set_id,)).get(rate_set_id)
        if info is None:
            raise RatesError(f"{plancode} {schema_type}: rate set {rate_set_id} is missing.")
        values = self._reader.rate_values((rate_set_id,), None).get(rate_set_id, {})
        years = last_year(info.grain, values, 0)
        schedule: List = [None]
        for year in range(1, years + 1):
            rate = rate_at(info.grain, values, 0, year)
            if rate is None:
                raise RatesError(f"{plancode} {schema_type} has no rate for year {year}.")
            schedule.append(float(rate))
        return schedule if len(schedule) > 1 else None

    # -- bands -----------------------------------------------------------------

    def _band_rows(self, plancode: str):
        plan = self._loaded_plan(plancode)
        if plan is None:
            return None, ()
        return plan, self._reader.plan_bands(plan.company, plan.plancode)

    def get_band(self, plancode: str, specified_amount, issue_date=None) -> Optional[int]:
        """The numbered rate band for an amount (``PLAN_BAND``): 0 for an unbanded plan,
        ``None`` when the plancode is not loaded or has no ``PLAN_BAND`` rows.

        ``issue_date`` is the POLICY issue date for base (and base-banded rider)
        amounts, the rider's own issue date otherwise; without one the earliest
        band spec is used.
        """
        plan, bands = self._band_rows(plancode)
        if not bands:
            return None
        on = _as_date(issue_date) or min(b.issue_date_from for b in bands)
        spec, note = band_for_amount(bands, on, specified_amount)
        if spec is None:
            raise RatesError(f"{plan.plancode} has no rate band for {specified_amount}: {note}.")
        return int(spec.band)

    def get_band_break(self, plancode: str, band: int = 2, issue_date=None) -> Optional[float]:
        """The amount where ``band`` begins: the previous band's upper limit, rounded up to
        the cent (ratchet banding charges NAR up to it at band 1's rate)."""
        plan, bands = self._band_rows(plancode)
        limited = [b for b in bands if b.upper_limit is not None]
        if not limited:
            return None
        on = _as_date(issue_date) or min(b.issue_date_from for b in limited)
        starts = sorted({b.issue_date_from for b in limited if b.issue_date_from <= on})
        if not starts:
            return None
        below = [b for b in limited if b.issue_date_from == starts[-1] and b.band == str(int(band) - 1)]
        if len(below) != 1:
            return None
        return float(Decimal(str(below[0].upper_limit)).quantize(Decimal("0.01"), rounding=ROUND_CEILING))

    # -- index funds -----------------------------------------------------------

    def get_index_strategy_parameters(
        self, plancode: str, illustration_date, rga_indicator: str = "",
    ) -> Dict[str, Dict[str, float]]:
        """Current-scale index crediting parameters by fund on the illustration date.

        Each ``IDX_*`` fund rate is the latest current-scale rate starting on or before
        the illustration date, from the policy's reinsurance block (``R`` for RGA).
        A fund is returned only when every parameter is loaded for it.
        """
        on = _as_date(illustration_date)
        if not plancode or on is None:
            return {}
        rein = "R" if (rga_indicator or "").strip().upper() == "R" else ""
        plan = self._loaded_plan(plancode)
        if plan is None:
            return {}
        funds = [f for f in self._reader.fund_assignments(plan.company, plan.plancode)
                 if f.fund_type == _INDEX_FUND_TYPE and f.rein_block == rein]
        if not funds:
            return {}
        rates = self._reader.fund_rates(tuple(sorted({f.fund_key for f in funds})))
        result: Dict[str, Dict[str, float]] = {}
        for fund in funds:
            parameters: Dict[str, float] = {}
            for rate_type, name in _INDEX_PARAMETERS.items():
                rows = [r for r in rates if r.fund_key == fund.fund_key and r.rate_type == rate_type
                        and r.scale == "C" and r.rate_start <= on]
                if not rows:
                    continue
                latest = max(r.rate_start for r in rows)
                chosen = [r for r in rows if r.rate_start == latest]
                if len(chosen) != 1:
                    raise RatesError(f"{plan.plancode} fund {fund.fund} has several {rate_type} rates "
                                     f"starting {latest:%m/%d/%Y}.")
                parameters[name] = float(chosen[0].rate)
            if not parameters:
                continue
            if len(parameters) != len(_INDEX_PARAMETERS):
                missing = sorted(set(_INDEX_PARAMETERS.values()) - set(parameters))
                raise RatesError(f"{plan.plancode} fund {fund.fund} is missing index parameters "
                                 f"{', '.join(missing)} on {on:%m/%d/%Y}.")
            result[fund.fund.strip().upper()] = parameters
        return result
