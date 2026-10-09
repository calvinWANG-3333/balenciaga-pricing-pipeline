"""Serve the assembled site locally the way GitHub Pages does.

    python -m tools.site.preview                 # http://127.0.0.1:8000  (run tools.site.assemble first)

GitHub Pages answers /phase-4 with phase-4.html and /bi/ with bi/index.html. Python's plain http.server does
not do the first, so the site's clean links would 404 locally. Local preview only, never used in CI.
"""

from __future__ import annotations

import argparse
import functools
import http.server
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class PagesHandler(http.server.SimpleHTTPRequestHandler):
    def send_head(self):
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        local = Path(self.directory) / path.lstrip("/")
        if not local.exists() and local.with_name(local.name + ".html").exists():
            self.path = path + ".html"
        return super().send_head()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preview the assembled site with clean URLs.")
    parser.add_argument("--dir", default="_site")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    root = ROOT / args.dir
    if not (root / "index.html").exists():
        raise SystemExit(f"{root}/index.html not found: run `python -m tools.site.assemble` first.")
    handler = functools.partial(PagesHandler, directory=str(root))
    print(f"Serving {root} on http://127.0.0.1:{args.port}  (Ctrl+C to stop)")
    http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
