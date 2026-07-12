#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import webbrowser
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterable

HOME = Path.home()
ROOT = Path(__file__).resolve().parent
SKILL_PATH_RE = re.compile(r"(?:^|[/\\])skills[/\\](.+?)[/\\]SKILL\.md", re.I)

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = not IS_WINDOWS and not IS_MACOS

APPDATA = Path(os.environ.get("APPDATA", HOME / "AppData/Roaming"))
LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA", HOME / "AppData/Local"))
XDG_CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config"))
XDG_DATA_HOME = Path(os.environ.get("XDG_DATA_HOME", HOME / ".local/share"))


@dataclass
class Stat:
    agent: str
    skill: str
    uses: int = 0
    sessions: int = 0
    views: int = 0
    patches: int = 0
    last_used: str | None = None
    confidence: str = "exact"
    skill_path: str | None = None
    skill_id: str | None = None


def iso_from_timestamp(value: float | int | None, millis: bool = False) -> str | None:
    if not value:
        return None
    try:
        ts = float(value) / (1000 if millis else 1)
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except (ValueError, TypeError, OSError):
        return None


SHARED_SKILL_ROOTS = [
    HOME / ".agents" / "skills",
]

AGENT_SKILL_ROOTS: dict[str, list[Path]] = {
    "Hermes": [
        HOME / ".hermes" / "skills",
    ],
    "OpenCode": [
        XDG_CONFIG_HOME / "opencode" / "skills",
        XDG_DATA_HOME / "opencode" / "skills",
        APPDATA / "opencode" / "skills",
        LOCALAPPDATA / "opencode" / "skills",
        HOME / ".claude" / "skills",
        *SHARED_SKILL_ROOTS,
    ],
    "Codex": [
        HOME / ".codex" / "skills",
        *SHARED_SKILL_ROOTS,
    ],
    "Claude Code": [
        HOME / ".claude" / "skills",
    ],
    "Pi": [
        HOME / ".pi" / "agent" / "skills",
        HOME / ".codex" / "skills",
        HOME / ".claude" / "skills",
        *SHARED_SKILL_ROOTS,
    ],
    "Continue": [
        HOME / ".continue" / "skills",
    ],
    "Cline": [
        HOME / ".cline" / "skills",
    ],
    "Cursor": [
        HOME / ".cursor" / "skills",
    ],
    "Roo Code": [
        HOME / ".roo" / "skills",
        *SHARED_SKILL_ROOTS,
    ],
    "Windsurf": [
        HOME / ".windsurf" / "skills",
        HOME / ".codeium" / "windsurf" / "skills",
    ],
}

AGENT_DATA_ROOTS: dict[str, list[Path]] = {
    "Hermes": [
        HOME / ".hermes",
    ],
    "OpenCode": [
        XDG_DATA_HOME / "opencode",
        LOCALAPPDATA / "opencode",
        APPDATA / "opencode",
    ],
    "Codex": [
        HOME / ".codex",
    ],
    "Claude Code": [
        HOME / ".claude",
    ],
    "Pi": [
        HOME / ".pi",
    ],
    "Continue": [
        HOME / ".continue",
    ],
    "Cline": [
        HOME / ".cline",
    ],
    "Cursor": [
        HOME / ".cursor",
    ],
    "Roo Code": [
        HOME / ".roo",
    ],
    "Windsurf": [
        HOME / ".windsurf",
        HOME / ".codeium" / "windsurf",
    ],
}


def agent_is_installed(agent: str) -> bool:
    roots = AGENT_DATA_ROOTS.get(agent, [])
    skill_roots = AGENT_SKILL_ROOTS.get(agent, [])
    return any(path.exists() for path in [*roots, *skill_roots])


def find_first_existing(paths: Iterable[Path]) -> Path | None:
    return next((path for path in paths if path.exists()), None)


def open_folder(path: Path) -> None:
    if IS_WINDOWS:
        os.startfile(path)
        return
    if IS_MACOS:
        subprocess.Popen(["open", str(path)])
        return
    subprocess.Popen(["xdg-open", str(path)])


