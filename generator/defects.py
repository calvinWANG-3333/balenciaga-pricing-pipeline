"""
Dirty-data injection + the answer key.

Plain English: a clean synthetic crawl would teach nothing. Real crawls arrive with prices
written as "1.250,00", names full of "&nbsp;", the same product twice, a market that silently
went missing... This module plants those problems on purpose AND writes down every single
one it planted (defect_manifest.csv). Later, the dbt QA layer is graded against that list:
every planted defect must be either fixed or quarantined - nothing silently dropped.

Defect families (same letters as docs/02_synthetic_data.md):
  A  price value format         B  currency / market consistency    C  text
  D  identity / keys            E  structure / schema drift          F  batch level
  G  semantic plausibility

expected_handling vocabulary:
  fix         deterministic, reversible repair in staging (raw value kept)
  quarantine  ambiguous or implausible -> excluded from marts, surfaced in a qa_ model
  warn        row/batch kept, but a warning test / QA model must surface it
  block       the whole file must not be loaded twice / must not be trusted as "latest"
"""

import copy
import random

from . import config

FULLWIDTH = str.maketrans("0123456789", "０１２３４５６７８９")
ARABIC_INDIC = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
NNBSP = " "   # narrow no-break space (French thousands separator)
NBSP = " "


def fmt_us(n: int) -> str:
    return f"{n:,}"


def fmt_eu_dot(n: int) -> str:
    return f"{n:,}".replace(",", ".") + ",00"


def fmt_fr_space(n: int) -> str:
    return f"{n:,}".replace(",", NNBSP) + ",00"


