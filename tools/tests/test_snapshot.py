"""BI snapshot: exact cell formatting and the guarantees checked before anything is written."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from tools.snapshot.export import SnapshotError, cell, check_config, check_released, to_csv


def test_cells_are_exact_and_stable():
    assert cell(Decimal("10900.00")) == "10900.00"
    assert cell(date(2026, 9, 29)) == "2026-09-29"
    assert cell(datetime(2026, 10, 8, 10, 44, 20, 123)) == "2026-10-08 10:44:20"
    assert cell(True) == "true" and cell(None) == ""
    assert cell(["lfl_change_bounds", "hero_large_moves"]) == "lfl_change_bounds; hero_large_moves"
    assert to_csv([{"a": 1, "b": "x,y"}], ["a", "b"]) == 'a,b\n1,"x,y"\n'


def test_refuses_non_public_models():
    with pytest.raises(SnapshotError, match="non-public"):
        check_config([{"model": "int_catalogue__as_of"}], {"pub_dim_market": ["market"]})


def test_refuses_an_unreleased_delivery():
    released = [{"scope": "micro", "as_of_date": date(2026, 9, 29)}]
    check_released({"released_deliveries": released, "hero_prices_weekly": [{"delivery_date": date(2026, 9, 29)}]})
    with pytest.raises(SnapshotError, match="Unreleased"):
        check_released({"released_deliveries": released,
                        "hero_prices_weekly": [{"delivery_date": date(2026, 10, 6)}]})
    with pytest.raises(SnapshotError, match="No released delivery"):
        check_released({"released_deliveries": []})


def test_masks_rewrite_only_the_declared_column():
    from tools.snapshot.export import apply_masks
    rows = [{"legacy_file": "XYZ_2026-09-15_1789_balenciaga.ndjson.gz", "market": "XYZ_2026-09-15_"},
            {"legacy_file": None, "market": "FRA"}]
    mask = [{"column": "legacy_file", "pattern": r"^[A-Za-z]+_(?=\d{4}-\d{2}-\d{2}_)", "replace": "crawl_"}]
    out = apply_masks(rows, mask)
    assert out[0]["legacy_file"] == "crawl_2026-09-15_1789_balenciaga.ndjson.gz"
    assert out[0]["market"] == "XYZ_2026-09-15_"          # other columns untouched
    assert out[1]["legacy_file"] is None                  # non-strings untouched
    assert rows[0]["legacy_file"].startswith("XYZ_")      # input not mutated


def test_committed_incident_snapshot_is_masked():
    import yaml
    from tools.snapshot.export import ROOT, CONFIG
    config = yaml.safe_load(CONFIG.read_text())
    t = next(t for t in config["tables"] if t["file"] == "incident_replay")
    assert t.get("mask"), "incident_replay must declare its mask"
    text = (ROOT / config["output_dir"] / "incident_replay.csv").read_text()
    assert ",crawl_2026-" in text
    import re
    assert not re.search(r",[A-Za-z]+_\d{4}-\d{2}-\d{2}_", text.replace(",crawl_", ","))
