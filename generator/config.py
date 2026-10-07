"""
Static configuration for the synthetic Balenciaga crawl generator.

Everything here is either
  (a) an aggregate measured on real crawl exports (market price ratios, rounding habits,
      which crawler serves which market), or
  (b) a deliberate design choice for the portfolio (batch calendar, defect rates).

Plain-English picture
---------------------
A luxury brand sets ONE reference price in Paris (EUR) and then a "price ladder" for every
other country: the same bag costs ~1.24x the EUR number in USD, ~180x in JPY, and so on.
We reproduce that ladder from real data, so a synthetic Rodeo bag in Tokyo costs what a real
one would cost - never a random number.
"""

import json
from datetime import date
from pathlib import Path

CALIBRATION_DIR = Path(__file__).parent / "calibration"
CATEGORY_PROFILES = json.loads((CALIBRATION_DIR / "category_profiles.json").read_text(encoding="utf-8"))
QUANTILE_LEVELS = CATEGORY_PROFILES["quantile_levels"]
MACRO_TAGS = CATEGORY_PROFILES["macro_tags"]

BRAND_ID = 532
BRAND_SLUG = "Balenciaga"
IMPORT_SOURCE = "LY-PM-Crawler"

# --------------------------------------------------------------------------------------
# Markets
#   ratio_q      : local price / FRA price for the same SKU, quantiles (p05, p25, p50, p75, p95)
#                  measured on real crawls. Each synthetic product draws one ratio per market
#                  inside this band and keeps it (prices are sticky).
#   minor_scale  : the real crawler writes price.price in minor units (x100) for most markets,
#                  but NOT for CHN, SAU and FRA - a genuine source quirk we reproduce.
#   rounding     : list of (upper_bound_in_local_currency, step). Prices are snapped to the
#                  step of the first bound they fall under, mimicking real retail price points.
#   lang         : language of the localized category labels in this market.
#   availability : probability that a product is sold in this market.
# --------------------------------------------------------------------------------------
MARKETS = {
    "ARE": dict(currency="AED", locale="en-ae", lang="en", ratio_q=(4.333, 4.479, 4.615, 4.636, 4.800),
                minor_scale=100, rounding=[(1000, 5), (10**9, 50)], availability=0.92, weekly=True),
    "CHN": dict(currency="CNY", locale="cn", lang="zh", ratio_q=(9.086, 9.286, 9.455, 9.588, 10.000),
                minor_scale=1, rounding=[(10**9, 100)], availability=0.68, weekly=True),
    "FRA": dict(currency="EUR", locale="fr-fr", lang="fr", ratio_q=(1.0, 1.0, 1.0, 1.0, 1.0),
                minor_scale=1, rounding=[(1000, 5), (5000, 10), (10**9, 50)], availability=0.94, weekly=True),
    "GBR": dict(currency="GBP", locale="en-gb", lang="en", ratio_q=(0.874, 0.886, 0.897, 0.912, 0.947),
                minor_scale=100, rounding=[(1000, 5), (10**9, 10)], availability=0.94, weekly=True),
    "HKG": dict(currency="HKD", locale="en-hk", lang="en", ratio_q=(9.238, 9.458, 9.641, 9.778, 10.000),
                minor_scale=100, rounding=[(10**9, 100)], availability=0.92, weekly=True),
    "JPN": dict(currency="JPY", locale="en-jp", lang="en", ratio_q=(171.1, 176.0, 180.0, 181.9, 196.0),
                minor_scale=100, rounding=[(10**9, 100)], availability=0.96, weekly=True),
    "KOR": dict(currency="KRW", locale="en-kr", lang="en", ratio_q=(1648.1, 1686.9, 1728.6, 1775.8, 1833.3),
                minor_scale=100, rounding=[(10**9, 10000)], availability=0.93, weekly=True),
    "USA": dict(currency="USD", locale="en-us", lang="en", ratio_q=(1.178, 1.214, 1.241, 1.264, 1.339),
                minor_scale=100, rounding=[(1000, 5), (10**9, 10)], availability=0.97, weekly=True),
    # ---- extended markets: only crawled in the monthly "extended" batch ----
    "AUS": dict(currency="AUD", locale="en-au", lang="en", ratio_q=(1.654, 1.799, 1.838, 1.923, 1.970),
                minor_scale=100, rounding=[(1000, 5), (10**9, 10)], availability=0.92, weekly=False),
    "CAN": dict(currency="CAD", locale="en-ca", lang="en", ratio_q=(1.571, 1.624, 1.657, 1.692, 1.720),
                minor_scale=100, rounding=[(1000, 5), (10**9, 10)], availability=0.92, weekly=False),
    "MEX": dict(currency="MXN", locale="es-mx", lang="es", ratio_q=(25.16, 26.43, 27.27, 28.28, 29.25),
                minor_scale=100, rounding=[(10**9, 100)], availability=0.22, weekly=False),
    "MYS": dict(currency="MYR", locale="en-my", lang="en", ratio_q=(4.905, 5.083, 5.253, 5.417, 5.600),
                minor_scale=100, rounding=[(1000, 10), (10**9, 50)], availability=0.92, weekly=False),
    "SAU": dict(currency="SAR", locale="en-sa", lang="en", ratio_q=(4.671, 4.847, 4.946, 4.967, 5.091),
                minor_scale=1, rounding=[(1000, 5), (10**9, 50)], availability=0.92, weekly=False),
    "SGP": dict(currency="SGD", locale="en-sg", lang="en", ratio_q=(1.577, 1.619, 1.635, 1.709, 1.786),
                minor_scale=100, rounding=[(1000, 5), (10**9, 10)], availability=0.92, weekly=False),
    "THA": dict(currency="THB", locale="en-th", lang="en", ratio_q=(39.73, 40.71, 41.27, 43.43, 45.65),
                minor_scale=100, rounding=[(10**9, 100)], availability=0.92, weekly=False),
    "TWN": dict(currency="TWD", locale="en-tw", lang="en", ratio_q=(37.41, 38.64, 39.11, 39.41, 41.45),
                minor_scale=100, rounding=[(10**9, 100)], availability=0.92, weekly=False),
}
WEEKLY_MARKETS = [m for m, c in MARKETS.items() if c["weekly"]]
ALL_MARKETS = list(MARKETS)

