"""Tests for ats-check: fixtures vs expected findings, degradation, package,
frontmatter, documentation sync.

Run: pip install -r requirements-dev.txt && pytest -q
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(ROOT, "skills", "ats-check")
SCRIPTS = os.path.join(SKILL, "scripts")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import analyze  # noqa: E402
import extractors as ex  # noqa: E402

with open(os.path.join(ROOT, "tests", "expected.json"), encoding="utf-8") as _fh:
    EXPECTED = json.load(_fh)["fixtures"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def fixture_pdfs(tmp_path_factory):
    import make_fixtures
    return make_fixtures.build(str(tmp_path_factory.mktemp("fixtures")))


@pytest.fixture(scope="session")
def results(fixture_pdfs):
    return {name: analyze.analyze(path) for name, path in fixture_pdfs.items()}


def test_all_extractors_available_for_expectations():
    """expected.json was measured with all five extractors; say so if not."""
    missing = [n for n, s in ex.probe().items() if s["status"] != "available"]
    assert not missing, f"expected.json assumes all extractors; unavailable: {missing}"


def test_every_fixture_has_expectations(fixture_pdfs):
    assert set(fixture_pdfs) == set(EXPECTED)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_fixture_findings(name, results):
    exp = EXPECTED[name]
    got = {f["id"] for f in results[name]["findings"]}
    must = set(exp["must"])
    allowed = set(exp.get("allowed", {}))
    must_not = set(analyze.FINDING_CATALOGUE) - must - allowed
    assert must <= got, f"missing (false negatives): {sorted(must - got)}"
    assert not (got & must_not), f"unexpected (false positives): {sorted(got & must_not)}"
    for sev in exp.get("forbid_severity", []):
        assert not [f for f in results[name]["findings"] if f["severity"] == sev]


@pytest.mark.parametrize("name", sorted(n for n in EXPECTED if "columns" in EXPECTED[n]))
def test_fixture_columns(name, results):
    pages = [c["page"] for c in results[name]["layout"]["columns"]]
    assert pages == EXPECTED[name]["columns"]


@pytest.mark.parametrize("name", sorted(n for n in EXPECTED if "clean_extractors" in EXPECTED[n]))
def test_fixture_clean_extractors(name, results):
    finding = next(f for f in results[name]["findings"] if f["id"] == "reading_order_mixed")
    for extractor in EXPECTED[name]["clean_extractors"]:
        assert extractor not in finding["evidence"]


def test_mixing_reported_only_when_measured(results):
    """reading_order_mixed appears exactly when an extractor's output mixes."""
    for name, res in results.items():
        measured = [c for c in res["layout"]["columns"]
                    if any(analyze._mixes(r) for r in c["mixing"].values())]
        reported = [f for f in res["findings"] if f["id"] == "reading_order_mixed"]
        assert bool(measured) == bool(reported), name
        for f in reported:
            for extractor, r in f["evidence"].items():
                assert analyze._mixes(r), (name, extractor)


def test_columns_without_mixing_give_no_finding():
    """Two detected columns, extracted column by column: no mixing."""
    Frag = ex.Fragment
    frags = []
    for row in range(8):
        frags.append(Frag(1, 40, 120, 100 + 16 * row, 10, f"Sidebar{row} Kenntnis{row}"))
        frags.append(Frag(1, 200, 500, 100 + 16 * row, 10, f"Hauptspalte{row} Erfahrung{row}"))
    layout = ex.PageLayout(1, 595, 842, frags)
    cols = analyze.detect_columns(layout, [])
    assert cols and cols["count"] == 2
    columnwise = "\n".join([f"Sidebar{r} Kenntnis{r}" for r in range(8)]
                           + [f"Hauptspalte{r} Erfahrung{r}" for r in range(8)])
    rowwise = "\n".join(f"Sidebar{r} Kenntnis{r} Hauptspalte{r} Erfahrung{r}" for r in range(8))
    alternating = "\n".join(f"Sidebar{r} Kenntnis{r}\nHauptspalte{r} Erfahrung{r}" for r in range(8))
    assert not analyze._mixes(analyze.measure_mixing(frags, cols, columnwise))
    assert analyze.measure_mixing(frags, cols, rowwise)["mixed_lines"] == 8
    assert analyze._mixes(analyze.measure_mixing(frags, cols, alternating))


def test_finding_schema(results):
    for name, res in results.items():
        for f in res["findings"]:
            assert set(f) >= {"id", "group", "severity", "evidence_type", "message",
                              "location", "source_id"}, name
            assert f["severity"] in ("P0", "P1", "P2")
            assert f["evidence_type"] in ("measured", "documented", "heuristic")
            assert analyze.FINDING_CATALOGUE[f["id"]] == (f["group"], f["evidence_type"])
            assert set(f["location"]) == {"page", "area"}
            if f["evidence_type"] == "documented":
                assert f["source_id"] in analyze.SOURCES
            if f["evidence_type"] == "heuristic":
                assert f.get("rationale")


