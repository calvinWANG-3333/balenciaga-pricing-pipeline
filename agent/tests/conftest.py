"""Offline fixtures: the semantic manifest (a committed copy) and the vocabulary of the reference data.
No warehouse, no API key - the agent's logic is tested on its own."""

from datetime import date, timedelta
from pathlib import Path

import pytest

from agent import semantic
from agent.vocabulary import (CATEGORY_ALIASES, DIRECTION_ALIASES, MARKET_ALIASES, Vocabulary,
                              normalise, product_aliases)

FIXTURES = Path(__file__).with_name("fixtures")

MARKETS = {"FRA": ("France", "EUR"), "GBR": ("United Kingdom", "GBP"), "USA": ("United States", "USD"),
           "CAN": ("Canada", "CAD"), "MEX": ("Mexico", "MXN"), "ARE": ("United Arab Emirates", "AED"),
           "SAU": ("Saudi Arabia", "SAR"), "CHN": ("Mainland China", "CNY"), "HKG": ("Hong Kong", "HKD"),
           "TWN": ("Taiwan", "TWD"), "JPN": ("Japan", "JPY"), "KOR": ("South Korea", "KRW"),
           "SGP": ("Singapore", "SGD"), "MYS": ("Malaysia", "MYR"), "THA": ("Thailand", "THB"),
           "AUS": ("Australia", "AUD")}
WEEKLY = ["ARE", "CHN", "FRA", "GBR", "HKG", "JPN", "KOR", "USA"]
HEROES = {"HERO-01": "Le City Bag Medium (black)", "HERO-02": "Rodeo Handbag Small (black)",
          "HERO-03": "Hourglass Handbag Small (black)", "HERO-04": "Le Cagole Shoulder Bag Small (black)",
          "HERO-05": "Triple S.2 Sneaker (black)", "HERO-06": "3XL Sneaker (black)",
          "HERO-07": "Le City Card Holder (black)", "HERO-08": "Cash Long Coin and Card Holder Large (black)"}
CATEGORIES = ["Accessories", "Bags", "Shoes", "Small Leather Goods"]


@pytest.fixture(scope="session")
def catalogue():
    return semantic.load(FIXTURES / "semantic_manifest.json")


@pytest.fixture(scope="session")
def vocab():
    v = Vocabulary()
    v.values[("hero_prices", "market")] = sorted(WEEKLY)
    v.values[("hero_prices", "pointer_id")] = sorted(HEROES)
    v.values[("hero_prices", "product_label")] = [HEROES[k] for k in sorted(HEROES)]
    v.values[("hero_prices", "currency_code")] = sorted(MARKETS[m][1] for m in WEEKLY)
    v.values[("hero_prices", "price_status")] = ["first_delivery", "price_decrease", "price_increase", "unchanged"]
    for model in ("category_monthly", "price_changes"):
        v.values[(model, "market")] = sorted(MARKETS)
        v.values[(model, "macro_category")] = CATEGORIES
    v.values[("category_monthly", "currency_code")] = sorted(c for _, c in MARKETS.values())
    v.values[("price_changes", "change_direction")] = ["decrease", "increase"]
    v.periods["hero_prices"] = [date(2026, 7, 7) + timedelta(weeks=i) for i in range(13)]
    v.periods["category_monthly"] = [date(2026, 7, 1), date(2026, 8, 1), date(2026, 9, 1)]
    v.periods["price_changes"] = [date(2026, 7, 13) + timedelta(weeks=i) for i in range(12) if i != 6]
    v.market_currency = {m: c for m, (_, c) in MARKETS.items()}
    aliases = {m.lower(): m for m in MARKETS}
    aliases.update({normalise(name): m for m, (name, _) in MARKETS.items()})
    aliases.update(MARKET_ALIASES)
    v.aliases["market"] = aliases
    v.aliases["product_label"] = product_aliases(list(HEROES.values()))
    v.aliases["pointer_id"] = {p.lower(): p for p in HEROES}
    v.aliases["macro_category"] = {**{c.lower(): c for c in CATEGORIES}, **CATEGORY_ALIASES}
    v.aliases["change_direction"] = dict(DIRECTION_ALIASES)
    return v
