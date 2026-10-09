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
