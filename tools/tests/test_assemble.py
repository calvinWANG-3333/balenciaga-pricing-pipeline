"""tools/site/assemble.py: three builds into one Pages folder."""

from pathlib import Path

import pytest

from tools.site.assemble import assemble


def build(root: Path, name: str, page: str = "index.html") -> Path:
    d = root / name / "dist"
    (d / "_observablehq").mkdir(parents=True)
    (d / page).write_text(f"<h1>{name}</h1>")
    (d / "_observablehq" / "client.js").write_text("//")
    return d


def test_layout_with_production_docs(tmp_path):
    target = tmp_path / "dbt" / "target"
    target.mkdir(parents=True)
    (target / "static_index.html").write_text("<html>docs</html>")
    result = assemble(build(tmp_path, "site"), build(tmp_path, "bi"), target, tmp_path / "_site")
    out = tmp_path / "_site"
    assert (out / "index.html").read_text() == "<h1>site</h1>"
    assert (out / "bi" / "index.html").read_text() == "<h1>bi</h1>"
    assert (out / "dbt-docs" / "index.html").read_text() == "<html>docs</html>"
    assert (out / ".nojekyll").exists()
    assert (out / "_observablehq" / "client.js").exists()
    assert result["dbt_docs"] == "production"


def test_placeholder_without_production_docs(tmp_path):
    result = assemble(build(tmp_path, "site"), build(tmp_path, "bi"), tmp_path / "nothing", tmp_path / "_site")
    assert result["dbt_docs"] == "placeholder"
    assert "production deploy" in (tmp_path / "_site" / "dbt-docs" / "index.html").read_text()


def test_stale_output_is_replaced(tmp_path):
    out = tmp_path / "_site"
    (out / "old").mkdir(parents=True)
    (out / "old" / "page.html").write_text("stale")
    assemble(build(tmp_path, "site"), build(tmp_path, "bi"), tmp_path / "nothing", out)
    assert not (out / "old").exists()


def test_missing_build_is_an_error(tmp_path):
    with pytest.raises(SystemExit, match="build it first"):
        assemble(tmp_path / "site" / "dist", build(tmp_path, "bi"), tmp_path / "nothing", tmp_path / "_site")
