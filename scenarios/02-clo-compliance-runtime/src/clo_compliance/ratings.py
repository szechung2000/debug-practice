"""Point-in-time agency ratings and Moody's rating factors.

The compliance tests must use the rating that was in force on the run date.
The ratings feed is a history of rating actions, and it can contain actions
dated after the run date when we rerun an earlier date.
"""
from __future__ import annotations

import logging
from datetime import date

import pandas as pd

log = logging.getLogger(__name__)

MOODYS_SCALE = ["Aaa", "Aa1", "Aa2", "Aa3", "A1", "A2", "A3", "Baa1", "Baa2", "Baa3",
                "Ba1", "Ba2", "Ba3", "B1", "B2", "B3", "Caa1", "Caa2", "Caa3", "Ca", "C"]
SP_SCALE = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-",
            "BB+", "BB", "BB-", "B+", "B", "B-", "CCC+", "CCC", "CCC-", "CC", "C"]
RATING_FACTOR = {
    "Aaa": 1, "Aa1": 10, "Aa2": 20, "Aa3": 40, "A1": 70, "A2": 120, "A3": 180,
    "Baa1": 260, "Baa2": 360, "Baa3": 610, "Ba1": 940, "Ba2": 1350, "Ba3": 1766,
    "B1": 2220, "B2": 2720, "B3": 3490, "Caa1": 4770, "Caa2": 6500, "Caa3": 8070,
    "Ca": 10000, "C": 10000,
}
UNRATED_MOODYS = "Caa3"
CCC_MOODYS_NOTCH = MOODYS_SCALE.index("Caa1")
CCC_SP_NOTCH = SP_SCALE.index("CCC+")


def sp_to_moodys(sp: str) -> str:
    """Map an S&P rating to the Moody's notch at the same position on the scale."""
    return MOODYS_SCALE[SP_SCALE.index(sp)]


def notch_down(moodys: str, notches: int = 1) -> str:
    idx = min(MOODYS_SCALE.index(moodys) + notches, len(MOODYS_SCALE) - 1)
    return MOODYS_SCALE[idx]


class RatingsStore:
    """Answers "what was the rating of instrument X from agency Y on date D"."""

    def __init__(self, history: pd.DataFrame, as_of: date):
        self.history = history
        self.as_of = pd.Timestamp(as_of)
        self._lookups = 0

    def get(self, loanx_id: str, agency: str) -> str | None:
        self._lookups += 1
        h = self.history
        rows = h[(h["loanx_id"] == loanx_id) & (h["agency"] == agency) & (h["as_of"] <= self.as_of)]
        if rows.empty:
            return None
        rating = rows.sort_values("as_of").iloc[-1]["rating"]
        if pd.isna(rating) or rating in ("WR", "NR"):
            return None
        return str(rating)

    def moodys_derived(self, loanx_id: str) -> str:
        """Moody's rating if there is one; otherwise S&P mapped and one notch lower;
        otherwise the unrated default."""
        moodys = self.get(loanx_id, "MOODYS")
        if moodys:
            return moodys
        sp = self.get(loanx_id, "SP")
        if sp:
            return notch_down(sp_to_moodys(sp))
        return UNRATED_MOODYS

    def is_ccc(self, loanx_id: str) -> bool:
        """CCC bucket: Caa1 or lower at Moody's (derived), or CCC+ or lower at S&P."""
        moodys = self.moodys_derived(loanx_id)
        if MOODYS_SCALE.index(moodys) >= CCC_MOODYS_NOTCH:
            return True
        sp = self.get(loanx_id, "SP")
        return bool(sp) and SP_SCALE.index(sp) >= CCC_SP_NOTCH

    def rating_factor(self, loanx_id: str) -> int:
        return RATING_FACTOR[self.moodys_derived(loanx_id)]

    @property
    def lookups(self) -> int:
        return self._lookups
