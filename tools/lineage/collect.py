"""Build the lineage graphs that render.py draws.

    python -m tools.lineage.collect --current          # today's DAG, from dbt/target/manifest.json (run `dbt parse`)
    python -m tools.lineage.collect --phase p4         # the DAG at the end of Phase 4, compiled from git
    python -m tools.lineage.collect --all-phases       # every phase in phases.yml

How a past phase is rebuilt: `git archive <ref> dbt` extracts the dbt project exactly as it was at the
commit that closed the phase, then `dbt deps` + `dbt parse` compile it (parse never connects to the
warehouse: the profile's credentials are placeholders). The resulting graph is committed in graphs/, so
the history is computed once and the site build only needs the current DAG.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import yaml

from tools.lineage.extract import extract

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "tools/lineage/phases.yml"
PARSE_ENV = {"DATABRICKS_SERVER_HOSTNAME": "parse-only.invalid",
             "DATABRICKS_HTTP_PATH": "/sql/1.0/warehouses/parse-only", "DATABRICKS_TOKEN": "parse-only",
             "DBT_PROFILES_DIR": str(ROOT / "ci")}


def write_graph(manifest: dict, out: Path) -> None:
    graph = extract(manifest)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(graph, indent=1) + "\n")
    print(f"{out.relative_to(ROOT)}: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges", file=sys.stderr)


def compile_ref(ref: str) -> dict:
    """The dbt manifest of the project as it was at a git ref (read-only for the repository)."""
    archive = subprocess.run(["git", "archive", "--format=tar", ref, "dbt"], cwd=ROOT,
                             capture_output=True, check=True).stdout
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            try:
                tar.extractall(tmp, filter="data")       # Python >= 3.10.12 / 3.11.4
            except TypeError:
                tar.extractall(tmp)                      # older Python: the archive is our own repository
        project = Path(tmp) / "dbt"
        env = {**os.environ, **PARSE_ENV}
        for cmd in (["dbt", "deps", "--quiet"], ["dbt", "parse", "--quiet"]):
            subprocess.run(cmd, cwd=project, env=env, check=True)
        return json.loads((project / "target/manifest.json").read_text())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build lineage graphs from dbt manifests.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--current", action="store_true", help="today's DAG from dbt/target/manifest.json")
    group.add_argument("--phase", help="one phase id from phases.yml")
    group.add_argument("--all-phases", action="store_true")
    args = parser.parse_args(argv)

    config = yaml.safe_load(CONFIG.read_text())
    graphs = ROOT / config["graphs_dir"]
    if args.current:
        manifest = ROOT / "dbt/target/manifest.json"
        if not manifest.exists():
            raise SystemExit("dbt/target/manifest.json not found: run `dbt parse` in dbt/ first.")
        write_graph(json.loads(manifest.read_text()), graphs / "current.json")
        return 0
    phases = config["phases"] if args.all_phases else [p for p in config["phases"] if p["id"] == args.phase]
    if not phases:
        raise SystemExit(f"Unknown phase {args.phase!r}. Known: {', '.join(p['id'] for p in config['phases'])}")
    for p in phases:
        write_graph(compile_ref(p["ref"]), graphs / f"{p['id']}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
