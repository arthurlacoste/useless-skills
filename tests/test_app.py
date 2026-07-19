import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Stat, merge, iso_from_timestamp, is_inside_allowed_root, open_folder, agent_is_installed, find_first_existing, AGENT_SKILL_ROOTS, render_table, render_toon, _apply_query, _sort_rows

def test_merge_sums_same_agent_skill():
    rows = merge([Stat('A','x',2,1), Stat('A','x',3,2)])
    assert rows == [{'agent':'A','skill':'x','uses':5,'sessions':3,'views':0,'patches':0,'last_used':None,'confidence':'exact','skill_path':None,'skill_id':None}]

def test_merge_keeps_agents_separate():
    assert len(merge([Stat('A','x',1), Stat('B','x',1)])) == 2

def test_timestamp_millis():
    assert iso_from_timestamp(1000, True).startswith('1970-01-01T00:00:01')

def test_is_inside_allowed_root_with_valid_path(tmp_path):
    import app
    original = app.AGENT_SKILL_ROOTS
    base = tmp_path / ".claude" / "skills"
    base.mkdir(parents=True)
    app.AGENT_SKILL_ROOTS = {"Claude Code": [base]}
    try:
        fake = base / "review"
        fake.mkdir()
        assert is_inside_allowed_root(fake)
    finally:
        app.AGENT_SKILL_ROOTS = original

def test_is_inside_allowed_root_rejects_path_outside(tmp_path):
    outside = tmp_path / "evil" / "skills" / "review"
    outside.mkdir(parents=True)
    assert not is_inside_allowed_root(outside)

def test_is_inside_allowed_root_with_sibling(tmp_path):
    """A sibling directory starting with the same prefix is rejected."""
    base = tmp_path / ".claude" / "skills"
    base.mkdir(parents=True)
    sibling = tmp_path / ".claude" / "skills-evil"
    sibling.mkdir(parents=True)
    import app
    original = app.AGENT_SKILL_ROOTS
    app.AGENT_SKILL_ROOTS = {"Claude Code": [base]}
    try:
        child = base / "review"
        child.mkdir()
        assert is_inside_allowed_root(child)
        assert not is_inside_allowed_root(sibling)
    finally:
        app.AGENT_SKILL_ROOTS = original

