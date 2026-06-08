"""Commutation-function actuarial engine (pure Python, no DB).

Builds the classic commutation columns (Dx, Nx, Cx, Mx, Rx) from a mortality
table + interest rate, then exposes net single premiums, annuities, endowment
insurance, net level premiums, and the Fackler reserve recursion for rolling
reserves forward or backward.

Everything is parameterized so it can be called flexibly:

    table = MortalityTable.from_rates(qx_list, start_age=0, sex="M")
    basis = CommutationFunctions.build(table, interest_rate=0.04,
                                       substandard=SubstandardRating(2.0, 5.0),
                                       issue_age=45)
    nsp   = basis.endowment_insurance(x=60, n=40)      # A_{60:40}
    ann   = basis.annuity_due(x=60, n=40)              # ä_{60:40}
    P     = basis.net_level_premium(60, 40, benefit=100000, endowment=100000)

The commutation values only ever appear as ratios, so the radix and the absolute
discount offset cancel — results are invariant to those choices.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Union

Number = Union[int, float]
AgeFunc = Union[Number, Callable[[int], Number]]


@dataclass
class MortalityTable:
    """Annual mortality rates qx for contiguous ages from ``min_age``.

    The table is treated as terminating at ``omega = min_age + len(rates)``:
    q is 1.0 at/after omega (no survivors). If the supplied rates do not already
    end at 1.0 that is fine — survivorship simply hits zero at omega.
    """

    rates: List[float]
    min_age: int = 0
    name: str = ""
    sex: str = ""

    @classmethod
    def from_rates(
        cls,
        rates: Sequence[Number],
        start_age: int = 0,
        name: str = "",
        sex: str = "",
    ) -> "MortalityTable":
        return cls(rates=[float(r) for r in rates], min_age=int(start_age), name=name, sex=sex)

    @property
    def omega(self) -> int:
        """First age at which there are no survivors."""
        return self.min_age + len(self.rates)

    def q(self, age: int) -> float:
        if age < self.min_age:
            return self.rates[0] if self.rates else 1.0
        idx = age - self.min_age
        if idx >= len(self.rates):
            return 1.0
        return self.rates[idx]


@dataclass
class SubstandardRating:
    """Substandard mortality adjustment.

    rated q = min(1, base_q * table_multiple + flat_extra_per_1000 / 1000),
    with the flat extra optionally ceasing after ``flat_extra_years`` from issue.
    """

    table_multiple: float = 1.0
    flat_extra_per_1000: float = 0.0
    flat_extra_years: Optional[int] = None  # None = for life

    def adjust(self, base_q: float, duration: int) -> float:
        rated = base_q * self.table_multiple
        if self.flat_extra_per_1000 and (
            self.flat_extra_years is None or duration < self.flat_extra_years
        ):
            rated += self.flat_extra_per_1000 / 1000.0
        return min(max(rated, 0.0), 1.0)


@dataclass
class CommutationFunctions:
    """Commutation columns Dx/Nx/Cx/Mx/Rx for one mortality + interest basis."""

    interest_rate: float
    min_age: int
    max_age: int                    # last age with a D value (= omega)
    D: Dict[int, float] = field(default_factory=dict)
    N: Dict[int, float] = field(default_factory=dict)
    C: Dict[int, float] = field(default_factory=dict)
    M: Dict[int, float] = field(default_factory=dict)
    R: Dict[int, float] = field(default_factory=dict)
    table_name: str = ""

    # ── construction ─────────────────────────────────────────────────────
    @classmethod
    def build(
        cls,
        table: MortalityTable,
        interest_rate: float,
        substandard: Optional[SubstandardRating] = None,
        issue_age: Optional[int] = None,
        start_age: Optional[int] = None,
    ) -> "CommutationFunctions":
        """Build commutation columns.

        Args:
            table: mortality table (annual qx).
            interest_rate: annual effective interest rate.
            substandard: optional rating applied to every qx (flat-extra duration
                is measured from ``issue_age``).
            issue_age: issue age, for timing a flat extra. Defaults to ``start_age``.
            start_age: lowest age to tabulate. Defaults to the table's min age.
        """
        start = table.min_age if start_age is None else int(start_age)
        omega = table.omega
        issue = start if issue_age is None else int(issue_age)
        v = 1.0 / (1.0 + interest_rate)

        # Survivorship from a radix of 1.0 (ratios cancel the radix).
        lx: Dict[int, float] = {start: 1.0}
        for age in range(start, omega):
            dur = age - issue
            q = table.q(age)
            if substandard is not None:
                q = substandard.adjust(q, dur)
            lx[age + 1] = lx[age] * (1.0 - q)

        # Dx, Cx with the discount offset measured from ``start`` (cancels in ratios).
        D: Dict[int, float] = {}
        C: Dict[int, float] = {}
        for age in range(start, omega + 1):
            D[age] = (v ** (age - start)) * lx.get(age, 0.0)
        for age in range(start, omega):
            dx = lx[age] - lx.get(age + 1, 0.0)
            C[age] = (v ** (age - start + 1)) * dx
        # Limiting-age convention: any survivors at omega all die there
        # (q_omega = 1, l_{omega+1} = 0), so the death cohort closes cleanly and
        # the M_x = D_x - d*N_x identity holds for whole-life sums.
        C[omega] = (v ** (omega - start + 1)) * lx.get(omega, 0.0)

        # Reverse cumulative sums: Nx, Mx, then Rx = sum of Mx.
        N: Dict[int, float] = {}
        M: Dict[int, float] = {}
        R: Dict[int, float] = {}
        run_n = run_m = run_r = 0.0
        for age in range(omega, start - 1, -1):
            run_n += D.get(age, 0.0)
            run_m += C.get(age, 0.0)
            N[age] = run_n
            M[age] = run_m
        for age in range(omega, start - 1, -1):
            run_r += M.get(age, 0.0)
            R[age] = run_r

        return cls(
            interest_rate=interest_rate, min_age=start, max_age=omega,
            D=D, N=N, C=C, M=M, R=R, table_name=table.name,
        )

    # ── safe accessors (0 outside the tabulated range) ───────────────────
    def _D(self, age: int) -> float:
        return self.D.get(age, 0.0)

    def _N(self, age: int) -> float:
        if age <= self.min_age:
            return self.N.get(self.min_age, 0.0)
        return self.N.get(age, 0.0)

    def _C(self, age: int) -> float:
        return self.C.get(age, 0.0)

    def _M(self, age: int) -> float:
        if age <= self.min_age:
            return self.M.get(self.min_age, 0.0)
        return self.M.get(age, 0.0)

    # ── core present values (per $1 unless noted) ────────────────────────
    def discount_factor(self) -> float:
        """v = 1/(1+i)."""
        return 1.0 / (1.0 + self.interest_rate)

    def pure_endowment(self, x: int, n: int) -> float:
        """nEx = D_{x+n} / D_x — PV of $1 paid at x+n if alive."""
        dx = self._D(x)
        return self._D(x + n) / dx if dx else 0.0

    def term_insurance(self, x: int, n: int) -> float:
        """A^1_{x:n} = (M_x - M_{x+n}) / D_x — n-year term, $1 at end of death year."""
        dx = self._D(x)
        return (self._M(x) - self._M(x + n)) / dx if dx else 0.0

    def endowment_insurance(self, x: int, n: int) -> float:
        """A_{x:n} = (M_x - M_{x+n} + D_{x+n}) / D_x — term + pure endowment."""
        dx = self._D(x)
        if not dx:
            return 0.0
        return (self._M(x) - self._M(x + n) + self._D(x + n)) / dx

    def whole_life_insurance(self, x: int) -> float:
        """A_x = M_x / D_x."""
        dx = self._D(x)
        return self._M(x) / dx if dx else 0.0

    def annuity_due(self, x: int, n: int) -> float:
        """ä_{x:n} = (N_x - N_{x+n}) / D_x — n-year annuity-due, $1/yr."""
        dx = self._D(x)
        return (self._N(x) - self._N(x + n)) / dx if dx else 0.0

    def annuity_due_whole(self, x: int) -> float:
        """ä_x = N_x / D_x."""
        dx = self._D(x)
        return self._N(x) / dx if dx else 0.0

    def annuity_immediate(self, x: int, n: int) -> float:
        """a_{x:n} = ä_{x:n} - 1 + nEx — payments at year end."""
        return self.annuity_due(x, n) - 1.0 + self.pure_endowment(x, n)

    # ── premiums ─────────────────────────────────────────────────────────
    def net_level_premium(
        self,
        x: int,
        n: int,
        benefit: float = 1.0,
        endowment: Optional[float] = None,
        premium_years: Optional[int] = None,
    ) -> float:
        """Net level annual premium for an n-year endowment insurance.

        PV(benefits) = benefit * term + endowment * pure_endowment.
        Premiums are an annuity-due over ``premium_years`` (default n).

        endowment defaults to ``benefit`` (a standard endowment insurance); pass
        endowment=0 for level n-year term, or a different face for an endowment
        that differs from the death benefit.
        """
        endow = benefit if endowment is None else endowment
        pay_years = n if premium_years is None else premium_years
        pv_benefit = benefit * self.term_insurance(x, n) + endow * self.pure_endowment(x, n)
        ann = self.annuity_due(x, pay_years)
        return pv_benefit / ann if ann else 0.0

    def reserve(
        self,
        x: int,
        n: int,
        t: int,
        benefit: float = 1.0,
        endowment: Optional[float] = None,
    ) -> float:
        """Prospective net premium reserve at duration t of an n-year endowment.

        tV = PV(future benefits) - P * PV(future premiums), all at age x+t.
        """
        endow = benefit if endowment is None else endowment
        prem = self.net_level_premium(x, n, benefit=benefit, endowment=endow)
        future_ben = (
            benefit * self.term_insurance(x + t, n - t)
            + endow * self.pure_endowment(x + t, n - t)
        )
        future_prem = self.annuity_due(x + t, n - t)
        return future_ben - prem * future_prem

    # ── Fackler reserve roll (commutation form) ──────────────────────────
    def roll_reserve_forward(self, reserve: float, age: int, premium: float, benefit: float) -> float:
        """One-year Fackler accumulation: _{age+1}V from _{age}V.

        _{t+1}V = (_tV + P)(D_x / D_{x+1}) - B(C_x / D_{x+1}).
        """
        d_next = self._D(age + 1)
        if not d_next:
            return 0.0
        return (reserve + premium) * (self._D(age) / d_next) - benefit * (self._C(age) / d_next)

    def roll_reserve_backward(self, reserve_next: float, age: int, premium: float, benefit: float) -> float:
        """Inverse Fackler step: _{age}V from _{age+1}V."""
        d_age = self._D(age)
        if not d_age:
            return 0.0
        return (
            reserve_next * (self._D(age + 1) / d_age)
            + benefit * (self._C(age) / d_age)
            - premium
        )

    def roll_reserve(
        self,
        reserve: float,
        from_age: int,
        to_age: int,
        premium: AgeFunc = 0.0,
        benefit: AgeFunc = 0.0,
    ) -> float:
        """Roll a reserve from ``from_age`` to ``to_age`` (either direction).

        ``premium`` and ``benefit`` may be constants or callables of attained age
        (the age at the *start* of the year being rolled).
        """
        def at(value: AgeFunc, age: int) -> float:
            return float(value(age)) if callable(value) else float(value)

        val = reserve
        if to_age >= from_age:
            for age in range(from_age, to_age):
                val = self.roll_reserve_forward(val, age, at(premium, age), at(benefit, age))
        else:
            for age in range(from_age - 1, to_age - 1, -1):
                val = self.roll_reserve_backward(val, age, at(premium, age), at(benefit, age))
        return val


# ── standalone Fackler primitives (q/i form, no commutation needed) ──────
def fackler_forward(reserve: float, premium: float, benefit: float, q: float, i: float) -> float:
    """_{t+1}V = [(_tV + P)(1+i) - B*q] / (1-q)."""
    p = 1.0 - q
    if p == 0.0:
        raise ValueError("q = 1 has no surviving cohort to roll forward")
    return ((reserve + premium) * (1.0 + i) - benefit * q) / p


def fackler_backward(reserve_next: float, premium: float, benefit: float, q: float, i: float) -> float:
    """_tV = [_{t+1}V(1-q) + B*q] / (1+i) - P."""
    return (reserve_next * (1.0 - q) + benefit * q) / (1.0 + i) - premium
