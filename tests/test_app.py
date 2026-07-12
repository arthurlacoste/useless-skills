import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Stat, merge, iso_from_timestamp, is_inside_allowed_root, open_folder, agent_is_installed, find_first_existing, AGENT_SKILL_ROOTS

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
