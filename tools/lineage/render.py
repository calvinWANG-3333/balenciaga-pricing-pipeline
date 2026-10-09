"""Lineage graphs (one JSON per phase, see extract.py) -> SVG pictures.

    python -m tools.lineage.render            # reads tools/lineage/phases.yml, writes site/src/lineage/*.svg

Pictures:
    lineage_full.svg          the whole DAG as it is today
    lineage_<phase>.svg       the DAG as it was at the end of that phase: nodes added in the phase in black,
                              nodes built earlier outlined, nodes still to come as faint placeholders

Every picture uses ONE layout, computed on the union of all phases, so a node never moves from one
picture to the next: scrolling through the phases, the reader sees the pipeline grow in place.

Layout, in plain words:
  - columns follow the layers of the project, left to right: sources and seeds, staging, intermediate,
    marts, published, semantic layer, exposures. A layer whose models read each other takes several
    columns (a model sits one column right of its right-most parent), so every arrow points right.
  - the QA lane (models/quality) gets its own band under the main flow: it reads the pipeline, the
    pipeline never reads it.
  - inside a column, nodes are ordered and placed near the average height of their parents
    (barycenter heuristic), which keeps most arrows short and straight.
Pure Python, no Graphviz: the output is deterministic, so a changed picture in a pull request always
means a changed DAG.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from html import escape
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]

LANES = ["sources", "staging", "intermediate", "marts", "published", "semantic", "exposures"]
LANE_TITLES = {"sources": "Sources · Seeds", "staging": "Staging", "intermediate": "Intermediate",
               "marts": "Marts", "published": "Published", "semantic": "Semantic layer",
               "exposures": "Exposures"}
QUALITY = "quality"

# --- the design system (shared with the site) -------------------------------------------------------
BG, INK, PAPER, MUTED, GHOST = "#E4E4E1", "#0B0B0B", "#F7F7F5", "#7A7A74", "#C2C2BD"
FONT_SANS = "'Archivo', 'Helvetica Neue', Helvetica, Arial, sans-serif"
FONT_MONO = "'JetBrains Mono', 'SFMono-Regular', Menlo, Consolas, monospace"
LABEL_PX, CHAR_W = 11, 6.7          # monospace label size and the width of one character
BOX_H, ROW_GAP, COL_GAP, PAD_X = 24, 12, 46, 10
MARGIN, HEADER_H, BAND_GAP, LEGEND_H = 40, 46, 70, 54


@dataclass
class Box:
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    col: int = 0
    band: str = "main"


def lane_of(node: dict) -> str:
    return "sources" if node["layer"] in ("sources", "seeds") else node["layer"]


# ------------------------------------------------------------------------------------------- layout

def union(graphs: list[dict]) -> dict:
    nodes, edges = {}, set()
    for g in graphs:
        for n in g["nodes"]:
            nodes[n["id"]] = n                       # latest description wins
        edges.update(map(tuple, g["edges"]))
    used = {x for e in edges for x in e}
    # a source nothing reads is noise in a lineage picture (the answer key's documentation-only tables)
    nodes = {k: v for k, v in nodes.items() if k in used or v["layer"] != "sources"}
    edges = {e for e in edges if e[0] in nodes and e[1] in nodes}
    return {"nodes": nodes, "edges": sorted(edges)}


def layout(graph: dict) -> dict[str, Box]:
    nodes, edges = graph["nodes"], graph["edges"]
    parents: dict[str, list[str]] = {k: [] for k in nodes}
    children: dict[str, list[str]] = {k: [] for k in nodes}
    for a, b in edges:
        parents[b].append(a)
        children[a].append(b)

    # 1. columns: each lane starts right of the previous one; a node sits right of all its parents
    cols: dict[str, int] = {}
    lane_start: dict[str, int] = {}

    def start_of(lane: str) -> int:
        if lane not in lane_start:
            i = LANES.index(lane)
            prev = [col(k) for k, n in nodes.items() if i and lane_of(n) == LANES[i - 1]]
            lane_start[lane] = (max(prev) + 1) if prev else (start_of(LANES[i - 1]) + 1 if i else 0)
        return lane_start[lane]

    def col(k: str) -> int:
        if k not in cols:
            after = max((col(p) + 1 for p in parents[k]), default=0)
            lane = lane_of(nodes[k])
            cols[k] = after if lane == QUALITY else max(start_of(lane), after)
        return cols[k]

    for k in sorted(nodes):
        col(k)
    for lane in LANES:                                   # empty lanes still get a start
        start_of(lane)

    boxes = {k: Box(col=cols[k], band="quality" if lane_of(n) == QUALITY else "main",
                    w=len(n["name"]) * CHAR_W + 2 * PAD_X) for k, n in nodes.items()}

    # 2. order inside each column (barycenter sweeps), separately for the main flow and the QA band
    n_cols = max(cols.values()) + 1
    for band in ("main", "quality"):
        grid = [sorted((k for k, b in boxes.items() if b.band == band and b.col == c),
                       key=lambda k: (nodes[k]["folder"], nodes[k]["name"])) for c in range(n_cols)]
        pos = {k: i for column in grid for i, k in enumerate(column)}

        def bary(k: str, links: dict[str, list[str]]) -> float:
            same = [pos[x] for x in links[k] if x in pos and boxes[x].band == band]
            return sum(same) / len(same) if same else pos[k]

        for _ in range(6):
            for c in range(n_cols):
                grid[c].sort(key=lambda k: bary(k, parents))
                pos.update({k: i for i, k in enumerate(grid[c])})
            for c in reversed(range(n_cols)):
                grid[c].sort(key=lambda k: bary(k, children))
                pos.update({k: i for i, k in enumerate(grid[c])})

        # 3. vertical positions: near the parents' average height, never overlapping
        step = BOX_H + ROW_GAP
        for c in range(n_cols):
            prev_bottom = -step
            for k in grid[c]:
                ys = [boxes[p].y for p in parents[k] if boxes[p].band == band and boxes[p].col < c]
                want = sum(ys) / len(ys) if ys else prev_bottom + step
                boxes[k].y = max(want, prev_bottom + step)
                prev_bottom = boxes[k].y

    # 4. x: column widths from their longest label
    widths = [max((b.w for b in boxes.values() if b.col == c), default=0) for c in range(n_cols)]
    xs, x = [], MARGIN
    for w in widths:
        xs.append(x)
        x += w + COL_GAP
    for b in boxes.values():
        b.x = xs[b.col]
        b.w = widths[b.col]

    # 5. stack the QA band under the main flow
    main_bottom = max(b.y for b in boxes.values() if b.band == "main")
    q_top = min((b.y for b in boxes.values() if b.band == "quality"), default=0)
    for b in boxes.values():
        if b.band == "main":
            b.y += MARGIN + HEADER_H
        else:
            b.y += MARGIN + HEADER_H + main_bottom + BOX_H + BAND_GAP - q_top
    return boxes


# ------------------------------------------------------------------------------------------- drawing

def _node_svg(n: dict, b: Box, state: str) -> str:
    """state: new | built | future."""
    fill, stroke, text, dash = {
        "new": (INK, INK, PAPER, ""),
        "built": (PAPER, INK, INK, ""),
        "future": ("none", GHOST, GHOST, ' stroke-dasharray="3 3"'),
    }[state]
    rx = BOX_H / 2 if n["type"] == "exposure" else 0                    # exposures: pills
    if n["type"] == "semantic_model" and state != "future":
        dash = ' stroke-dasharray="5 3"'                                   # semantic models: dashed
    out = [f'<g class="node {state}" data-id="{escape(n["id"])}">',
           f'<rect x="{b.x:.1f}" y="{b.y:.1f}" width="{b.w:.1f}" height="{BOX_H}" rx="{rx}" '
           f'fill="{fill}" stroke="{stroke}" stroke-width="1"{dash}/>']
    if n["type"] == "seed" and state != "future":                         # seeds: a small notch
        out.append(f'<rect x="{b.x:.1f}" y="{b.y:.1f}" width="4" height="{BOX_H}" fill="{stroke if state == "built" else PAPER}"/>')
    out.append(f'<text x="{b.x + PAD_X:.1f}" y="{b.y + BOX_H / 2 + 3.8:.1f}" font-family="{FONT_MONO}" '
               f'font-size="{LABEL_PX}" fill="{text}">{escape(n["name"])}</text></g>')
    return "".join(out)


def _edge_svg(a: Box, b: Box, strong: bool) -> str:
    x1, y1 = a.x + a.w, a.y + BOX_H / 2
    x2, y2 = b.x, b.y + BOX_H / 2
    dx = max((x2 - x1) * 0.5, 24)
    colour, width, opacity = (INK, 1.3, 1) if strong else (MUTED, 0.8, 0.55)
    return (f'<path d="M{x1:.1f},{y1:.1f} C{x1 + dx:.1f},{y1:.1f} {x2 - dx:.1f},{y2:.1f} {x2:.1f},{y2:.1f}" '
            f'fill="none" stroke="{colour}" stroke-width="{width}" stroke-opacity="{opacity}"/>')


def _lane_headers(nodes: dict, boxes: dict[str, Box]) -> list[str]:
    out = []
    for lane in LANES:
        members = [boxes[k] for k, n in nodes.items() if lane_of(n) == lane]
        if not members:
            continue
        x0, x1 = min(b.x for b in members), max(b.x + b.w for b in members)
        out.append(f'<text x="{x0:.1f}" y="{MARGIN + 12}" font-family="{FONT_SANS}" font-size="10" '
                   f'font-weight="700" letter-spacing="1.8" fill="{INK}">{escape(LANE_TITLES[lane].upper())}</text>')
        out.append(f'<line x1="{x0:.1f}" y1="{MARGIN + 22}" x2="{x1:.1f}" y2="{MARGIN + 22}" stroke="{INK}" stroke-width="1"/>')
    q = [b for b in boxes.values() if b.band == "quality"]
    if q:
        top = min(b.y for b in q) - 30
        out.append(f'<text x="{MARGIN}" y="{top + 12:.1f}" font-family="{FONT_SANS}" font-size="10" font-weight="700" '
                   f'letter-spacing="1.8" fill="{INK}">QUALITY LANE — READS THE PIPELINE, NEVER FEEDS IT</text>')
        out.append(f'<line x1="{MARGIN}" y1="{top + 22:.1f}" x2="{max(b.x + b.w for b in boxes.values()):.1f}" '
                   f'y2="{top + 22:.1f}" stroke="{INK}" stroke-width="1" stroke-dasharray="2 4"/>')
    return out


def _legend(x: float, y: float, items: list[tuple[str, str]]) -> list[str]:
    out = []
    for state, label in items:
        fill, stroke, dash = {"new": (INK, INK, ""), "built": (PAPER, INK, ""),
                              "future": ("none", GHOST, ' stroke-dasharray="3 3"')}[state]
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="22" height="12" fill="{fill}" stroke="{stroke}"{dash}/>')
        out.append(f'<text x="{x + 30:.1f}" y="{y + 10:.1f}" font-family="{FONT_SANS}" font-size="11" '
                   f'fill="{INK}">{escape(label)}</text>')
        x += 40 + len(label) * 6.2
    return out


def render(union_graph: dict, boxes: dict[str, Box], phase_graph: dict | None = None,
           previous: dict | None = None, background: bool = True, title: str = "") -> str:
    nodes = union_graph["nodes"]
    width = max(b.x + b.w for b in boxes.values()) + MARGIN
    height = max(b.y for b in boxes.values()) + BOX_H + LEGEND_H + MARGIN

    full = phase_graph is None or phase_graph is previous      # the full picture: everything built
    if phase_graph is None:
        present = set(nodes)
        added: set[str] = set()
        edges = union_graph["edges"]
    else:
        present = {n["id"] for n in phase_graph["nodes"]} & set(nodes)
        before = {n["id"] for n in previous["nodes"]} if previous else set()
        added = present - before
        edges = [tuple(e) for e in phase_graph["edges"] if e[0] in nodes and e[1] in nodes]

    def state(k: str) -> str:
        return "new" if k in added else "built" if k in present else "future"

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
             f'width="{width:.0f}" height="{height:.0f}" role="img" aria-label="{escape(title or "dbt lineage")}">']
    if title:
        parts.append(f"<title>{escape(title)}</title>")
    if background:
        parts.append(f'<rect width="100%" height="100%" fill="{BG}"/>')
    parts += _lane_headers(nodes, boxes)
    parts.append('<g class="edges">')
    parts += [_edge_svg(boxes[a], boxes[b], strong=(a in added or b in added)) for a, b in edges]
    parts.append('</g><g class="nodes">')
    parts += [_node_svg(n, boxes[k], state(k)) for k, n in sorted(nodes.items())]
    parts.append("</g>")

    legend_y = height - MARGIN - 14
    if full:
        counts = {t: sum(1 for k in present if nodes[k]["type"] == t) for t in
                  ("source", "seed", "model", "semantic_model", "exposure")}
        caption = (f'{counts["model"]} models · {counts["source"]} sources · {counts["seed"]} seeds · '
                   f'{counts["semantic_model"]} semantic models · {counts["exposure"]} exposures · '
                   f'{len(edges)} dependencies')
        parts.append(f'<text x="{MARGIN}" y="{legend_y + 10:.1f}" font-family="{FONT_SANS}" font-size="11" '
                     f'fill="{INK}">{escape(caption)}</text>')
    else:
        parts += _legend(MARGIN, legend_y, [("new", f"added in this phase ({len(added)})"),
                                            ("built", f"built earlier ({len(present - added)})"),
                                            ("future", "still to come")])
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


# ------------------------------------------------------------------------------------------- CLI

def main() -> None:
    config = yaml.safe_load((ROOT / "tools/lineage/phases.yml").read_text())
    graph_dir = ROOT / config["graphs_dir"]
    out_dir = ROOT / config["output_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    phases = config["phases"]
    graphs = [json.loads((graph_dir / f"{p['id']}.json").read_text()) for p in phases]
    current_path = graph_dir / "current.json"           # today's DAG (collect.py --current)
    current = json.loads(current_path.read_text()) if current_path.exists() else graphs[-1]
    u = union(graphs + [current])                       # one layout for every picture
    boxes = layout(u)
    (out_dir / "lineage_full.svg").write_text(
        render(u, boxes, current, previous=current, title="dbt lineage of the Balenciaga pricing pipeline"))
    previous = None
    for p, g in zip(phases, graphs):
        (out_dir / f"lineage_{p['id']}.svg").write_text(
            render(u, boxes, g, previous, title=f"Lineage after {p['label']}: {p['title']}"))
        previous = g
    print(f"{len(phases) + 1} pictures -> {out_dir.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