def test_find_first_existing(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    b.write_text("hello")
    assert find_first_existing([a, b]) == b

def test_find_first_existing_none(tmp_path):
    a = tmp_path / "missing.txt"
    assert find_first_existing([a]) is None

def test_agent_is_installedchecks_data_and_skills(tmp_path):
    import app
    original_data = app.AGENT_DATA_ROOTS
    original_skills = app.AGENT_SKILL_ROOTS
    agent_dir = tmp_path / ".hermes"
    skill_dir = tmp_path / ".hermes" / "skills"
    skill_dir.mkdir(parents=True)
    app.AGENT_DATA_ROOTS = {"Hermes": [agent_dir]}
    app.AGENT_SKILL_ROOTS = {"Hermes": [skill_dir]}
    try:
        assert agent_is_installed("Hermes")
        app.AGENT_DATA_ROOTS = {}
        app.AGENT_SKILL_ROOTS = {}
        assert not agent_is_installed("Hermes")
    finally:
        app.AGENT_DATA_ROOTS = original_data
        app.AGENT_SKILL_ROOTS = original_skills


def test_dashboard_refreshes_on_open_and_every_30_seconds():
    html = (Path(__file__).resolve().parents[1] / "index.html").read_text()
    assert "const REFRESH_INTERVAL_MS=30000" in html
    assert "refreshNow();" in html
    assert "setInterval(reloadData,REFRESH_INTERVAL_MS)" in html
    assert "document.visibilityState==='visible'" in html
    assert "document.addEventListener('visibilitychange'" in html


def test_dashboard_refetches_without_http_cache_and_avoids_overlap():
    html = (Path(__file__).resolve().parents[1] / "index.html").read_text()
    assert "fetch('/refresh',{cache:'no-store'})" in html
    assert "fetch('data.json?'+Date.now(),{cache:'no-store'})" in html
    assert "if(refreshPromise)return refreshPromise" in html
    assert "last_used:null" in html


def test_apply_query_plain_text_searches_skill_and_agent(capsys):
    rows = [
        {"agent": "Codex", "skill": "seo", "uses": 1},
        {"agent": "OpenCode", "skill": "testing", "uses": 1},
    ]
    out = _apply_query(rows, "seo")
    assert len(out) == 1
    assert out[0]["skill"] == "seo"


def test_apply_query_agent_prefix(capsys):
    rows = [
        {"agent": "Codex", "skill": "x", "uses": 1},
        {"agent": "OpenCode", "skill": "y", "uses": 1},
    ]
    out = _apply_query(rows, "agent=OpenCode")
    assert len(out) == 1
    assert out[0]["agent"] == "OpenCode"


def test_apply_query_skill_prefix(capsys):
    rows = [
        {"agent": "Codex", "skill": "seo", "uses": 1},
        {"agent": "Codex", "skill": "testing", "uses": 1},
    ]
    out = _apply_query(rows, "skill=seo")
    assert len(out) == 1
    assert out[0]["skill"] == "seo"


def test_sort_rows_uses_descending(capsys):
    rows = [
        {"agent": "A", "skill": "x", "uses": 1, "sessions": 1},
        {"agent": "A", "skill": "y", "uses": 5, "sessions": 1},
        {"agent": "A", "skill": "z", "uses": 3, "sessions": 1},
    ]
    out = _sort_rows(rows, "uses")
    assert [r["skill"] for r in out] == ["y", "z", "x"]


def test_sort_rows_uses_ascending(capsys):
    rows = [
        {"agent": "A", "skill": "x", "uses": 1, "sessions": 1},
        {"agent": "A", "skill": "y", "uses": 5, "sessions": 1},
        {"agent": "A", "skill": "z", "uses": 3, "sessions": 1},
    ]
    out = _sort_rows(rows, "uses", reverse=False)
    assert [r["skill"] for r in out] == ["x", "z", "y"]


def test_sort_rows_sessions_descending(capsys):
    rows = [
        {"agent": "A", "skill": "x", "uses": 1, "sessions": 3},
        {"agent": "A", "skill": "y", "uses": 1, "sessions": 1},
        {"agent": "A", "skill": "z", "uses": 1, "sessions": 2},
    ]
    out = _sort_rows(rows, "sessions")
    assert [r["skill"] for r in out] == ["x", "z", "y"]


def test_sort_rows_sessions_ascending(capsys):
    rows = [
        {"agent": "A", "skill": "x", "uses": 1, "sessions": 3},
        {"agent": "A", "skill": "y", "uses": 1, "sessions": 1},
        {"agent": "A", "skill": "z", "uses": 1, "sessions": 2},
    ]
    out = _sort_rows(rows, "sessions", reverse=False)
    assert [r["skill"] for r in out] == ["y", "z", "x"]


def test_sort_rows_skill_ascending(capsys):
    rows = [
        {"agent": "A", "skill": "z", "uses": 1},
        {"agent": "A", "skill": "a", "uses": 1},
    ]
    out = _sort_rows(rows, "skill")
    assert [r["skill"] for r in out] == ["a", "z"]


def test_sort_rows_skill_descending(capsys):
    rows = [
        {"agent": "A", "skill": "z", "uses": 1},
        {"agent": "A", "skill": "a", "uses": 1},
    ]
    out = _sort_rows(rows, "skill", reverse=True)
    assert [r["skill"] for r in out] == ["z", "a"]


def test_sort_rows_agent_ascending(capsys):
    rows = [
        {"agent": "B", "skill": "y", "uses": 1},
        {"agent": "A", "skill": "x", "uses": 1},
    ]
    out = _sort_rows(rows, "agent")
    assert [r["agent"] for r in out] == ["A", "B"]


def test_sort_rows_last_used_descending(capsys):
    rows = [
        {"agent": "A", "skill": "old", "uses": 1, "last_used": "2026-01-01T00:00:00+00:00"},
        {"agent": "A", "skill": "new", "uses": 1, "last_used": "2026-07-01T00:00:00+00:00"},
    ]
    out = _sort_rows(rows, "last_used")
    assert [r["skill"] for r in out] == ["new", "old"]


def test_sort_rows_last_used_ascending(capsys):
    rows = [
        {"agent": "A", "skill": "old", "uses": 1, "last_used": "2026-01-01T00:00:00+00:00"},
        {"agent": "A", "skill": "new", "uses": 1, "last_used": "2026-07-01T00:00:00+00:00"},
    ]
    out = _sort_rows(rows, "last_used", reverse=False)
    assert [r["skill"] for r in out] == ["old", "new"]


def test_render_table_with_query(capsys):
    payload = {
        "rows": [
            {"agent": "Codex", "skill": "seo", "uses": 1, "sessions": 1, "views": 0, "patches": 0, "last_used": None, "confidence": "exact", "skill_path": None, "skill_id": None},
            {"agent": "OpenCode", "skill": "testing", "uses": 1, "sessions": 1, "views": 0, "patches": 0, "last_used": None, "confidence": "exact", "skill_path": None, "skill_id": None},
        ],
        "summary": {"uses": 2, "views": 0, "skills": 2, "agents": 2},
    }
    render_table(payload, query="seo", limit=10)
    out = capsys.readouterr().out
    assert "seo" in out
    assert "testing" not in out


def test_render_table_agent_prefix_query(capsys):
    payload = {
        "rows": [
            {"agent": "Codex", "skill": "x", "uses": 1, "sessions": 1, "views": 0, "patches": 0, "last_used": None, "confidence": "exact", "skill_path": None, "skill_id": None},
            {"agent": "OpenCode", "skill": "y", "uses": 2, "sessions": 2, "views": 0, "patches": 0, "last_used": None, "confidence": "exact", "skill_path": None, "skill_id": None},
        ],
        "summary": {"uses": 3, "views": 0, "skills": 2, "agents": 2},
    }
    render_table(payload, query="agent=OpenCode", limit=10)
    out = capsys.readouterr().out
    assert "OpenCode" in out
    assert "Codex" not in out


def test_render_table_sort(capsys):
    payload = {
        "rows": [
            {"agent": "A", "skill": "x", "uses": 1, "sessions": 1, "views": 0, "patches": 0, "last_used": None, "confidence": "exact", "skill_path": None, "skill_id": None},
            {"agent": "A", "skill": "y", "uses": 5, "sessions": 1, "views": 0, "patches": 0, "last_used": None, "confidence": "exact", "skill_path": None, "skill_id": None},
            {"agent": "A", "skill": "z", "uses": 3, "sessions": 1, "views": 0, "patches": 0, "last_used": None, "confidence": "exact", "skill_path": None, "skill_id": None},
        ],
        "summary": {"uses": 9, "views": 0, "skills": 3, "agents": 1},
    }
    render_table(payload, sort="uses", limit=10)
    out = capsys.readouterr().out
    lines = [l.strip() for l in out.splitlines() if l.strip() and not l.startswith("-") and not l.startswith("Skill")]
    data_lines = [l for l in lines if not l.startswith("Showing") and not l.startswith("Total") and not l.startswith("--")]
    assert data_lines[0].startswith("y")
    assert data_lines[1].startswith("z")
    assert data_lines[2].startswith("x")


def test_render_table_limit_offset(capsys):
    payload = {
        "rows": [
            {"agent": "A", "skill": "s1", "uses": 1, "sessions": 1, "views": 0, "patches": 0, "last_used": None, "confidence": "exact", "skill_path": None, "skill_id": None},
            {"agent": "A", "skill": "s2", "uses": 2, "sessions": 2, "views": 0, "patches": 0, "last_used": None, "confidence": "exact", "skill_path": None, "skill_id": None},
            {"agent": "A", "skill": "s3", "uses": 3, "sessions": 3, "views": 0, "patches": 0, "last_used": None, "confidence": "exact", "skill_path": None, "skill_id": None},
        ],
        "summary": {"uses": 6, "views": 0, "skills": 3, "agents": 1},
    }
    render_table(payload, limit=2, offset=1)
    out = capsys.readouterr().out
    assert "s2" in out
    assert "s1" in out
    assert "s3" not in out
    assert "Showing 2-3 of 3" in out


def test_render_toon_default_limit_100(capsys):
    payload = {
        "rows": [{"agent": "A", "skill": f"s{i}", "uses": i, "sessions": i, "views": 0, "patches": 0, "last_used": None, "confidence": "exact", "skill_path": None, "skill_id": None} for i in range(150)],
        "summary": {"uses": 0, "views": 0, "skills": 150, "agents": 1},
    }
    render_toon(payload)
    out = capsys.readouterr().out
    assert "skills{100}:" in out
    assert "skills{150}:" not in out


def test_render_toon_filters_and_limit(capsys):
    payload = {
        "rows": [
            {"agent": "A", "skill": "x", "uses": 1, "sessions": 1, "views": 0, "patches": 0, "last_used": None, "confidence": "exact", "skill_path": None, "skill_id": None},
            {"agent": "B", "skill": "y", "uses": 2, "sessions": 2, "views": 0, "patches": 0, "last_used": None, "confidence": "exact", "skill_path": None, "skill_id": None},
        ],
        "summary": {"uses": 3, "views": 0, "skills": 2, "agents": 2},
    }
    render_toon(payload, limit=1, agent="B")
    out = capsys.readouterr().out
    assert "skills{1}:" in out
    assert "B" in out
    assert "A" not in out
