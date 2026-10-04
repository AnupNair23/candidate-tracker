"""Offline zip → distance using pgeocode (GeoNames data, downloaded once on first use)."""

from __future__ import annotations

import asyncio
import logging
import math
import re

from app.constants.geo import GEO_COUNTRY, KM_PER_MILE, US_STATE_CODES

log = logging.getLogger("app.geo")

_dist = None
_failed = False
_lock = asyncio.Lock()


def state_code(state: str | None) -> str | None:
    """'Utah' / 'ut' / 'UT' → 'UT'; unknown → None."""
    if not state:
        return None
    text = state.strip()
    if len(text) == 2 and text.isalpha():
        return text.upper()
    return US_STATE_CODES.get(text.lower())


def same_state(a: str | None, b: str | None) -> bool:
    ca, cb = state_code(a), state_code(b)
    if ca and cb:
        return ca == cb
    return bool(a and b) and a.strip().lower() == b.strip().lower()


def _zip5(zipcode: str | None) -> str | None:
    if not zipcode:
        return None
    match = re.match(r"\s*(\d{5})", str(zipcode))
    return match.group(1) if match else None


async def _get():
    global _dist, _failed
    if _dist is not None or _failed:
        return _dist
    async with _lock:
        if _dist is None and not _failed:
            try:
                import pgeocode

                _dist = await asyncio.to_thread(pgeocode.GeoDistance, GEO_COUNTRY)
            except Exception as exc:  # network/data issues → distance stays unknown
                log.warning("pgeocode unavailable, distances will be unknown: %s", exc)
                _failed = True
    return _dist


async def distances_miles(origin_zip: str | None, zips: dict[str, str | None]) -> dict[str, float | None]:
    """Distance from origin to each candidate zip, keyed by candidate id. Unknown → None."""
    origin = _zip5(origin_zip)
    out: dict[str, float | None] = {k: None for k in zips}
    targets = {k: _zip5(z) for k, z in zips.items()}
    targets = {k: z for k, z in targets.items() if z}
    if not origin or not targets:
        return out
    dist = await _get()
    if dist is None:
        return out
    keys = list(targets)
    try:
        km = await asyncio.to_thread(dist.query_postal_code, [origin] * len(keys), [targets[k] for k in keys])
    except Exception as exc:
        log.warning("distance lookup failed: %s", exc)
        return out
    for key, value in zip(keys, list(km), strict=False):
        if value is not None and not (isinstance(value, float) and math.isnan(value)):
            out[key] = round(float(value) / KM_PER_MILE, 1)
    return out
