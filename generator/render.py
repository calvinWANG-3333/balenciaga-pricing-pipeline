"""
Render one product, in one market, on one crawl date, into one raw crawl record -
field-for-field the same shape as the real crawler output (19 top-level keys, same order,
same nesting, same quirks).

Real quirks reproduced on purpose (they are SYSTEMIC, so they are not listed in the defect
manifest - every row has them and the staging layer must handle them by design):
  S1  price.price is in minor units (x100) for most markets but not for CHN / SAU / FRA,
      and price.currency always says "EUR" even when it is not EUR.
  S2  raw category labels are written in the website's language (FEMME / 女士 / MUJER ...).
  S3  the free-text productCategory label changes from week to week for the same product.
  S4  brand tags contain typos inherited from the brand side (ba_micro_..., Bal_super_micro_...).
  S5  the China site is a different crawler: two SKUs (style code + numeric id), Title Case
      names, Chinese + English labels, and an empty productDetails list.
"""

import random
import re
import zlib

from . import config

SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    return SLUG_RE.sub("-", text.lower()).strip("-")


def stable_rng(*parts) -> random.Random:
    """Deterministic per-entity randomness (Python's hash() is salted per process, crc32 is not)."""
    return random.Random(zlib.crc32("|".join(map(str, parts)).encode("utf-8")))


def display_gender(product) -> str:
    if product.gender != "unisex":
        return product.gender
    return "women" if zlib.crc32(product.sku.encode()) % 2 else "men"


def _macro_tags(product) -> list[str]:
    return product.macro_tag.split("|")


def _stock(product, market, week) -> str:
    r = stable_rng("stock", product.sku, market, week // 4)
    x = r.random()
    for value, w in config.STOCK_STATES:
        x -= w
        if x <= 0:
            return value
    return "instock"


def _product_category(product, market, week) -> str:
    r = stable_rng("pc", product.sku, market, week)
    pool = config.MACRO_TAGS[product.macro_tag]["product_category_pool"]
    return r.choice(pool) if r.random() < 0.55 else product.default_product_category


def render_row(product, market: str, week: int, local_price: int, ts_ms: int) -> dict:
    mc = config.MARKETS[market]
    lang = mc["lang"]
    gender = display_gender(product)
    is_chn = market == "CHN"
    sku = product.sku

    # ---- name / url / image ----
    if is_chn:
        name = product.name.title()
        url = f"https://www.balenciaga.cn/products/{gender}/{_slug(product.name)}-{sku.lower()}.html"
        preview = f"https://media.balenciaga.cn/asset/{product.image_uuid}/Medium/{sku}_X.jpg"
        skus = [sku, product.chn_numeric_id]
        crawler = "BalenciagaChina"
    else:
        name = product.name
        url = (f"https://www.balenciaga.com/{mc['locale']}/"
               f"{_slug(product.name)}-{_slug(product.color)}-{sku}.html")
        preview = (f"https://balenciaga.dam.kering.com/asset/{product.image_uuid}/Small/"
                   f"{sku}_X.jpg?v={product.image_version}")
        skus = [sku]
        crawler = "BalenciagaInternational"

    # ---- raw categories (localized, unstable) ----
    tags = _macro_tags(product) + [product.micro, product.supermicro]
    top = config.TOP_LABEL[lang][gender]
    fam = config.FAMILY_LABEL[lang][product.family]
    pcat = _product_category(product, market, week)
    if is_chn:
        categories = [top, fam, gender.title(), config.CHN_EN_FAMILY[product.family]] + \
                     _macro_tags(product) + [product.supermicro, product.micro]
    elif product.has_top_category:
        categories = [top, fam, pcat]
        if stable_rng("season", sku, market, week).random() < 0.25:
            categories.append(stable_rng("seasonv", sku, week).choice(config.SEASONAL_TAGS))
        categories += tags
    else:
        categories = [gender] + tags

    # ---- productDetails (key/value list; empty on the China crawler) ----
    details = []
    if not is_chn:
        sub = None
        if product.has_sub_category and product.sub_fr:
            sub = product.sub_fr if lang == "fr" else config.SUB_FR_TO_EN.get(product.sub_fr, product.sub_fr)
        pairs = [
            ("collection", product.collection),
            ("packshotType", "video" if stable_rng("pack", sku).random() < 0.001 else "image"),
            ("brand", "balenciaga"),
            ("color", product.color),
            ("colorId", product.color_id),
        ]
        if product.has_top_category:
            pairs += [("category", fam), ("topCategory", top)]
        pairs += [
            ("productCategory", pcat),
            ("macroCategory", product.macro_tag),
            ("microCategory", product.micro),
            ("superMicroCategory", product.supermicro),
        ]
        if sub:
            pairs.append(("subCategory", sub))
        pairs += [("stock", _stock(product, market, week)), ("list", "productList")]
        if product.material:
            pairs.append(("material", product.material))
        details = [{"key": k, "value": v} for k, v in pairs]

    price = {
        "original_price": str(local_price),
        "original_currency": mc["currency"],
        "price": local_price * mc["minor_scale"],        # S1: minor units, mislabelled as EUR
        "currency": "EUR",
        "is_discounted": False,
    }

    # key order identical to the real crawler output
    return {
        "objectID": f"{config.BRAND_SLUG}_{market}_{sku}",
        "brandId": config.BRAND_ID,
        "name": name,
        "url": url,
        "price": price,
        "categories": categories,
        "productDetails": details,
        "previewUrl": preview,
        "status": 200,
        "source": f"{config.BRAND_SLUG}_{market}",
        "importSource": config.IMPORT_SOURCE,
        "crawlerName": crawler,
        "createdAt": ts_ms,
        "updatedAt": ts_ms,
        "releasedAt": ts_ms,
        "skus": skus,
        "market": market,
        "validationErrors": [],
        "isValid": True,
    }