CURRENCY_SYMBOL = {
    "AED": "AED ", "CNY": "CN¥", "EUR": "€", "GBP": "£", "HKD": "HK$", "JPY": "¥", "KRW": "₩", "USD": "$",
    "AUD": "A$", "CAD": "C$", "MXN": "MX$", "MYR": "RM", "SAR": "SAR ", "SGD": "S$", "THB": "฿", "TWD": "NT$",
}

# --------------------------------------------------------------------------------------
# Localized labels. Real crawls carry the website's own language: FEMME/Sacs on the
# French site, 女士/包袋 on the Chinese site, MUJER/Bolsos on the Mexican site.
# This is exactly why a downstream "harmonized category" layer is needed.
# --------------------------------------------------------------------------------------
TOP_LABEL = {
    "en": {"women": "WOMEN", "men": "MEN"},
    "fr": {"women": "FEMME", "men": "HOMME"},
    "es": {"women": "MUJER", "men": "HOMBRE"},
    "zh": {"women": "女士", "men": "男士"},
}
FAMILY_LABEL = {
    "en": {"rtw": "Ready-To-Wear", "bags": "Bags", "leather_goods": "Bags", "slg": "Small Leather Goods",
           "shoes": "Shoes", "accessories": "Accessories", "eyewear": "Accessories", "beauty": "Fragrances"},
    "fr": {"rtw": "Prêt-À-Porter", "bags": "Sacs", "leather_goods": "Sacs", "slg": "Petite Maroquinerie",
           "shoes": "Chaussures", "accessories": "Accessoires", "eyewear": "Accessoires", "beauty": "Parfums"},
    "es": {"rtw": "Ropa", "bags": "Bolsos", "leather_goods": "Bolsos", "slg": "Pequeña Marroquinería",
           "shoes": "Zapatos", "accessories": "Accesorios", "eyewear": "Accesorios", "beauty": "Fragancias"},
    "zh": {"rtw": "成衣", "bags": "包袋", "leather_goods": "包袋", "slg": "小皮具",
           "shoes": "鞋履", "accessories": "配饰", "eyewear": "配饰", "beauty": "香氛"},
}
CHN_EN_FAMILY = {"rtw": "Ready to Wear", "bags": "Bags", "leather_goods": "Bags", "slg": "Small Leather Goods",
                 "shoes": "Shoes", "accessories": "Accessories", "eyewear": "Eyewear", "beauty": "Fragrance"}

# French sub-category labels (from the FRA site) and their English counterparts.
SUB_FR_TO_EN = {
    "Pantalons": "Pants", "T-shirts": "T-Shirts", "Manteaux & Vestes": "Coats & Jackets",
    "Sweatshirts & Hoodies": "Sweatshirts & Hoodies", "Tops & Chemises": "Tops & Shirts",
    "Robes & Jupes": "Dresses & Skirts", "Bijoux": "Jewelry", "Ceintures": "Belts",
    "Charms & Accessoires Téléphone": "Charms & Phone Accessories", "Lunettes": "Eyewear",
    "Accessoires Cheveux": "Hair Accessories", "Sneakers": "Sneakers", "Sandales": "Sandals",
    "Chaussures À Talons": "Heels", "Bottes": "Boots", "Hamptons": "Hamptons", "Le City": "Le City",
    "Rodeo": "Rodeo", "Sacs À Main": "Handbags", "Sacs Porté Épaule": "Shoulder Bags",
    "Porte-Cartes": "Card Holders", "Portefeuille & Porte-Monnaies": "Wallets & Coin Purses",
    "Mules et Sandales": "Mules & Sandals", "Speed": "Speed", "Triple S.2": "Triple S.2",
    "Chapeaux & Casquettes": "Hats & Caps", "Chaussettes": "Socks", "Pochettes": "Pouches",
    "Cash": "Cash", "Objets": "Objects", "Chips": "Chips", "LUNETTES DE SOLEIL": "SUNGLASSES",
    "Hourglass Avenue": "Hourglass Avenue", "Bolero": "Bolero",
    "Sacs Bandoulière & Messenger": "Crossbody & Messenger Bags", "Sacs À Dos": "Backpacks",
    "Sacs Ceinture": "Belt Bags", "Cabas": "Totes", "Explorer": "Explorer",
}

