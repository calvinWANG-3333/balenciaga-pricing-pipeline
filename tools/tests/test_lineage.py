"""Lineage pictures: extraction from a manifest, and the layout rules the pictures rely on."""

import json
from pathlib import Path

import pytest
import yaml

from tools.lineage import render
from tools.lineage.extract import extract

ROOT = Path(__file__).resolve().parents[2]
CONFIG = yaml.safe_load((ROOT / "tools/lineage/phases.yml").read_text())
GRAPHS = ROOT / CONFIG["graphs_dir"]


def load_union():
    graphs = [json.loads((GRAPHS / f"{p['id']}.json").read_text()) for p in CONFIG["phases"]]
    current = GRAPHS / "current.json"
    if current.exists():
        graphs.append(json.loads(current.read_text()))
    return graphs, render.union(graphs)


def test_extract_keeps_only_the_project_data_flow():
    def model(name, path, deps=()):
        return {"resource_type": "model", "package_name": "balenciaga_pricing", "name": name,
                "original_file_path": path, "depends_on": {"nodes": list(deps)}, "config": {}}
    manifest = {
        "nodes": {
            "model.balenciaga_pricing.stg_a": model("stg_a", "models/staging/stg_a.sql", ["source.balenciaga_pricing.raw.a"]),
            "model.balenciaga_pricing.fct_a": model("fct_a", "models/marts/core/fct_a.sql", ["model.balenciaga_pricing.stg_a"]),
            "model.balenciaga_pricing.my_first": model("my_first", "models/example/my_first.sql"),
            "test.balenciaga_pricing.unique_x": {"resource_type": "test", "package_name": "balenciaga_pricing"},
            "model.dbt_utils.x": {**model("x", "models/x.sql"), "package_name": "dbt_utils"},
        },
        "sources": {"source.balenciaga_pricing.raw.a": {"resource_type": "source", "package_name": "balenciaga_pricing",
                                                         "name": "a", "source_name": "raw", "original_file_path": "models/staging/_s.yml"}},
    }
    g = extract(manifest)
    assert [n["name"] for n in g["nodes"]] == ["fct_a", "stg_a", "raw.a"]
    assert {n["name"]: n["layer"] for n in g["nodes"]} == {"fct_a": "marts", "stg_a": "staging", "raw.a": "sources"}
    assert g["edges"] == [["model.balenciaga_pricing.stg_a", "model.balenciaga_pricing.fct_a"],
                          ["source.balenciaga_pricing.raw.a", "model.balenciaga_pricing.stg_a"]]


def test_every_phase_has_a_graph_with_consistent_edges():
    for p in CONFIG["phases"]:
        g = json.loads((GRAPHS / f"{p['id']}.json").read_text())
        ids = {n["id"] for n in g["nodes"]}
        assert all(a in ids and b in ids for a, b in g["edges"]), p["id"]


def test_layout_every_arrow_points_right_and_nothing_overlaps():
    _, u = load_union()
    boxes = render.layout(u)
    for a, b in u["edges"]:
        assert boxes[b].x >= boxes[a].x + boxes[a].w, (a, b)            # left to right, always
    by_col = {}
    for b in boxes.values():
        by_col.setdefault((b.band, b.col), []).append(b.y)
    for ys in by_col.values():
        ys.sort()
        assert all(y2 - y1 >= render.BOX_H for y1, y2 in zip(ys, ys[1:]))
    main_bottom = max(b.y for b in boxes.values() if b.band == "main")
    assert all(b.y > main_bottom for b in boxes.values() if b.band == "quality")


def test_rendering_is_deterministic_and_marks_new_nodes():
    graphs, u = load_union()
    boxes = render.layout(u)
    first = render.render(u, boxes, graphs[1], graphs[0])
    assert first == render.render(u, render.layout(u), graphs[1], graphs[0])
    added = {n["id"] for n in graphs[1]["nodes"]} - {n["id"] for n in graphs[0]["nodes"]}
    assert first.count('class="node new"') == len(added & set(u["nodes"]))


@pytest.mark.parametrize("phase", [p["id"] for p in CONFIG["phases"]])
def test_phase_picture_exists(phase):
    assert (ROOT / CONFIG["output_dir"] / f"lineage_{phase}.svg").exists()
