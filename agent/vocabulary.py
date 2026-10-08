"""What values exist: the words a question can use, read from the published data itself.

Guardrails only accept filter values that exist here (no made-up market, no made-up product), and the
rule-based translator uses the aliases to recognise them in free text ("Japan" -> JPN, "the Le City" ->
"Le City Bag Medium (black)", "sneakers" -> Shoes).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from .semantic import Catalogue

# words people use that are not in the data
# market codes that are also English words: "what ARE prices", "CAN you show" must not become a filter
CODES_THAT_ARE_WORDS = {"are", "can"}


def code_aliases(codes) -> dict[str, str]:
    return {c.lower(): c for c in codes if c.lower() not in CODES_THAT_ARE_WORDS}


MARKET_ALIASES = {
    "usa": "USA", "u.s.": "USA", "united states": "USA", "america": "USA", "american": "USA",
    "uk": "GBR", "u.k.": "GBR", "britain": "GBR", "great britain": "GBR", "england": "GBR", "london": "GBR",
    "uae": "ARE", "emirates": "ARE", "dubai": "ARE",
    "china": "CHN", "mainland": "CHN", "korea": "KOR", "seoul": "KOR", "hong kong": "HKG", "hk": "HKG",
    "japan": "JPN", "tokyo": "JPN", "paris": "FRA", "france": "FRA", "french": "FRA", "taiwan": "TWN",
    "saudi": "SAU", "ksa": "SAU", "singapore": "SGP", "malaysia": "MYS", "thailand": "THA",
    "australia": "AUS", "canada": "CAN", "mexico": "MEX",
}
CATEGORY_ALIASES = {
    "bags": "Bags", "bag": "Bags", "handbags": "Bags", "handbag": "Bags",
    "small leather goods": "Small Leather Goods", "slg": "Small Leather Goods", "slgs": "Small Leather Goods",
    "wallets": "Small Leather Goods", "wallet": "Small Leather Goods", "card holders": "Small Leather Goods",
    "shoes": "Shoes", "shoe": "Shoes", "footwear": "Shoes", "sneakers": "Shoes",
    "accessories": "Accessories", "accessory": "Accessories", "jewelry": "Accessories", "jewellery": "Accessories",
}
DIRECTION_ALIASES = {
    "increase": "increase", "increases": "increase", "increased": "increase", "rises": "increase",
    "decrease": "decrease", "decreases": "decrease", "decreased": "decrease", "drops": "decrease",
    "drop": "decrease", "markdowns": "decrease", "markdown": "decrease", "cuts": "decrease",
}


def normalise(text: str) -> str:
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9\-\.\s]", " ", text)
    text = re.sub(r"(?<=\w)\.(?=\s|$)", " ", text)       # sentence dots, keep "s.2" / "u.s."
    return re.sub(r"\s+", " ", text).strip()


def product_aliases(labels: list[str]) -> dict[str, str]:
    """Every unambiguous way to name a hero: the full name, and its shorter unique prefixes."""
    cores = {label: normalise(re.sub(r"\(.*?\)", "", label)) for label in labels}
    aliases: dict[str, str] = {}
    for label, core in cores.items():
        aliases[core] = label
        words = core.split()
        for n in range(len(words) - 1, 0, -1):
            prefix = " ".join(words[:n])
            if len(prefix) < 3 or prefix in {"le", "the"}:
                continue
            owners = [lab for lab, c in cores.items() if c == prefix or c.startswith(prefix + " ")]
            if owners == [label]:
                aliases.setdefault(prefix, label)
    return aliases


@dataclass
class Vocabulary:
    values: dict[tuple[str, str], list[str]] = field(default_factory=dict)   # (model, dim) -> values
    aliases: dict[str, dict[str, str]] = field(default_factory=dict)         # dim -> alias -> value
    periods: dict[str, list[date]] = field(default_factory=dict)             # model -> sorted dates
    market_currency: dict[str, str] = field(default_factory=dict)

    def values_for(self, model: str, dim: str) -> list[str]:
        return self.values.get((model, dim), [])

    def bounds(self, model: str) -> tuple[date, date] | None:
        p = self.periods.get(model)
        return (p[0], p[-1]) if p else None


def _as_date(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def load(catalogue: Catalogue, db, published_schema: str) -> Vocabulary:
    """A handful of small DISTINCT queries on the published views - run once per session."""
    vocab = Vocabulary()
    for model in catalogue.models.values():
        relation = f"{published_schema}.{model.alias}"
        for dim in model.dimensions.values():
            if dim.type == "categorical":
                rows = db.query(f"select distinct {dim.expr} as v from {relation} where {dim.expr} is not null")
                vocab.values[(model.name, dim.name)] = sorted(str(r["v"]) for r in rows)
        tdim = model.dimensions[model.time_dimension]
        rows = db.query(f"select distinct {tdim.expr} as d from {relation} where {tdim.expr} is not null")
        vocab.periods[model.name] = sorted(_as_date(r["d"]) for r in rows)

    markets = db.query(f"select market, market_name, currency_code from {published_schema}.pub_dim_market")
    vocab.market_currency = {r["market"]: r["currency_code"] for r in markets}
    known_markets = {r["market"] for r in markets}
    market_aliases = code_aliases(known_markets)
    market_aliases.update({normalise(r["market_name"]): r["market"] for r in markets})
    market_aliases.update({k: v for k, v in MARKET_ALIASES.items() if v in known_markets})
    vocab.aliases["market"] = market_aliases

    labels = sorted({v for (m, d), vals in vocab.values.items() if d == "product_label" for v in vals})
    vocab.aliases["product_label"] = product_aliases(labels)
    pointers = sorted({v for (m, d), vals in vocab.values.items() if d == "pointer_id" for v in vals})
    vocab.aliases["pointer_id"] = {p.lower(): p for p in pointers}

    categories = {v for (m, d), vals in vocab.values.items() if d == "macro_category" for v in vals}
    cat_aliases = {c.lower(): c for c in categories}
    cat_aliases.update({k: v for k, v in CATEGORY_ALIASES.items() if v in categories})
    vocab.aliases["macro_category"] = cat_aliases
    vocab.aliases["change_direction"] = dict(DIRECTION_ALIASES)
    return vocab