class DefectInjector:
    def __init__(self, rng: random.Random):
        self.rng = rng
        self.records: list[dict] = []        # row-level records; 'row' holds the row object
        self.batch_records: list[dict] = []  # batch-level records
        self.touched: set[int] = set()       # id() of rows that already carry a row-level defect

        # (code, family, rate, handling, function, description)
        self.row_defects = [
            ("A01_us_thousands_separator", "A", 0.004, "fix", self._a01, 'original_price "1,250"'),
            ("A02_eu_decimal_format", "A", 0.004, "fix", self._a02, 'original_price "1.250,00" / "1 250,00"'),
            ("A03_currency_symbol_in_price", "A", 0.003, "fix", self._a03, 'original_price "$1,250" / "1 250 €"'),
            ("A04_trailing_decimals", "A", 0.003, "fix", self._a04, 'original_price "1250.00"'),
            ("A05_price_on_request", "A", 0.0008, "quarantine", self._a05, 'original_price "Price upon request"'),
            ("A06_from_price", "A", 0.0005, "quarantine", self._a06, 'original_price "From 1,250"'),
            ("A07_placeholder_price", "A", 0.0005, "quarantine", self._a07, 'original_price "0" / "99999999"'),
            ("A08_non_ascii_digits", "A", 0.0015, "fix", self._a08, "full-width / Arabic-Indic digits"),
            ("A09_minor_units_leak", "A", 0.0008, "quarantine", self._a09, "original_price written x100"),
            ("A10_numeric_type_drift", "A", 0.002, "fix", self._a10, "original_price is a JSON number"),
            ("A11_dot_thousands_ambiguous", "A", 0.001, "fix", self._a11, 'original_price "2.490"'),
            ("B01_currency_code_notation", "B", 0.001, "fix", self._b01, 'original_currency "usd" / "$"'),
            ("C01_html_entity_in_name", "C", 0.003, "fix", self._c01, "&amp; / &nbsp; / &#39; in name"),
            ("C02_whitespace_noise", "C", 0.005, "fix", self._c02, "leading/trailing/double/NBSP/newline"),
            ("C03_mojibake", "C", 0.004, "fix", self._c03, "UTF-8 read as Latin-1 (Ã© / å¥³å£«)"),
            ("C04_missing_name", "C", 0.0005, "quarantine", self._c04, "name empty or null"),
            ("C05_case_drift", "C", 0.002, "fix", self._c05, "name in UPPER or Title Case"),
            ("D01_exact_duplicate_row", "D", 0.003, "fix", None, "identical row delivered twice"),
            ("D02_conflicting_duplicate", "D", 0.0005, "quarantine", None, "same objectID, different price"),
            ("D03_sku_format_variant", "D", 0.002, "fix", self._d03, "sku lower-case / spaced / hyphenated"),
            ("D04_missing_sku", "D", 0.0005, "fix", self._d04, "skus = [] (recoverable from objectID)"),
            ("E01_missing_price_value", "E", 0.003, "fix", self._e01, "price.price key absent"),
            ("E02_null_url", "E", 0.0005, "warn", self._e02, "url is null"),
            ("E03_empty_preview_url", "E", 0.008, "warn", self._e03, 'previewUrl ""'),
            ("E05_boolean_as_string", "E", 0.001, "fix", self._e05, 'isValid "true"'),
            ("E06_missing_market_field", "E", 0.0005, "fix", self._e06, "market key absent (derive from source)"),
            ("G01_unit_scale_error", "G", 0.0005, "quarantine", self._g01, "price x10 or /10 vs truth"),
            ("G03_http_error_row", "G", 0.001, "quarantine", self._g03, "status 404, isValid false"),
            ("G04_isvalid_contradiction", "G", 0.0005, "quarantine", self._g04, "validationErrors present, isValid true"),
        ]

    # ------------------------------------------------------------------ helpers
    def _record(self, row, code, family, handling, field, clean, dirty, note=""):
        self.touched.add(id(row))
        self.records.append(dict(row=row, object_id=row.get("objectID"), defect_code=code,
                                 defect_family=family, field=field, clean_value=clean,
                                 dirty_value=dirty, expected_handling=handling, note=note))

    @staticmethod
    def _n(row) -> int:
        return int(row["price"]["original_price"])

    # ------------------------------------------------------------------ family A
    def _a01(self, row):
        n = self._n(row)
        if n < 1000:
            return None
        row["price"]["original_price"] = fmt_us(n)
        return "price.original_price", str(n), row["price"]["original_price"]

    def _a02(self, row):
        n = self._n(row)
        if n < 1000:
            return None
        row["price"]["original_price"] = fmt_fr_space(n) if row["market"] == "FRA" else fmt_eu_dot(n)
        return "price.original_price", str(n), row["price"]["original_price"]

    def _a03(self, row):
        n = self._n(row)
        cur = row["price"]["original_currency"]
        if cur == "EUR":
            v = f"{n:,}".replace(",", NNBSP) + NBSP + "€"
        else:
            v = config.CURRENCY_SYMBOL[cur] + fmt_us(n)
        row["price"]["original_price"] = v
        return "price.original_price", str(n), v

    def _a04(self, row):
        n = self._n(row)
        if row["price"]["original_currency"] in ("JPY", "KRW"):
            return None                                   # zero-decimal currencies never show .00
        row["price"]["original_price"] = f"{n}.00"
        return "price.original_price", str(n), row["price"]["original_price"]

    def _a05(self, row):
        n = self._n(row)
        text = {"FRA": "Sur demande", "CHN": "价格请咨询"}.get(row["market"], "Price upon request")
        row["price"]["original_price"] = text
        row["price"].pop("price", None)
        return "price.original_price", str(n), text

    def _a06(self, row):
        n = self._n(row)
        if row["market"] == "FRA":
            v = "À partir de " + f"{n:,}".replace(",", NNBSP) + NBSP + "€"
        else:
            v = "From " + fmt_us(n)
        row["price"]["original_price"] = v
        return "price.original_price", str(n), v

    def _a07(self, row):
        n = self._n(row)
        v = self.rng.choice(["0", "99999999"])
        row["price"]["original_price"] = v
        row["price"]["price"] = int(v) * config.MARKETS[row["market"]]["minor_scale"]
        return "price.original_price", str(n), v

    def _a08(self, row):
        n = self._n(row)
        if row["market"] in ("JPN", "CHN", "KOR", "HKG", "TWN"):
            v = str(n).translate(FULLWIDTH)
        elif row["market"] in ("ARE", "SAU"):
            v = str(n).translate(ARABIC_INDIC)
        else:
            return None
        row["price"]["original_price"] = v
        return "price.original_price", str(n), v

    def _a09(self, row):
        n = self._n(row)
        row["price"]["original_price"] = str(n * 100)
        return "price.original_price", str(n), row["price"]["original_price"]

    def _a10(self, row):
        n = self._n(row)
        row["price"]["original_price"] = n
        return "price.original_price", str(n), str(n) + " (number)"

    def _a11(self, row):
        n = self._n(row)
        if not (1000 <= n < 1_000_000) or row["price"]["original_currency"] in ("JPY", "KRW"):
            return None
        row["price"]["original_price"] = f"{n:,}".replace(",", ".")
        return "price.original_price", str(n), row["price"]["original_price"]

    # ------------------------------------------------------------------ family B
    def _b01(self, row):
        cur = row["price"]["original_currency"]
        v = self.rng.choice([cur.lower(), config.CURRENCY_SYMBOL[cur].strip()])
        row["price"]["original_currency"] = v
        return "price.original_currency", cur, v

    # ------------------------------------------------------------------ family C
    def _c01(self, row):
        name = row["name"]
        if " and " in name:
            v = name.replace(" and ", " &amp; ", 1)
        elif "'" in name:
            v = name.replace("'", "&#39;", 1)
        elif " " in name:
            v = name.replace(" ", "&nbsp;", 1)
        else:
            return None
        row["name"] = v
        return "name", name, v

    def _c02(self, row):
        name = row["name"]
        kind = self.rng.choice(["lead", "trail", "double", "nbsp", "newline"])
        if kind == "lead":
            v = "  " + name
        elif kind == "trail":
            v = name + " "
        elif kind == "double" and " " in name:
            v = name.replace(" ", "  ", 1)
        elif kind == "nbsp" and " " in name:
            v = name.replace(" ", NBSP, 1)
        else:
            v = name + "\n"
        row["name"] = v
        return "name", name, v

    def _c03(self, row):
        if row["market"] not in ("FRA", "CHN"):
            return None
        cats = row["categories"]
        idx = next((i for i, c in enumerate(cats) if any(ord(ch) > 127 for ch in c)), None)
        if idx is None:
            return None
        clean = cats[idx]
        dirty = clean.encode("utf-8").decode("latin-1")
        cats[idx] = dirty
        for d in row["productDetails"]:
            if d["value"] == clean:
                d["value"] = dirty
        return f"categories[{idx}]", clean, dirty

    def _c04(self, row):
        name = row["name"]
        row["name"] = self.rng.choice(["", None])
        return "name", name, repr(row["name"])

    def _c05(self, row):
        name = row["name"]
        v = name.upper() if self.rng.random() < 0.5 else name.title()
        if v == name:
            return None
        row["name"] = v
        return "name", name, v

    # ------------------------------------------------------------------ family D
    def _d03(self, row):
        sku = row["skus"][0]
        kind = self.rng.choice(["lower", "space", "hyphen"])
        if kind == "lower":
            v = sku.lower()
        elif kind == "space":
            v = " " + sku + " "
        else:
            v = f"{sku[:6]}-{sku[6:11]}-{sku[11:]}"
        row["skus"][0] = v
        row["objectID"] = f"{config.BRAND_SLUG}_{row['market']}_{v.strip()}"   # identity breaks too
        return "skus[0]", sku, v

    def _d04(self, row):
        clean = list(row["skus"])
        row["skus"] = []
        return "skus", "|".join(clean), "[]"

    # ------------------------------------------------------------------ family E
    def _e01(self, row):
        if "price" not in row["price"]:
            return None
        v = row["price"].pop("price")
        return "price.price", str(v), "<absent>"

    def _e02(self, row):
        clean = row["url"]
        row["url"] = None
        return "url", clean, "null"

    def _e03(self, row):
        clean = row["previewUrl"]
        row["previewUrl"] = ""
        return "previewUrl", clean, '""'

    def _e05(self, row):
        row["isValid"] = "true"
        return "isValid", "true (boolean)", '"true" (string)'

    def _e06(self, row):
        m = row.pop("market")
        return "market", m, "<absent>"

    # ------------------------------------------------------------------ family G
    def _g01(self, row):
        n = self._n(row)
        factor = self.rng.choice([10, 0.1])
        v = int(round(n * factor))
        row["price"]["original_price"] = str(v)
        row["price"]["price"] = v * config.MARKETS[row["market"]]["minor_scale"]
        return "price.original_price", str(n), str(v)

    def _g03(self, row):
        n = self._n(row)
        row["status"] = 404
        row["isValid"] = False
        row["validationErrors"] = ["price must be greater than 0"]
        row["price"]["original_price"] = "0"
        row["price"]["price"] = 0
        return "status", f"200 / {n}", "404 / 0"

    def _g04(self, row):
        row["validationErrors"] = ["price.price is missing"]
        clean = row["price"].pop("price", None)
        return "validationErrors", f"[] / price={clean}", "['price.price is missing'] / isValid=true"

    # ------------------------------------------------------------------ main entry
    def apply_row_defects(self, rows: list[dict]) -> list[dict]:
        """At most one row-level defect per row, so each planted defect is gradable on its own."""
        out = []
        for row in rows:
            out.append(row)
            u = self.rng.random()
            for code, fam, rate, handling, fn, _desc in self.row_defects:
                if u >= rate:
                    u -= rate
                    continue
                if code in ("D01_exact_duplicate_row", "D02_conflicting_duplicate"):
                    self.touched.add(id(row))
                if code == "D01_exact_duplicate_row":
                    dup = copy.deepcopy(row)
                    out.append(dup)
                    self._record(dup, code, fam, handling, "<row>", "", "duplicate of previous line")
                elif code == "D02_conflicting_duplicate":
                    dup = copy.deepcopy(row)
                    n = self._n(dup)
                    v = int(round(n * self.rng.uniform(1.05, 1.20), -1))
                    dup["price"]["original_price"] = str(v)
                    dup["price"]["price"] = v * config.MARKETS[dup["market"]]["minor_scale"]
                    dup["url"] = dup["url"] + "?variant=2"
                    out.append(dup)
                    self._record(dup, code, fam, handling, "price.original_price", str(n), str(v),
                                 "second row with same objectID")
                else:
                    res = fn(row)
                    if res:
                        field, clean, dirty = res
                        self._record(row, code, fam, handling, field, clean, dirty)
                break
        return out

    # ------------------------------------------------------------------ chunk / batch level
    def geo_redirect(self, rows, market, n_rows, eur_lookup):
        """B02: the crawler hit the site from a European IP and was served EUR prices."""
        hit = 0
        for row in rows:
            if (row.get("market") != market or hit >= n_rows or id(row) in self.touched
                    or row["price"]["original_currency"] != "USD"):
                continue
            clean = row["price"]["original_price"]
            eur = eur_lookup(row)
            if eur is None:
                continue
            row["price"]["original_price"] = str(eur)
            row["price"]["original_currency"] = "EUR"
            row["price"]["price"] = eur * 100
            self._record(row, "B02_geo_redirect_currency", "B", "quarantine", "price.original_currency",
                         f"USD {clean}", f"EUR {eur}")
            hit += 1

    def seconds_timestamps(self, rows, market):
        """E04: one market's crawler wrote epoch SECONDS instead of milliseconds."""
        for row in rows:
            if row.get("market") != market:
                continue
            clean = row["createdAt"]
            for k in ("createdAt", "updatedAt", "releasedAt"):
                row[k] = row[k] // 1000
            self._record(row, "E04_epoch_seconds_timestamp", "E", "fix", "createdAt", str(clean),
                         str(row["createdAt"]))

    def non_product_rows(self, rows, ts_ms, markets=("USA", "FRA", "GBR")):
        """G02: gift cards and a test page scraped as if they were products."""
        extra = []
        for m in markets:
            mc = config.MARKETS[m]
            for amount in (100, 250, 500):
                sku = f"GIFTCARD{amount}"
                extra.append(self._fake_row(m, mc, sku, "e-gift card", amount, ts_ms))
            if self.rng.random() < 0.5:
                extra.append(self._fake_row(m, mc, "TEST0000000000", "test product - do not buy", 1, ts_ms))
        for row in extra:
            self._record(row, "G02_non_product_page", "G", "quarantine", "<row>", "",
                         f"{row['name']} @ {row['price']['original_price']}")
        return rows + extra

    @staticmethod
    def _fake_row(market, mc, sku, name, amount, ts_ms):
        return {
            "objectID": f"{config.BRAND_SLUG}_{market}_{sku}", "brandId": config.BRAND_ID, "name": name,
            "url": f"https://www.balenciaga.com/{mc['locale']}/{sku.lower()}.html",
            "price": {"original_price": str(amount), "original_currency": mc["currency"],
                      "price": amount * mc["minor_scale"], "currency": "EUR", "is_discounted": False},
            "categories": ["GIFTS"], "productDetails": [{"key": "list", "value": "productList"}],
            "previewUrl": "", "status": 200, "source": f"{config.BRAND_SLUG}_{market}",
            "importSource": config.IMPORT_SOURCE, "crawlerName": "BalenciagaInternational",
            "createdAt": ts_ms, "updatedAt": ts_ms, "releasedAt": ts_ms, "skus": [sku],
            "market": market, "validationErrors": [], "isValid": True,
        }

    def batch_record(self, file_name, code, handling, detail, market=""):
        self.batch_records.append(dict(file_name=file_name, defect_code=code, defect_family="F",
                                       market=market, expected_handling=handling, detail=detail))
