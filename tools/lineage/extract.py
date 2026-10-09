"""dbt manifest.json -> a small, stable lineage graph (JSON).

The manifest is dbt's compiled map of the project: every model, source, seed, exposure and semantic model,
and what each one depends on. It is large (~2 MB) and changes with every parse. This module keeps only
what a lineage picture needs, in a form small enough to commit, diff and review:

    {"nodes": [{"id", "name", "type", "layer", "folder", "materialized", "access"}],
     "edges": [["parent_id", "child_id"], ...]}

Tests, operations, metrics and the nodes of installed packages (dbt_utils, dbt_project_evaluator) are
left out: the picture is about this project's own data flow.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT = "balenciaga_pricing"

# the folder right under models/ decides the layer of a model
MODEL_LAYERS = ("staging", "intermediate", "marts", "published", "semantic", "quality")


def _layer(node: dict) -> str | None:
    kind = node["resource_type"]
    if kind == "source":
        return "sources"
    if kind == "seed":
        return "seeds"
    if kind == "exposure":
        return "exposures"
    if kind == "semantic_model":
        return "semantic"
    if kind == "model":
        top = Path(node["original_file_path"]).parts[1]          # models/<top>/...
        return top if top in MODEL_LAYERS else None              # e.g. dbt's example/ models
    return None


def _folder(node: dict) -> str:
    parts = Path(node.get("original_file_path", "")).parts
    return "/".join(parts[1:-1]) if len(parts) > 2 else ""


def extract(manifest: dict) -> dict:
    pool = {**manifest["nodes"], **manifest["sources"], **manifest.get("exposures", {}),
            **manifest.get("semantic_models", {})}
    nodes = {}
    for uid, node in pool.items():
        if node.get("package_name") != PROJECT:
            continue
        layer = _layer(node)
        if layer is None:
            continue
        name = f"{node['source_name']}.{node['name']}" if node["resource_type"] == "source" else node["name"]
        config = node.get("config") or {}
        nodes[uid] = {
            "id": uid,
            "name": name,
            "type": node["resource_type"],
            "layer": layer,
            "folder": _folder(node),
            "materialized": config.get("materialized"),
            "access": node.get("access") or config.get("access"),
        }
    edges = sorted({(parent, uid)
                    for uid, node in pool.items() if uid in nodes
                    for parent in (node.get("depends_on") or {}).get("nodes", [])
                    if parent in nodes})
    return {"nodes": sorted(nodes.values(), key=lambda n: n["id"]), "edges": [list(e) for e in edges]}


if __name__ == "__main__":
    # python tools/lineage/extract.py dbt/target/manifest.json out.json
    graph = extract(json.loads(Path(sys.argv[1]).read_text()))
    Path(sys.argv[2]).write_text(json.dumps(graph, indent=1) + "\n")
    print(f"{len(graph['nodes'])} nodes, {len(graph['edges'])} edges -> {sys.argv[2]}")
