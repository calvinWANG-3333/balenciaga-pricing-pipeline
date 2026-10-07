"""
Price realism.

Three rules keep synthetic prices believable:
  1. The EUR reference price is drawn from the REAL price distribution of its category
     (13 measured quantiles, interpolated), so it can never leave the real min-max range.
  2. Each market price = EUR price x a per-product ratio drawn inside the REAL market band
     (p05-p95 of local/FRA ratios measured on the same SKUs).
  3. Prices are snapped to retail price points (EUR 595, 1,190, 2,490; JPY to the 100; KRW to
     the 10,000) the way the real websites round them.
"""

import bisect
import random

from . import config


def sample_eur_price(rng: random.Random, quantiles: list[float]) -> int:
    """Inverse-CDF sampling from a piecewise-linear distribution through the real quantiles."""
    levels = config.QUANTILE_LEVELS
    u = rng.random()
    i = max(1, bisect.bisect_left(levels, u))
    lo_l, hi_l = levels[i - 1], levels[i]
    lo_v, hi_v = quantiles[i - 1], quantiles[i]
    t = 0.0 if hi_l == lo_l else (u - lo_l) / (hi_l - lo_l)
    # The outer 5% segments span a huge range (women's bags: EUR 4,000 -> 15,000 for the top 5%).
    # Real prices crowd near the inner quantile, so bend the interpolation towards it instead of
    # spreading uniformly - otherwise the synthetic tail is far heavier than the real one.
    if i == len(levels) - 1:
        t = t ** 4
    elif i == 1:
        t = 1 - (1 - t) ** 4
    raw = lo_v + t * (hi_v - lo_v)
    snapped = snap_eur(rng, raw)
    # snapping must never push a price outside the measured range
    return int(min(max(snapped, quantiles[0]), quantiles[-1]))


def snap_eur(rng: random.Random, x: float) -> int:
    """Luxury EUR price points: 295, 375, 595, 990, 1,190, 2,150, 2,490, 3,800 ..."""
    if x < 1000:
        v = round(x / 5) * 5
    elif x < 5000:
        v = round(x / 10) * 10
    else:
        v = round(x / 50) * 50
    if v >= 300 and rng.random() < 0.45:          # charm pricing: 600 -> 595 / 590 / 550
        hundred = round(v / 100) * 100
        v = hundred - rng.choice([5, 10, 50])
    return int(v)


def draw_market_ratio(rng: random.Random, ratio_q: tuple) -> float:
    p05, _p25, p50, _p75, p95 = ratio_q
    if p05 == p95:
        return p50
    return rng.triangular(p05, p95, p50)


def round_local(price: float, rounding) -> int:
    if not rounding:
        return int(round(price))
    for bound, step in rounding:
        if price < bound:
            return int(max(step, round(price / step) * step))
    return int(round(price))


def local_price(eur_price: float, ratio: float, market: str) -> int:
    mc = config.MARKETS[market]
    return round_local(eur_price * ratio, mc["rounding"])


def real_bounds(macro_tag: str, market: str, event_headroom: float = 0.10) -> tuple[float, float]:
    """Envelope a CLEAN local price must sit in: [EUR min x ratio p05, EUR max x ratio p95 x (1+headroom)].
    Headroom covers the planted September price increase plus rounding."""
    q = config.MACRO_TAGS[macro_tag]["eur_quantiles"]
    r = config.MARKETS[market]["ratio_q"]
    return q[0] * r[0] * 0.97, q[-1] * r[-1] * (1 + event_headroom) * 1.03
