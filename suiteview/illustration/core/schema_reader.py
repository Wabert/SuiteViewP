"""Memoized, read-only access to UL_Rates schema ``rates`` for illustration rate loaders.

ISWL and par whole life load their rates from the four-structure tables through
``RatesSchemaRepository``. A live load shares one process-wide cache (schema reads
are immutable between rate loads); a caller-supplied repository (tests, scripts)
gets a private cache.
"""
from __future__ import annotations

import threading
from typing import Callable, Dict, Optional, Tuple

from suiteview.core.rates_schema import RatesSchemaRepository

_SHARED_CACHE: Dict[tuple, object] = {}
_CACHE_LOCK = threading.Lock()


def clear_schema_rate_cache() -> None:
    """Forget memoized schema reads (e.g. after a rate load)."""
    with _CACHE_LOCK:
        _SHARED_CACHE.clear()


class SchemaReader:
    """Memoized reads of schema ``rates``; results are immutable and shareable."""

    def __init__(self, repo, cache: Dict[tuple, object]):
        self._repo = repo
        self._cache = cache

    def _get(self, key: tuple, fetch: Callable[[], object]):
        with _CACHE_LOCK:
            if key in self._cache:
                return self._cache[key]
        value = fetch()
        with _CACHE_LOCK:
            return self._cache.setdefault(key, value)

    def rate_types(self):
        return self._get(("rate_types",), lambda: dict(self._repo.rate_types()))

    def plan_defs(self, plancode: str):
        return self._get(("plan_defs", plancode), lambda: tuple(self._repo.plan_defs(plancode)))

    def plan_attrs(self, company: str, plancode: str):
        return self._get(("plan_attrs", company, plancode),
                         lambda: tuple(self._repo.plan_attrs(company, plancode)))

    def plan_bands(self, company: str, plancode: str):
        return self._get(("plan_bands", company, plancode),
                         lambda: tuple(self._repo.plan_bands(company, plancode)))

    def plan_subseries(self, company: str, plancode: str):
        return self._get(("subseries", company, plancode),
                         lambda: tuple(self._repo.plan_subseries(company, plancode)))

    def cell_assignments(self, company: str, plancode: str):
        return self._get(("cells", company, plancode),
                         lambda: tuple(self._repo.cell_assignments(company, plancode)))

    def schedule_windows(self, schedule_id: int):
        return self._get(("windows", schedule_id),
                         lambda: tuple(self._repo.schedule_windows([schedule_id])))

    def rate_sets(self, rate_set_ids: Tuple[int, ...]):
        return self._get(("sets", rate_set_ids), lambda: dict(self._repo.rate_sets(list(rate_set_ids))))

    def rate_values(self, rate_set_ids: Tuple[int, ...], issue_age: Optional[int]):
        return self._get(("values", rate_set_ids, issue_age),
                         lambda: dict(self._repo.rate_values(list(rate_set_ids), issue_age)))

    def plan_assignments(self, company: str, plancode: str):
        return self._get(("plan_rates", company, plancode),
                         lambda: tuple(self._repo.plan_assignments(company, plancode)))

    def modal_factors(self, company: str, plancode: str):
        return self._get(("modefact", company, plancode),
                         lambda: tuple(self._repo.modal_factors(company, plancode)))

    def modal_factor_plancodes(self, company: str, prefix: str):
        return self._get(("modefact_plans", company, prefix),
                         lambda: tuple(self._repo.modal_factor_plancodes(company, prefix)))

    def fund_assignments(self, company: str, plancode: str):
        return self._get(("funds", company, plancode),
                         lambda: tuple(self._repo.fund_assignments(company, plancode)))

    def fund_rates(self, fund_keys: Tuple[str, ...]):
        return self._get(("fund_rates", fund_keys), lambda: tuple(self._repo.fund_rates(list(fund_keys))))

    def div_assignments(self, company: str, plancode: str):
        return self._get(("div_assign", company, plancode),
                         lambda: tuple(self._repo.div_assignments(company, plancode)))

    def div_schedules(self, div_keys: Tuple[str, ...]):
        return self._get(("div_sched", div_keys), lambda: tuple(self._repo.div_schedules(list(div_keys))))

    def div_values(self, rate_set_ids: Tuple[int, ...], issue_ages: Tuple[int, ...]):
        return self._get(("div_values", rate_set_ids, issue_ages),
                         lambda: dict(self._repo.div_values(list(rate_set_ids), list(issue_ages))))


class open_schema_reader:
    """Context manager: a reader over the given repository, or an owned live one."""

    def __init__(self, repo=None):
        self._repo = repo
        self._owned = None

    def __enter__(self) -> SchemaReader:
        if self._repo is not None:
            return SchemaReader(self._repo, {})
        self._owned = RatesSchemaRepository()
        return SchemaReader(self._owned, _SHARED_CACHE)

    def __exit__(self, *exc) -> None:
        if self._owned is not None:
            self._owned.close()
