"""Premium paid to cover a policy change's partial surrender charge.

Option *Apply premium needed to cover policy change surrender charge*
(``IllustrationOptions.cover_change_surrender_charge``, off by default). The
administration system refuses a specified face decrease, or the face reduction
of a DB option A to B change, whose partial surrender charge (PSC) exceeds the
surrender value (``decrease_charge_check``). With the option on, the engine
solves the premium that lifts the surrender value to the largest PSC of the
month's changes and applies it after the month's withdrawal and before the DB
option change and face change: grossed up for the premium load, tested against
the pre-change guideline (GPT) room, 7-pay room (TAMRA years 1-7) and CVAT
necessary premium, and added to premiums year-to-date, premiums to date and
cost basis. A premium those limits refuse stops the illustration
(:class:`ChangeChargePremiumRejectedError`).

The guaranteed projection does not re-solve: it replays the current side's
premium as a locked premium (``input_compiler.CHANGE_CHARGE_SUBTYPE``,
``guaranteed_projection.lock_values``).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, Optional

REJECTED_TITLE = "Policy Change Premium Not Accepted"

_EPS = 0.005


class ChangeChargePremiumRejectedError(ValueError):
    """The premium needed to cover a policy change's PSC is not accepted."""


@dataclass(frozen=True)
class ChangePremiumRoom:
    """Premium room before the change; None = that limit does not apply."""

    guideline: Optional[float] = None
    seven_pay: Optional[float] = None
    npt: Optional[float] = None

    def refusals(self, gross: float) -> list[str]:
        """The limits ``gross`` exceeds, worded for the user."""
        refused = []
        for room, label in (
            (self.guideline, "guideline premium limit"),
            (self.seven_pay, "7-pay (TAMRA) premium limit"),
            (self.npt, "CVAT necessary premium limit"),
        ):
            if room is not None and gross > room + _EPS:
                refused.append(f"the remaining {label} of {_money(room)}")
        return refused


@dataclass(frozen=True)
class ChangeChargePremium:
    """The month's policy-change premium and how it was derived."""

    change_date: Optional[date]
    surrender_value_before: float   # AV after the withdrawal - full SC - debt
    largest_psc: float              # largest partial surrender charge of the month's changes, after the premium
    net_needed: float               # net premium the surrender value is short (0 if locked)
    room: ChangePremiumRoom
    gross: float
    premium_load: float
    net: float
    av_after: float
    premiums_to_date_after: float
    cost_basis_after: float
    locked: bool = False            # replayed from the current side (guaranteed run)

    def detail(self) -> Dict[str, object]:
        """Values-tab columns (``DETAIL_COLUMNS``) keyed by their display names."""
        return dict(zip(DETAIL_COLUMNS, (
            self.surrender_value_before,
            self.largest_psc,
            self.net_needed,
            _room_cell(self.room.guideline),
            _room_cell(self.room.seven_pay),
            _room_cell(self.room.npt),
            self.gross,
            self.premium_load,
            self.net,
            self.av_after,
            self.premiums_to_date_after,
            self.cost_basis_after,
        )))


DETAIL_COLUMNS = (
    "Chg Prem SV Before",
    "Chg Prem Largest PSC",
    "Chg Prem Net Needed",
    "Chg Prem GP Room",
    "Chg Prem 7-Pay Room",
    "Chg Prem NPT Room",
    "Chg Prem Gross",
    "Chg Prem Load",
    "Chg Prem Net",
    "AV after Chg Prem",
    "PremTD after Chg Prem",
    "CostBasis after Chg Prem",
)
ROOM_COLUMNS = ("Chg Prem GP Room", "Chg Prem 7-Pay Room", "Chg Prem NPT Room")


def _room_cell(room: Optional[float]) -> object:
    return "" if room is None else float(room)


def _money(value: float) -> str:
    return f"-${-value:,.2f}" if value < 0 else f"${value:,.2f}"


def rejected_message(gross: float, change_date: Optional[date], refused: list[str]) -> str:
    """Why the illustration cannot run: the covering premium is not accepted."""
    stamp = change_date.strftime("%m/%d/%Y") if change_date else "the change date"
    return (
        f"The premium of {_money(gross)} needed to cover the partial surrender charge of "
        f"the policy change effective {stamp} cannot be accepted: it exceeds "
        f"{' and '.join(refused)}.\n\n"
        "The administration system will not process the face decrease without enough "
        "surrender value to cover its partial surrender charge, so the illustration "
        "cannot be run. Reduce the decrease or move the change to a later date.")