def is_inside_allowed_root(path: Path) -> bool:
    for roots in AGENT_SKILL_ROOTS.values():
        for root in roots:
            try:
                path.relative_to(root.resolve())
                return True
            except ValueError:
                continue
    return False


def resolve_skill_path(agent: str, name: str) -> str | None:
    for root in AGENT_SKILL_ROOTS.get(agent, []):
        folder = root / name
        if folder.is_dir():
            return str(folder.resolve())
    return None


def merge(stats: Iterable[Stat]) -> list[dict]:
    merged: dict[tuple[str, str], Stat] = {}
    for item in stats:
        key = (item.agent, item.skill)
        if key not in merged:
            merged[key] = item
            continue
        current = merged[key]
        current.uses += item.uses
        current.sessions += item.sessions
        current.views += item.views
        current.patches += item.patches
        if item.last_used and (not current.last_used or item.last_used > current.last_used):
            current.last_used = item.last_used
        if item.confidence != "exact":
            current.confidence = item.confidence
        if not current.skill_path and item.skill_path:
            current.skill_path = item.skill_path
    return [asdict(v) for v in merged.values()]


def collect_hermes() -> list[Stat]:
    path = HOME / ".hermes/skills/.usage.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except Exception:
        return []
    return [Stat("Hermes", name, int(v.get("use_count") or 0), 0,
                 int(v.get("view_count") or 0), int(v.get("patch_count") or 0),
                 v.get("last_used_at"), "exact", str((HOME / ".hermes/skills" / name).resolve())) for name, v in data.items()]


def collect_opencode() -> list[Stat]:
    db = find_first_existing([
        XDG_DATA_HOME / "opencode" / "opencode.db",
        LOCALAPPDATA / "opencode" / "opencode.db",
        APPDATA / "opencode" / "opencode.db",
    ])
    if db is None:
        return []
    counts: Counter[str] = Counter()
    sessions: dict[str, set[str]] = defaultdict(set)
    last: dict[str, int] = {}
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        rows = con.execute("SELECT session_id,time_created,data FROM part WHERE data LIKE '%\"tool\":\"skill\"%'")
        for sid, ts, raw in rows:
            try:
                obj = json.loads(raw)
                state = obj.get("state") or {}
                name = (state.get("input") or {}).get("name")
                if obj.get("tool") != "skill" or state.get("status") != "completed" or not name:
                    continue
            except Exception:
                continue
            counts[name] += 1
            sessions[name].add(sid)
            last[name] = max(last.get(name, 0), int(ts or 0))
        con.close()
    except sqlite3.Error:
        return []
    return [Stat("OpenCode", name, count, len(sessions[name]), last_used=iso_from_timestamp(last[name], True),
                 skill_path=resolve_skill_path("OpenCode", name))
            for name, count in counts.items()]


def scan_jsonl_paths(agent: str, files: Iterable[Path], valid_roots: list[Path] | None = None) -> list[Stat]:
    valid = set()
    for root in valid_roots or []:
        if root.exists():
            valid |= {str(p.parent.relative_to(root)) for p in root.rglob("SKILL.md")}
    counts: Counter[str] = Counter()
    sessions: dict[str, set[str]] = defaultdict(set)
    last: dict[str, float] = {}
    for file in files:
        sid = file.stem
        try:
            with file.open(errors="ignore") as handle:
                for line in handle:
                    if "SKILL.md" not in line or "skills" not in line.lower():
                        continue
                    for name in set(SKILL_PATH_RE.findall(line)):
                        name = name.replace("\\", "/")
                        if valid and name not in valid and not any(name.endswith("/" + v) for v in valid):
                            continue
                        counts[name] += 1
                        sessions[name].add(sid)
                        last[name] = max(last.get(name, 0), file.stat().st_mtime)
        except OSError:
            continue
    return [Stat(agent, name, count, len(sessions[name]), last_used=iso_from_timestamp(last[name]),
                 confidence="explicit read", skill_path=resolve_skill_path(agent, name))
            for name, count in counts.items()]