def test_json_top_level(results):
    res = results["01_clean_de"]
    for key in ("schema_version", "file", "extractors", "primary_extractor", "preview",
                "layout", "findings", "summary", "skipped_checks", "sources", "text"):
        assert key in res
    assert len(res["preview"]["lines"]) <= analyze.PREVIEW_LINES
    assert "Mustermann" in "\n".join(res["preview"]["lines"])
    assert "Überlingen" in res["text"]["full"]  # umlauts survive extraction


def test_deterministic(fixture_pdfs):
    a = analyze.analyze(fixture_pdfs["02_two_column"])
    b = analyze.analyze(fixture_pdfs["02_two_column"])
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_relevance(fixture_pdfs, tmp_path):
    job = tmp_path / "job.txt"
    job.write_text("Wir suchen: Python, Kubernetes und Kotlin. Erfahrung mit AWS.", encoding="utf-8")
    out = tmp_path / "out.json"
    assert analyze.main([fixture_pdfs["01_clean_de"], "--job", str(job), "--out", str(out)]) == 0
    rel = json.loads(out.read_text(encoding="utf-8"))["relevance"]
    terms = {t["term"]: t for t in rel["terms"]}
    assert terms["Python"]["in_cv"] and terms["Kubernetes"]["in_cv"] and terms["AWS"]["in_cv"]
    assert not terms["Kotlin"]["in_cv"]
    assert "Erfahrung" not in terms  # stopword list


@pytest.mark.parametrize("text,expected", [
    ("Tel. +49 170 1234567", ["+49 170 1234567"]),
    ("0221 1234567", ["0221 1234567"]),
    ("(030) 123 456 78", ["(030) 123 456 78"]),
    ("01.2019 - 12.2020 Controllerin", []),
    ("03/2020 – 02/2021", []),
    ("2015 - 2019", []),
    ("PLZ 10115", []),
])
def test_phone_detection(text, expected):
    assert analyze._phones(text) == expected


# ---------------------------------------------------------------------------
# Degradation
# ---------------------------------------------------------------------------

OTHERS = ("pdfplumber", "pdfminer", "pdfminer.high_level", "fitz", "pymupdf")


def _remove_modules(monkeypatch, names):
    for mod in names:
        monkeypatch.setitem(sys.modules, mod, None)  # import now raises ImportError
    monkeypatch.setattr(ex.shutil, "which", lambda _name: None)


def test_degradation_only_pypdf(monkeypatch, fixture_pdfs):
    _remove_modules(monkeypatch, OTHERS)
    res = analyze.analyze(fixture_pdfs["01_clean_de"])
    assert res["extractors"]["pypdf"]["status"] == "ok"
    for name in ("pdftotext", "pdfminer", "pymupdf", "pdfplumber"):
        assert res["extractors"][name]["status"] == "unavailable"
        assert res["extractors"][name]["reason"]
    assert res["primary_extractor"] == "pypdf"
    assert res["layout"]["coordinate_source"] == "pypdf"
    assert not [f for f in res["findings"] if f["severity"] == "P0"]
    # The two-column fixture still gets column detection from pypdf coordinates.
    res2 = analyze.analyze(fixture_pdfs["02_two_column"])
    assert [c["page"] for c in res2["layout"]["columns"]] == [1]
    assert "reading_order_mixed" in {f["id"] for f in res2["findings"]}


def test_degradation_cli_only_pypdf(monkeypatch, fixture_pdfs, tmp_path, capsys):
    _remove_modules(monkeypatch, OTHERS)
    assert analyze.main([fixture_pdfs["06_image_only"]]) == 0
    res = json.loads(capsys.readouterr().out)
    assert "text_is_image" in {f["id"] for f in res["findings"]}


def test_degradation_without_pypdf(monkeypatch, fixture_pdfs):
    _remove_modules(monkeypatch, ("pypdf",))
    res = analyze.analyze(fixture_pdfs["01_clean_de"])
    assert res["extractors"]["pypdf"]["status"] == "unavailable"
    assert res["skipped_checks"], "checks that need pypdf must be listed as skipped"
    assert res["primary_extractor"] in ("pdfminer", "pymupdf", "pdfplumber")


def test_degradation_nothing_available(monkeypatch, fixture_pdfs):
    _remove_modules(monkeypatch, OTHERS + ("pypdf",))
    res = analyze.analyze(fixture_pdfs["01_clean_de"])
    assert all(s["status"] == "unavailable" for s in res["extractors"].values())
    assert [f["id"] for f in res["findings"]] == ["no_extractor"]


# ---------------------------------------------------------------------------
# Package
# ---------------------------------------------------------------------------

DIST = os.path.join(ROOT, "dist", "ats-check.zip")


