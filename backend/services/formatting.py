"""Shared formatting helpers so the generator and the validator agree on how facts look."""
from __future__ import annotations

import re
from datetime import date, datetime

DATE_FMT = "%d %B %Y"  # 28 October 2026

_DATE_PATTERNS = [
    (re.compile(r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?,?\s+(\d{4})\b", re.I), "dmy_text"),
    (re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", re.I), "mdy_text"),
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "iso"),
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"), "dmy_slash"),
]
_MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
     "November", "December"], 1)}
_MONTHS.update({k[:3]: v for k, v in list(_MONTHS.items())})
_MONTHS["sept"] = 9


def fmt_date(d: date | None) -> str:
    return d.strftime(DATE_FMT).lstrip("0") if d else ""


def fmt_money(amount: float | None, symbol: str = "$") -> str:
    return f"{symbol}{amount:,.2f}" if amount is not None else ""


def extract_dates(text: str) -> list[tuple[str, date | None]]:
    """Return (matched_text, parsed_date) for every date-like string in text."""
    found: list[tuple[str, date | None]] = []
    for pattern, kind in _DATE_PATTERNS:
        for m in pattern.finditer(text):
            try:
                if kind == "dmy_text":
                    d = date(int(m.group(3)), _MONTHS[m.group(2).lower().rstrip(".")], int(m.group(1)))
                elif kind == "mdy_text":
                    d = date(int(m.group(3)), _MONTHS[m.group(1).lower().rstrip(".")], int(m.group(2)))
                elif kind == "iso":
                    d = datetime.strptime(m.group(0), "%Y-%m-%d").date()
                else:
                    d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except (ValueError, KeyError):
                d = None
            found.append((m.group(0), d))
    return found


_MONEY = re.compile(r"(?:\$|₹|£|€|\bRs\.?|\bINR|\bUSD)\s?(\d[\d,]*(?:\.\d{1,2})?)", re.I)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def extract_money(text: str) -> list[float]:
    return [float(m.replace(",", "")) for m in _MONEY.findall(text)]


def extract_numbers(text: str) -> list[float]:
    out = []
    for m in _NUMBER.findall(text):
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            continue
    return out
