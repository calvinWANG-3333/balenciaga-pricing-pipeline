"""Export the public interface of the warehouse to CSV files: the data the BI site is built from.

    QA_SCHEMA_PREFIX="" python -m tools.snapshot.export          # production (bare schema names)
    python -m tools.snapshot.export                              # your dev schemas (dbt_rwang_*)
    python -m tools.snapshot.export --check                      # verify the committed files, write nothing

Why a snapshot and not a live connection: the site is static (GitHub Pages). It is rebuilt from files in
the repository, so it builds the same way for anyone, costs nothing, and never depends on a warehouse
being awake. The manifest records where the snapshot came from, so every number on the site can be
traced back to a dbt run.

Guarantees, checked before anything is written:
  - every exported model is PUBLIC in the dbt manifest (access: public): BI never reads internal models
  - at least one delivery is released (an empty published layer means the gate has not run)
  - every delivery date in the Micro and Macro tables is a released delivery

Masks: a table may declare `mask: [{column, pattern, replace}]` in snapshot.yml. The regex rewrite is applied
to that column before the CSV is written, and the manifest lists the masked columns. Used to keep internal
naming out of the public files (the crawler's file-name prefix is reduced to a neutral `crawl_`).
Connection settings are the delivery gate's (qa/config.py): QA_BACKEND, QA_CATALOG, QA_SCHEMA_PREFIX,
DATABRICKS_*.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import yaml

from qa.backends import connect
from qa.config import Settings

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "tools/snapshot/snapshot.yml"
PROJECT = "balenciaga_pricing"


class SnapshotError(SystemExit):
    pass


# ------------------------------------------------------------------------------------------- values

def cell(value) -> str:
    """One CSV cell. Exact and stable: decimals keep their digits, dates are ISO, lists are '; '-joined."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.replace(tzinfo=None).isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return repr(round(value, 10))
    if hasattr(value, "tolist"):                     # numpy arrays (Databricks connector)
        value = value.tolist()
    if isinstance(value, (list, tuple)):
        return "; ".join(cell(v) for v in value)
    return str(value)


def to_csv(rows: list[dict], columns: list[str]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(columns)
    for r in rows:
        w.writerow([cell(r.get(c)) for c in columns])
    return buf.getvalue()


# ------------------------------------------------------------------------------------------- checks

def public_models(manifest_path: Path) -> dict[str, list[str]]:
    """Public models of the project -> their contracted column names, from dbt's manifest."""
    if not manifest_path.exists():
        raise SnapshotError(f"{manifest_path} not found: run `dbt parse` in dbt/ first.")
    manifest = json.loads(manifest_path.read_text())
    out = {}
    for node in manifest["nodes"].values():
        if node["resource_type"] == "model" and node["package_name"] == PROJECT and node.get("access") == "public":
            out[node["name"]] = list(node.get("columns", {}))
    return out


def check_config(tables: list[dict], public: dict[str, list[str]]) -> None:
    private = [t["model"] for t in tables if t["model"] not in public]
    if private:
        raise SnapshotError("Refusing to export non-public models (BI reads only access: public): "
                            + ", ".join(private))


def check_released(data: dict[str, list[dict]]) -> None:
    released = {(r["scope"], cell(r["as_of_date"])) for r in data.get("released_deliveries", [])}
    if not released:
        raise SnapshotError("No released delivery: run the delivery gate (python -m qa.gate audit) first.")
    micro = {cell(r["delivery_date"]) for r in data.get("hero_prices_weekly", [])}
    macro = {cell(r["as_of_date"]) for r in data.get("category_monthly", [])}
    stray = sorted({("micro", d) for d in micro} - released) + sorted({("macro", d) for d in macro} - released)
    if stray:
        raise SnapshotError(f"Unreleased deliveries in the published layer: {stray[:5]}")


# ------------------------------------------------------------------------------------------- export

def git_sha() -> str | None:
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"][:7]
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def apply_masks(rows: list[dict], masks: list[dict]) -> list[dict]:
    """Rewrite masked columns with their regex. Values that are not strings (None, numbers) are left alone."""
    if not masks:
        return rows
    compiled = [(m["column"], re.compile(m["pattern"]), m["replace"]) for m in masks]
    out = []
    for r in rows:
        r = dict(r)
        for col, pat, rep in compiled:
            if isinstance(r.get(col), str):
                r[col] = pat.sub(rep, r[col])
        out.append(r)
    return out


def export(settings: Settings, config: dict, manifest_path: Path, check_only: bool = False) -> dict:
    tables = config["tables"]
    public = public_models(manifest_path)
    check_config(tables, public)

    db = connect(settings)
    try:
        data, columns = {}, {}
        for t in tables:
            relation = f"{settings.schema(t['layer'])}.{t['model']}"
            cols = public[t["model"]]
            sql = f"select {', '.join(cols)} from {relation} order by {', '.join(t['order_by'])}"
            data[t["file"]] = apply_masks(db.query(sql), t.get("mask", []))
            columns[t["file"]] = cols
            print(f"  {t['file']:<24} {len(data[t['file']]):>6} rows   <- {relation}", file=sys.stderr)
    finally:
        db.close()
    check_released(data)

    out_dir = ROOT / config["output_dir"]
    files = {}
    for t in tables:
        text = to_csv(data[t["file"]], columns[t["file"]])
        path = out_dir / f"{t['file']}.csv"
        files[t["file"]] = {"model": t["model"], "rows": len(data[t["file"]]), "columns": columns[t["file"]],
                            "sha256": hashlib.sha256(text.encode()).hexdigest()}
        if t.get("mask"):
            files[t["file"]]["masked"] = [m["column"] for m in t["mask"]]
        if check_only:
            if not path.exists() or path.read_text() != text:
                raise SnapshotError(f"{path.relative_to(ROOT)} differs from the warehouse: re-export it.")
        else:
            out_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(text)

    manifest = {
        "exported_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": {"backend": settings.backend, "schema_prefix": settings.schema_prefix or "(production)",
                   "git_sha": git_sha()},
        "released_deliveries": len(data["released_deliveries"]),
        "tables": files,
    }
    if not check_only:
        (ROOT / config["manifest"]).write_text(json.dumps(manifest, indent=1) + "\n")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--manifest", default=str(ROOT / "dbt/target/manifest.json"),
                        help="dbt manifest used to check that every exported model is public")
    parser.add_argument("--check", action="store_true", help="compare with the committed files, write nothing")
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    config = yaml.safe_load(CONFIG.read_text())
    where = "production" if not settings.schema_prefix else f"{settings.schema_prefix}_*"
    print(f"Snapshot of the public interface ({settings.backend}, {where}):", file=sys.stderr)
    m = export(settings, config, Path(args.manifest), check_only=args.check)
    verb = "matches" if args.check else "written to"
    print(f"{len(m['tables'])} tables, {m['released_deliveries']} released deliveries - {verb} "
          f"{config['output_dir']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