def test_zip_matches_source(tmp_path):
    import build_dist
    expected = {arc: open(src, "rb").read() for arc, src in build_dist.skill_files()}
    with zipfile.ZipFile(DIST) as zf:
        got = {name: zf.read(name) for name in zf.namelist()}
    assert set(got) == set(expected), "dist/ats-check.zip is stale: run tools/build_dist.py"
    for name in expected:
        assert got[name] == expected[name], f"{name} differs: run tools/build_dist.py"
    assert all(n.startswith("ats-check/") for n in got)
    assert "ats-check/SKILL.md" in got


def test_zip_runs_in_empty_dir(tmp_path, fixture_pdfs):
    with zipfile.ZipFile(DIST) as zf:
        zf.extractall(tmp_path)
    proc = subprocess.run([sys.executable, os.path.join("ats-check", "scripts", "analyze.py"),
                           fixture_pdfs["01_clean_de"]], cwd=tmp_path, capture_output=True,
                          text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr
    res = json.loads(proc.stdout)
    assert res["findings"] == []


# ---------------------------------------------------------------------------
# SKILL.md, docs, evals
# ---------------------------------------------------------------------------

def _frontmatter():
    text = open(os.path.join(SKILL, "SKILL.md"), encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    assert m, "SKILL.md must start with a YAML frontmatter block"
    fields = {}
    for line in m.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields, m.group(2)


def test_frontmatter():
    fields, body = _frontmatter()
    name, desc = fields["name"], fields["description"]
    # platform.claude.com Agent Skills overview: max 64 chars, lowercase letters,
    # numbers and hyphens, no XML tags, no reserved words "anthropic", "claude".
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name) and len(name) <= 64
    assert "claude" not in name and "anthropic" not in name
    assert name == os.path.basename(SKILL)  # agentskills.io spec: matches folder name
    # description: non-empty, max 1024 chars, no XML tags.
    assert 0 < len(desc) <= 1024
    assert not re.search(r"<[^>]+>", desc)
    # Best practices: SKILL.md body under 500 lines.
    assert len(body.splitlines()) < 500
    try:
        import yaml
    except ImportError:
        return
    text = open(os.path.join(SKILL, "SKILL.md"), encoding="utf-8").read()
    meta = yaml.safe_load(text.split("---")[1])
    assert meta["name"] == name and meta["description"] == desc


def test_checks_md_lists_every_finding():
    doc = open(os.path.join(SKILL, "references", "checks.md"), encoding="utf-8").read()
    for fid in analyze.FINDING_CATALOGUE:
        assert f"`{fid}`" in doc, fid


def test_sources_md_matches_script():
    doc = open(os.path.join(SKILL, "references", "sources.md"), encoding="utf-8").read()
    for sid, src in analyze.SOURCES.items():
        assert f"`{sid}`" in doc and src["url"] in doc, sid


def test_triggers_eval_file():
    data = json.load(open(os.path.join(ROOT, "evals", "triggers.json"), encoding="utf-8"))
    cases = data["cases"]
    assert sum(c["should_trigger"] for c in cases) >= 10
    assert sum(not c["should_trigger"] for c in cases) >= 10
    positives = [c["query"] for c in cases if c["should_trigger"]]
    assert any("ats" not in q.lower() for q in positives)


def test_marketplace_json():
    data = json.load(open(os.path.join(ROOT, ".claude-plugin", "marketplace.json"), encoding="utf-8"))
    assert data["name"] and data["owner"]["name"] and data["plugins"]
    for plugin in data["plugins"]:
        assert plugin["name"] and plugin["source"].startswith("./")
        for skill in plugin.get("skills", []):
            assert os.path.isfile(os.path.join(ROOT, skill, "SKILL.md"))


def test_no_network_imports():
    banned = {"socket", "urllib", "http", "requests", "httpx", "ftplib", "smtplib"}
    for fname in ("analyze.py", "extractors.py"):
        tree = ast.parse(open(os.path.join(SCRIPTS, fname), encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for n in names:
                assert n.split(".")[0] not in banned, (fname, n)


def test_numeric_constants_are_commented():
    """Every module-level UPPER_CASE constant holding a number has a comment."""
    for fname in ("analyze.py", "extractors.py"):
        src = open(os.path.join(SCRIPTS, fname), encoding="utf-8").read()
        lines = src.splitlines()
        tree = ast.parse(src)
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            names += [e.id for t in node.targets if isinstance(t, ast.Tuple)
                      for e in t.elts if isinstance(e, ast.Name)]
            if not names or not all(n.isupper() for n in names):
                continue
            if not any(isinstance(n, ast.Constant) and isinstance(n.value, (int, float))
                       and not isinstance(n.value, bool) for n in ast.walk(node.value)):
                continue
            row = node.lineno - 1
            if "#" in lines[row]:
                continue
            k = row - 1
            while k >= 0 and re.match(r"^[A-Z_][A-Z0-9_, ]* = ", lines[k]):
                k -= 1  # a comment may cover a group of consecutive constants
            assert k >= 0 and lines[k].lstrip().startswith("#"), f"{fname}:{node.lineno} {names}"