# Colours measured on real crawls: (colour name, 4-digit colour code used as the SKU suffix)
COLORS = [
    ("black", "1000"), ("black", "1000"), ("black", "1000"), ("black", "1000"), ("black", "1000"),
    ("white", "9000"), ("antique silver", "0911"), ("black/multicolor", "1084"), ("black", "1090"),
    ("light espresso", "2308"), ("volcanic rock", "1251"), ("black/white", "1090"), ("silver", "8122"),
    ("navy", "8065"), ("camel", "2533"), ("shiny gold", "0127"), ("faded black", "1041"), ("blue", "4011"),
    ("grey", "1240"), ("light blue", "4200"), ("shiny silver", "0926"), ("cream", "9020"), ("khaki", "2840"),
    ("petal pink", "5723"), ("ivory", "9002"), ("light grey", "1210"), ("optic white", "9104"),
    ("army green", "3258"),
]

COLLECTIONS = [  # (value, weight) measured on real crawls
    ("S_S_2026", 4501), ("F_W_2026", 4003), ("F_W_2025", 1470), ("F_W_2025/S_S_2026", 660),
    ("F_W_2026/S_S_2026", 497), ("F_W_2026/S_S_2026/S_S_2027", 448), ("S_S_2025", 423),
    ("F_W_2026/S_S_2027", 392), ("F_W_2025/F_W_2026/S_S_2026", 308), ("S_S_2026/S_S_2027", 161),
    ("F_W_2024/S_S_2025", 98), ("F_W_2024", 91),
]
STOCK_STATES = [("instock", 0.815), ("notifyMe", 0.137), ("outofstock", 0.044), ("preorder", 0.002),
                ("nonEcom", 0.002)]
SEASONAL_TAGS = ["winter 25 all", "all new arrivals", "summer 26 for women", "summer 26 for men",
                 "gifts for father's day", "new arrivals back to work view all", "fall_26"]

# --------------------------------------------------------------------------------------
# Batch calendar - one crawl per Monday. On the last Monday of each month the crawler runs
# an "extended" scope (16 markets) instead of the usual 8. This mirrors the real cadence:
# a weekly scope that Micro deliveries consume, and a monthly scope Macro deliveries consume.
# --------------------------------------------------------------------------------------
FIRST_CRAWL = date(2026, 7, 6)
N_WEEKS = 13                                   # 2026-07-06 ... 2026-09-28
EXTENDED_CRAWLS = {date(2026, 7, 27), date(2026, 8, 31), date(2026, 9, 28)}

# Price events (planted ground truth so the marts have a real signal to find)
SEPTEMBER_INCREASE = dict(
    effective=date(2026, 9, 7),
    families={"bags", "leather_goods", "slg"},
    share_of_products=0.85,
    pct_by_market={"FRA": 0.06, "USA": 0.07, "GBR": 0.06, "JPN": 0.08, "KOR": 0.05, "HKG": 0.06,
                   "ARE": 0.06, "CHN": 0.05},
    default_pct=0.06,
)
WEEKLY_INDIVIDUAL_CHANGE_SHARE = 0.0015       # ~0.15% of products re-priced per week (real: 1-2 per batch)

# Hero products for the Micro mart (the "pointers"). Forced into the catalogue in black,
# sold in every weekly market for the whole period, never discontinued.
HERO_PRODUCTS = [
    ("HERO-01", "bal_macro_women_leather_goods", "le city bag medium"),
    ("HERO-02", "bal_macro_women_bags", "rodeo handbag small"),
    ("HERO-03", "bal_macro_women_leather_goods", "hourglass handbag small"),
    ("HERO-04", "bal_macro_women_bags", "le cagole shoulder bag small"),
    ("HERO-05", "bal_macro_men_shoes", "triple s.2 sneaker"),
    ("HERO-06", "bal_macro_men_shoes", "3xl sneaker"),
    ("HERO-07", "bal_macro_women_slg", "le city card holder"),
    ("HERO-08", "bal_macro_women_leather_goods", "cash long coin and card holder large"),
]
