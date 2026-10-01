"""Joint survivor UL rate lookups in UL_Rates schema ``rates``.

The 12 FFL joint survivor plans exist only in schema ``rates``. ``JointSurvivorRateSource``
reads them through ``RatesSchemaRepository`` and chooses cells EXACTLY: a joint COI
built from another insured's class or sex would be quietly wrong, so no unisex/class
fallback applies. It is the base of PolView's ``suiteview.core.rates.Rates`` and
RERUN's ``suiteview.illustration.core.ul_rates.ULRates``; the blended joint COI itself
is ``suiteview.core.joint_survivor_coi``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .local_dev import local_data_enabled
from .rates_errors import RatesError


class JointSurvivorRateSource:
    """Joint survivor plan facts and JS_Q/charge cells from schema ``rates``."""

    # Class-level caches: schema reads are immutable between rate loads.
    _cache: Dict[Any, Any] = {}
    _joint_companies: Dict[str, Optional[str]] = {}
    # dbo rate kinds ``joint_survivor_rates`` answers (or rejects, for COI).
    JOINT_RATE_TYPES = frozenset({"COI", "GINT", "MFEE", "TPP", "EPP", "SCR", "BENCOI"})

    _schema_repo = None

    def _schema(self):
        if local_data_enabled():
            raise RatesError(
                "UL_Rates schema 'rates' is not in the local SQLite rates database; "
                "joint survivor rates need live UL_Rates."
            )
        if self._schema_repo is None:
            from .rates_schema import RatesSchemaRepository

            self._schema_repo = RatesSchemaRepository()
        return self._schema_repo

    def _close_schema(self) -> None:
        if self._schema_repo is not None:
            self._schema_repo.close()
            self._schema_repo = None

    def joint_survivor_company(self, plancode: str) -> Optional[str]:
        """Company of a joint survivor plan (``rates.PLAN_ATTR`` LIVES=3), else None."""
        plancode = (plancode or "").strip()
        if not plancode or local_data_enabled():
            return None
        if plancode not in JointSurvivorRateSource._joint_companies:
            schema = self._schema()
            companies = sorted({
                plan.company for plan in schema.plan_defs(plancode)
                if any(a.attr == "LIVES" and a.value == "3"
                       for a in schema.plan_attrs(plan.company, plancode))
            })
            if len(companies) > 1:
                raise RatesError(
                    f"Joint survivor plan {plancode} is defined for several companies "
                    f"({', '.join(companies)}); the rate lookup needs one."
                )
            JointSurvivorRateSource._joint_companies[plancode] = companies[0] if companies else None
        return JointSurvivorRateSource._joint_companies[plancode]

    def get_plan_attributes(self, company: str, plancode: str) -> Dict[str, str]:
        """``rates.PLAN_ATTR`` ATTR -> VALUE for one company/plancode ({} if none)."""
        company, plancode = company.strip(), plancode.strip()
        key = ("PLAN_ATTR", company, plancode)
        if key not in self._cache:
            attrs: Dict[str, str] = {}
            for row in self._schema().plan_attrs(company, plancode):
                if row.attr in attrs:
                    raise RatesError(f"Duplicate rates.PLAN_ATTR {row.attr} for {company}/{plancode}.")
                attrs[row.attr] = row.value
            self._cache[key] = attrs
        return dict(self._cache[key])

    def get_plan_definition(self, company: str, plancode: str) -> Optional[Dict[str, Any]]:
        """The ``rates.PLAN_DEF`` row for one company/plancode as a dict, or None."""
        company, plancode = company.strip(), plancode.strip()
        key = ("PLAN_DEF", company, plancode)
        if key not in self._cache:
            plans = [p for p in self._schema().plan_defs(plancode) if p.company == company]
            if len(plans) > 1:
                raise RatesError(f"Duplicate rates.PLAN_DEF rows for {company}/{plancode}.")
            self._cache[key] = None if not plans else {
                "PRODUCT_FAMILY": plans[0].product_family,
                "COVERAGE_ROLE": plans[0].coverage_role,
                "DESCRIPTION": plans[0].description,
                **dict(plans[0].facts),
            }
        cached = self._cache[key]
        return dict(cached) if cached is not None else None

    def get_joint_survivor_q(
        self, company: str, plancode: str, scale: str, sex: str, rate_class: str, issue_age: int,
    ) -> Dict[int, float]:
        """One insured's single-life JS_Q (annual q per $1) by duration.

        Rate type JS_Q, no benefit, state ``**``, band 0, the insured's exact sex
        and class. Unisex plans store the same rates under M and F, so callers
        pass the insured's own sex.
        """
        if scale not in ("C", "G"):
            raise RatesError(f"JS_Q scale must be C or G, not {scale!r}.")
        cells = self._joint_cells(company.strip(), plancode.strip(), "JS_Q", scale, int(issue_age))
        return dict(cells.get((sex, rate_class), {}))

    def joint_survivor_rate_classes(self, company: str, plancode: str) -> List[str]:
        """Rate classes a joint plan loads JS_Q cells for (either sex), sorted."""
        company, plancode = company.strip(), plancode.strip()
        return sorted({
            a.rate_class for a in self._joint_assignments(company, plancode)
            if a.rate_type == "JS_Q" and not a.benefit and a.state == "**"
            and a.band == "0" and not a.subseries
        })

    def _joint_assignments(self, company: str, plancode: str):
        key = ("RATES_ASSIGN", company, plancode)
        if key not in self._cache:
            self._cache[key] = self._schema().cell_assignments(company, plancode)
        return self._cache[key]

    def _joint_cells(
        self, company: str, plancode: str, rate_type: str, scale: str, issue_age: int,
        benefit: str = "",
    ) -> Dict[Tuple[str, str], Dict[int, float]]:
        """All (sex, class) duration schedules of one CELL rate type at an issue age.

        Joint plans are unbanded (band 0) with all-state (``**``) cells. A cell
        with several effective windows for the scale raises: the illustration
        engine has no dated rate switch for the blended joint COI, so it must not
        silently pick one.
        """
        key = ("RATES_CELL", company, plancode, rate_type, scale, issue_age, benefit)
        if key in self._cache:
            return self._cache[key]
        schema = self._schema()
        assignments = [
            a for a in self._joint_assignments(company, plancode)
            if a.rate_type == rate_type and a.benefit == benefit
            and a.state == "**" and a.band == "0" and not a.subseries
        ]
        windows: Dict[int, list] = {}
        for window in schema.schedule_windows([a.schedule_id for a in assignments]):
            if window.scale == scale:
                windows.setdefault(window.schedule_id, []).append(window)
        rate_sets: Dict[Tuple[str, str], int] = {}
        for a in assignments:
            found = windows.get(a.schedule_id, [])
            if not found:
                continue
            if len(found) > 1 or (a.sex, a.rate_class) in rate_sets:
                raise RatesError(
                    f"{plancode} {rate_type} {a.sex}/{a.rate_class} scale {scale} has several "
                    "effective windows or cells; an illustration needs exactly one."
                )
            rate_sets[(a.sex, a.rate_class)] = found[0].rate_set_id
        values = schema.rate_values(sorted(set(rate_sets.values())), issue_age)
        cells: Dict[Tuple[str, str], Dict[int, float]] = {}
        for cell, rate_set_id in rate_sets.items():
            schedule = {}
            for (age, duration), rate in values.get(rate_set_id, {}).items():
                if age != issue_age:
                    continue
                if rate is None:
                    raise RatesError(f"NULL {rate_type} rate for {plancode} at duration {duration}.")
                schedule[int(duration)] = float(rate)
            cells[cell] = schedule
        self._cache[key] = cells
        return cells

    def _joint_plan_rate(self, company: str, plancode: str, rate_type: str,
                         scale: str) -> Dict[int, float]:
        """A PLAN rate type's duration schedule (state ``**``), e.g. GINT."""
        schema = self._schema()
        rate_set_ids = [
            a.rate_set_id for a in schema.plan_assignments(company, plancode)
            if a.rate_type == rate_type and a.scale == scale and a.state == "**"
        ]
        if len(rate_set_ids) > 1:
            raise RatesError(f"{plancode} has several {rate_type} {scale} plan rate sets.")
        if not rate_set_ids:
            return {}
        values = schema.rate_values(rate_set_ids, None).get(rate_set_ids[0], {})
        return {int(duration): float(rate) for (_age, duration), rate in values.items()}

    @staticmethod
    def _one_indexed(schedule: Dict[int, float], label: str) -> Optional[List[float]]:
        if not schedule:
            return None
        durations = sorted(schedule)
        if durations != list(range(1, durations[-1] + 1)):
            raise RatesError(f"{label} is not a complete schedule from duration 1.")
        return [None] + [schedule[d] for d in durations]

    def joint_survivor_rates(
        self, rate_type: str, company: str, plancode: str, issue_age: Optional[int],
        sex: Optional[str], rateclass: Optional[str], scale: Optional[int], benefit_type: str,
    ) -> Optional[List[float]]:
        """A dbo-named rate kind for a joint survivor plan, answered from schema ``rates``.

        1-indexed schedules, scale 1 = C, 0 = G; units verified equal to dbo on
        plans loaded in both (MFEE, PREMLOAD_PCT, SCR, COI).
        """
        rate_type = rate_type.upper()
        if rate_type == "COI":
            raise RatesError(
                f"{plancode} is a joint survivor plan: its base COI is the blended "
                "two-life JointCOI (suiteview.core.joint_survivor_coi), not an IAF rate."
            )
        if rate_type == "GINT":
            return self._one_indexed(
                self._joint_plan_rate(company, plancode, "GINT", "G"), f"{plancode} GINT")
        source = {
            "MFEE": ("MFEE", None, ""),
            "TPP": ("PREMLOAD_PCT", None, ""),
            "EPP": ("PREMLOAD_PCT", None, ""),
            "SCR": ("SCR", "G", ""),
            "BENCOI": ("COI", None, benefit_type or ""),
        }.get(rate_type)
        if source is None:
            # Targets are VP/MS (not loaded); these plans have no EPU or bands.
            # Callers treat None as "not available".
            return None
        if issue_age is None:
            raise RatesError(f"{plancode} {rate_type} lookup needs an issue age.")
        schema_type, fixed_scale, benefit = source
        if rate_type == "BENCOI" and not benefit:
            raise RatesError(f"{plancode} benefit COI lookup needs a benefit code.")
        scale_code = fixed_scale or ("G" if scale == 0 else "C")
        cells = self._joint_cells(company, plancode, schema_type, scale_code, int(issue_age), benefit)
        schedule = self._select_joint_cell(cells, sex, rateclass, benefit)
        label = f"{plancode} {schema_type}{' ' + benefit if benefit else ''} {scale_code} age {issue_age}"
        return self._one_indexed(schedule, label)

    @staticmethod
    def _select_joint_cell(
        cells: Dict[Tuple[str, str], Dict[int, float]], sex: Optional[str],
        rateclass: Optional[str], benefit: str,
    ) -> Dict[int, float]:
        """The (sex, class) cell; benefits may be keyed generically (e.g. M/K, F/*).

        Base cells are loaded for every joint sex/class, so they must match
        exactly. Benefit rates that don't vary by class are loaded once per sex
        (class ``*`` or one IAF class) or once in total; use that only when it
        is the sole candidate.
        """
        sex, rateclass = (sex or "").strip(), (rateclass or "").strip()
        if (sex, rateclass) in cells:
            return cells[(sex, rateclass)]
        if not cells:
            return {}
        if not benefit:
            raise RatesError(f"No rate for sex {sex!r} class {rateclass!r}.")
        if (sex, "*") in cells:
            return cells[(sex, "*")]
        for candidates in ([k for k in cells if k[0] == sex], list(cells)):
            if len(candidates) == 1:
                return cells[candidates[0]]
        raise RatesError(
            f"Benefit {benefit} has no rate for sex {sex!r} class {rateclass!r} "
            f"and several candidates ({sorted(cells)})."
        )

    def clear_joint_cache(self) -> None:
        self._cache.clear()
        JointSurvivorRateSource._joint_companies.clear()
