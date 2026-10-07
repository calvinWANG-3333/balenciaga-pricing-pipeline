"""
Build the synthetic product master: "what Balenciaga sells", independent of any crawl.

Plain English: before we can fake a week of website crawls we need a fake shop. This module
invents ~2,000 products, each with a style code, a colour, a category, a launch/retire week,
and a single reference price in EUR. Every later crawl is just "look at this shop in market X
on date Y" - which is why the same SKU shows a consistent price ladder across markets.
"""

import random
import string
from dataclasses import dataclass, field

from . import config
from .pricing import sample_eur_price, draw_market_ratio


@dataclass
class Product:
    sku: str
    style: str
    name: str
    macro_tag: str
    gender: str              # women / men / unisex (as the brand tags it)
    family: str              # rtw / bags / leather_goods / slg / shoes / accessories / eyewear / beauty
    color: str
    color_id: str
    collection: str
    micro: str
    supermicro: str
    sub_fr: str | None
    default_product_category: str
    eur_price: int
    launch_week: int         # first batch index the product is on the site
    end_week: int | None     # first batch index the product is gone (None = never)
    markets: dict = field(default_factory=dict)   # market -> fixed ratio vs EUR
    chn_numeric_id: str = ""
    image_uuid: str = ""
    image_version: int = 1
    has_top_category: bool = True
    has_sub_category: bool = True
    material: str | None = None
    is_hero: bool = False
    hero_id: str | None = None


def _weighted(rng, pairs):
    total = sum(w for _, w in pairs)
    x = rng.random() * total
    for value, w in pairs:
        x -= w
        if x <= 0:
            return value
    return pairs[-1][0]


def _style_code(rng):
    # real style codes look like 795456, 872668, 617196 or A001YY / A0070I
    if rng.random() < 0.12:
        return "A0" + "".join(rng.choice(string.digits + "ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(4))
    return rng.choice("5678") + "".join(rng.choice(string.digits) for _ in range(5))


def _material_code(rng):
    # real material/variant blocks look like 2AA4U, TZ99G, W2DDB, T3461, 210F6
    first = rng.choice(["2A", "T", "W", "21", "4G", "TT", "2AB"])
    rest_len = 5 - len(first)
    return first + "".join(rng.choice(string.ascii_uppercase + string.digits) for _ in range(rest_len))


def _uuid(rng):
    h = "%032x" % rng.getrandbits(128)
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def build_product_master(rng: random.Random, n_products: int, n_weeks: int) -> list[Product]:
    tags = config.MACRO_TAGS
    total_real = sum(t["real_count"] for t in tags.values())
    products: list[Product] = []
    used_skus: set[str] = set()
    style_by_name: dict[tuple, str] = {}

    def make(tag: str, name: str, color=None, hero_id=None) -> Product:
        prof = tags[tag]
        key = (tag, name)
        if key not in style_by_name:
            style_by_name[key] = _style_code(rng)
        style = style_by_name[key]
        color_name, color_id = color or rng.choice(config.COLORS)
        while True:
            sku = style + _material_code(rng) + color_id
            if sku not in used_skus:
                used_skus.add(sku)
                break
        is_hero = hero_id is not None
        launch = 0 if (is_hero or rng.random() < 0.92) else rng.randint(1, n_weeks - 1)
        end = None
        if not is_hero and rng.random() < 0.07:
            end = rng.randint(max(launch + 1, 1), n_weeks)  # == n_weeks means "never seen gone"
            end = None if end >= n_weeks else end

        p = Product(
            sku=sku, style=style, name=name, macro_tag=tag, gender=prof["gender"], family=prof["family"],
            color=color_name, color_id=color_id, collection=_weighted(rng, config.COLLECTIONS),
            micro=rng.choice(prof["micro"]), supermicro=rng.choice(prof["supermicro"]),
            sub_fr=rng.choice(prof["sub_fr"]) if prof["sub_fr"] else None,
            default_product_category=rng.choice(prof["product_category_pool"]),
            eur_price=sample_eur_price(rng, prof["eur_quantiles"]),
            launch_week=launch, end_week=end,
            chn_numeric_id=str(rng.randint(50000, 59999)),
            image_uuid=_uuid(rng), image_version=rng.randint(1, 4),
            has_top_category=is_hero or rng.random() > 0.12,
            has_sub_category=is_hero or rng.random() > 0.18,
            material=rng.choice(["calfskin", "lambskin", "canvas", "nylon"]) if rng.random() < 0.02 else None,
            is_hero=is_hero, hero_id=hero_id,
        )
        # market assortment: which markets sell it, and at which fixed ratio
        exclusive = None if is_hero or rng.random() > 0.04 else rng.choice(config.ALL_MARKETS)
        for m, mc in config.MARKETS.items():
            if exclusive and m != exclusive:
                continue
            if is_hero and mc["weekly"]:
                sold = True
            else:
                sold = exclusive == m or rng.random() < mc["availability"]
            if sold:
                p.markets[m] = draw_market_ratio(rng, mc["ratio_q"])
        return p

    # 1) hero products first, so they always exist with clean, predictable attributes
    for hero_id, tag, name in config.HERO_PRODUCTS:
        products.append(make(tag, name, color=("black", "1000"), hero_id=hero_id))

    # 2) the rest of the assortment, allocated to macro tags in real proportions
    remaining = n_products - len(products)
    for tag, prof in tags.items():
        n_tag = max(1, round(remaining * prof["real_count"] / total_real))
        for _ in range(n_tag):
            products.append(make(tag, rng.choice(prof["names"])))
    return products