def collect_codex() -> list[Stat]:
    files = list((HOME / ".codex/sessions").rglob("*.jsonl")) + list((HOME / ".codex/archived_sessions").rglob("*.jsonl"))
    return scan_jsonl_paths("Codex", files, [HOME / ".codex/skills"])


def collect_claude() -> list[Stat]:
    files = list((HOME / ".claude/projects").rglob("*.jsonl")) + list((HOME / ".claude/sessions").rglob("*.jsonl"))
    return scan_jsonl_paths("Claude Code", files, [HOME / ".claude/skills"])


def collect_pi() -> list[Stat]:
    files = list((HOME / ".pi/agent/sessions").rglob("*.jsonl"))
    roots = [HOME / ".pi/agent/skills", HOME / ".codex/skills", HOME / ".claude/skills"]
    return scan_jsonl_paths("Pi", files, roots)


def collect_generic() -> list[Stat]:
    configs = [
        ("Continue", HOME / ".continue/sessions", HOME / ".continue/skills"),
        ("Cline", HOME / ".cline/data/sessions", HOME / ".cline/skills"),
        ("Cursor", HOME / ".cursor", HOME / ".cursor/skills"),
        ("Roo Code", HOME / ".roo", HOME / ".roo/skills"),
        ("Windsurf", HOME / ".windsurf", HOME / ".windsurf/skills"),
    ]
    out: list[Stat] = []
    for agent, sessions_root, skills_root in configs:
        files = list(sessions_root.rglob("*.jsonl")) + list(sessions_root.rglob("*.json")) if sessions_root.exists() else []
        out.extend(scan_jsonl_paths(agent, files, [skills_root]))
    return out


def build_payload() -> dict:
    collectors = [collect_hermes, collect_opencode, collect_codex, collect_claude, collect_pi, collect_generic]
    stats: list[Stat] = []
    for collector in collectors:
        try:
            stats.extend(collector())
        except Exception as exc:
            print(f"collector {collector.__name__} failed: {exc}")
    rows = merge(stats)
    for row in rows:
        row["skill_id"] = (
            os.path.normcase(row["skill_path"])
            if row["skill_path"]
            else row["skill"]
        )
    rows.sort(key=lambda r: (-r["uses"], r["skill"].lower(), r["agent"]))
    agents = sorted({r["agent"] for r in rows})
    installed = {
        agent: agent_is_installed(agent)
        for agent in AGENT_SKILL_ROOTS
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows": rows,
        "agents": agents,
        "installed": installed,
        "summary": {
            "uses": sum(r["uses"] for r in rows),
            "views": sum(r["views"] for r in rows),
            "skills": len({r["skill"] for r in rows}),
            "agents": len(agents),
        },
    }


def write_data() -> Path:
    path = ROOT / "data.json"
    path.write_text(json.dumps(build_payload(), ensure_ascii=False, indent=2))
    return path


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/refresh"):
            write_data()
            self.send_response(204)
            self.end_headers()
            return
        if self.path.startswith("/open-folder"):
            from urllib.parse import unquote, urlparse, parse_qs
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            folder = params.get("path", [None])[0]
            if folder:
                folder = unquote(folder)
                resolved = Path(folder).resolve()
                if is_inside_allowed_root(resolved) and resolved.is_dir():
                    open_folder(resolved)
            self.send_response(204)
            self.end_headers()
            return
        super().do_GET()

    def log_message(self, fmt: str, *args):
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Merged local skill usage dashboard")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    path = write_data()
    if args.json:
        print(path.read_text())
        return
    os.chdir(ROOT)
    port = args.port
    while True:
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            server.allow_reuse_address = True
            break
        except OSError:
            port += 1
    url = f"http://127.0.0.1:{port}"
    print(f"Useless Skills: {url}")
    print("Ctrl+C pour arrêter")
    if not args.no_open:
        threading.Timer(0.35, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
