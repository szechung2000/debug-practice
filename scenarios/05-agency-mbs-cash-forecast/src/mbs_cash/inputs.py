"""Positions (from the accounting system) and pool factors (from the agencies)."""
from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .config import PROGRAMS

log = logging.getLogger(__name__)

CUSIP_RE = re.compile(r"^[0-9A-Z]{8}[0-9]$")
PERIOD_RE = re.compile(r"^\d{4}-\d{2}$")


class InputError(Exception):
    pass


@dataclass(frozen=True)
class Position:
    account: str
    cusip: str
    pool_number: str
    program: str
    coupon: Decimal          # pass-through rate, e.g. 0.055
    original_face: Decimal


def _dec(raw: str, what: str, where: str) -> Decimal:
    try:
        return Decimal(raw.strip().replace(",", ""))
    except (InvalidOperation, AttributeError) as exc:
        raise InputError(f"{where}: bad {what} {raw!r}") from exc


def cusip_check_digit(base: str) -> int:
    total = 0
    for i, ch in enumerate(base):
        v = int(ch) if ch.isdigit() else ord(ch) - 55
        if i % 2:
            v *= 2
        total += v // 10 + v % 10
    return (10 - total % 10) % 10


def load_positions(path: Path) -> list[Position]:
    out: list[Position] = []
    with path.open(newline="") as fh:
        for n, row in enumerate(csv.DictReader(fh), start=2):
            where = f"{path.name} line {n}"
            cusip = row["cusip"].strip().upper()
            if not CUSIP_RE.match(cusip) or cusip_check_digit(cusip[:8]) != int(cusip[8]):
                raise InputError(f"{where}: invalid CUSIP {cusip}")
            program = row["program"].strip().upper()
            if program not in PROGRAMS:
                raise InputError(f"{where}: unknown program {program}")
            coupon = _dec(row["coupon"], "coupon", where)
            if coupon > 1:
                coupon = coupon / 100
            out.append(Position(row["account"].strip(), cusip, row["pool_number"].strip(), program,
                                coupon, _dec(row["original_face"], "original face", where)))
    log.info("positions: %d lines, %d accounts, %d pools", len(out),
             len({p.account for p in out}), len({p.cusip for p in out}))
    return out


def load_factors(path: Path) -> dict[str, dict[str, Decimal]]:
    """Return {cusip: {period 'YYYY-MM': factor}}. Factors carry 8 decimals."""
    factors: dict[str, dict[str, Decimal]] = {}
    with path.open(newline="") as fh:
        for n, row in enumerate(csv.DictReader(fh), start=2):
            where = f"{path.name} line {n}"
            period = row["period"].strip()
            if not PERIOD_RE.match(period):
                raise InputError(f"{where}: bad period {period!r}")
            f = _dec(row["factor"], "factor", where)
            if not Decimal("0") <= f <= Decimal("1"):
                raise InputError(f"{where}: factor out of range {f}")
            factors.setdefault(row["cusip"].strip().upper(), {})[period] = f
    log.info("factors: %d pools, latest period %s", len(factors),
             max((max(v) for v in factors.values()), default="-"))
    return factors
