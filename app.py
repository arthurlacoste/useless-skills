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


def _read_key(prompt: str) -> str:
    if IS_WINDOWS:
        import msvcrt
        sys.stdout.write(prompt)
        sys.stdout.flush()
        while True:
            if msvcrt.kbhit():
                ch = msvcrt.getwch()
                if ch == "\x03":
                    raise KeyboardInterrupt
                if ch in ("\r", "\n"):
                    return ""
                if ch == "\x08":
                    return ch
                sys.stdout.write(ch)
                sys.stdout.flush()
                return ch
    else:
        import tty
        fd = sys.stdin.fileno()
        old = tty.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            sys.stdout.write(prompt)
            sys.stdout.flush()
            ch = sys.stdin.read(1)
            if ch == "\x03":
                raise KeyboardInterrupt
            return ch
        finally:
            tty.tcsetattr(fd, tty.TCSAFLUSH, old)

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


def _truncate(text: str, length: int) -> str:
    return text if len(text) <= length else text[: length - 1] + "…"


def _format_last_used(value: str | None) -> str:
    if not value:
        return ""
    try:
        return value.split("T")[0]
    except Exception:
        return value or ""


def _apply_query(rows, query):
    if not query:
        return rows
    query = query.strip()
    if query.startswith("agent="):
        agent = query[6:].strip()
        return [r for r in rows if r.get("agent") == agent]
    if query.startswith("skill="):
        term = query[6:].strip().lower()
        return [r for r in rows if term in r.get("skill", "").lower()]
    term = query.lower()
    return [r for r in rows if term in r.get("skill", "").lower() or term in r.get("agent", "").lower()]


_SORT_DEFAULTS = {
    "uses": True,
    "sessions": True,
    "skill": False,
    "agent": False,
    "last_used": True,
}


def _sort_rows(rows, sort, reverse=None):
    if reverse is None:
        reverse = _SORT_DEFAULTS.get(sort, True)
    if sort == "sessions":
        return sorted(rows, key=lambda r: (r.get("sessions", 0), r.get("skill", "").lower()), reverse=reverse)
    if sort == "skill":
        return sorted(rows, key=lambda r: r.get("skill", "").lower(), reverse=reverse)
    if sort == "agent":
        return sorted(rows, key=lambda r: (r.get("agent", ""), r.get("skill", "").lower()), reverse=reverse)
    if sort == "last_used":
        return sorted(rows, key=lambda r: (r.get("last_used") or "", r.get("skill", "").lower()), reverse=reverse)
    return sorted(rows, key=lambda r: (r.get("uses", 0), r.get("skill", "").lower()), reverse=reverse)


def _render_page(rows, start, end, total, query, sort, actual_limit, interactive=False):
    page = rows[start:end]
    if not page:
        print("No data")
        return None
    headers = ("Skill", "Agent", "Uses", "Sessions", "Last Used")
    widths = [len(h) for h in headers]
    display = []
    for r in page:
        cells = (
            _truncate(r.get("skill", ""), 40),
            _truncate(r.get("agent", ""), 14),
            str(r.get("uses", 0)),
            str(r.get("sessions", 0)),
            _format_last_used(r.get("last_used")),
        )
        widths = [max(w, len(c)) for w, c in zip(widths, cells)]
        display.append(cells)
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    sep = "  ".join("-" * w for w in widths)
    print(fmt.format(*headers))
    print(sep)
    for cells in display:
        print(fmt.format(*cells))
    shown_start = start + 1
    shown_end = start + len(page)
    print()
    filter_str = query if query else "no filter"
    print(f"Showing {shown_start}-{shown_end} of {total} ({filter_str})")
    hints = []
    if interactive:
        if end < total:
            hints.append(f"n=next")
        if start > 0:
            hints.append(f"p=prev")
        hints.append(f"f=filter 1=uses 2=sessions 3=skill 4=agent 5=last_used c=clear o=web q=quit")
    else:
        if end < total:
            hints.append(f"--offset {end} --limit {actual_limit} for next")
        if start > 0:
            hints.append(f"--offset {max(0, start - actual_limit)} for prev")
        if not query:
            hints.append("--search text or agent=Name to filter")
        hints.append("--open for dashboard")
    print(" | ".join(hints))
    return page


def render_table(payload: dict, limit: int | None = None, offset: int = 0, query: str | None = None, sort: str = "uses", reverse: bool | None = None, interactive: bool = False) -> None:
    rows = payload.get("rows", [])
    if not interactive:
        rows = _apply_query(rows, query)
        rows = _sort_rows(rows, sort, reverse)
        total = len(rows)
        start = max(0, offset)
        actual_limit = limit
        if actual_limit is None:
            try:
                term_lines = os.get_terminal_size().lines
                actual_limit = max(1, term_lines - 7)
            except OSError:
                actual_limit = total
        if actual_limit <= 0:
            end = total
        else:
            end = min(start + actual_limit, total)
        _render_page(rows, start, end, total, query, sort, actual_limit, interactive=False)
        s = payload.get("summary", {})
        print(f"Total: {s.get('uses', 0)} uses, {s.get('views', 0)} views, {s.get('skills', 0)} skills, {s.get('agents', 0)} agents")
        return
    cur_query = query
    cur_sort = sort
    cur_reverse = _SORT_DEFAULTS.get(sort, True)
    actual_limit = limit
    if actual_limit is None:
        try:
            term_lines = os.get_terminal_size().lines
            actual_limit = max(1, term_lines - 7)
        except OSError:
            actual_limit = len(rows)
    cur_start = max(0, offset)
    cur_end = min(cur_start + actual_limit, len(rows)) if actual_limit > 0 else len(rows)
    while True:
        filtered = _apply_query(rows, cur_query)
        sorted_rows = _sort_rows(filtered, cur_sort, cur_reverse)
        total = len(sorted_rows)
        cur_start = min(cur_start, total)
        cur_end = min(cur_end, total)
        print("\033[H\033[J", end="")
        page = _render_page(sorted_rows, cur_start, cur_end, total, cur_query, cur_sort, actual_limit, interactive=True)
        if page is None:
            break
        s = payload.get("summary", {})
        direction = "DESC" if cur_reverse else "ASC"
        print(f"Total: {s.get('uses', 0)} uses, {s.get('views', 0)} views, {s.get('skills', 0)} skills, {s.get('agents', 0)} agents | sort={cur_sort} {direction}")
        try:
            cmd = _read_key("n/p/f/1/2/3/4/5/c/o/q> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break
        if cmd == "q":
            break
        if cmd == "n":
            if cur_end < total:
                cur_start = cur_end
                cur_end = min(cur_start + actual_limit, total)
        elif cmd == "p":
            if cur_start > 0:
                cur_end = cur_start
                cur_start = max(0, cur_end - actual_limit)
        elif cmd == "f":
            try:
                val = input("Filter (agent=X, skill=Y, or text): ").strip()
            except (EOFError, KeyboardInterrupt):
                val = ""
            if val:
                cur_query = val
            else:
                cur_query = None
            cur_start = 0
            cur_end = min(actual_limit, total) if actual_limit > 0 else total
        elif cmd == "1":
            if cur_sort == "uses":
                cur_reverse = not cur_reverse
            else:
                cur_sort = "uses"
                cur_reverse = _SORT_DEFAULTS["uses"]
            cur_start = 0
            cur_end = min(actual_limit, total) if actual_limit > 0 else total
        elif cmd == "2":
            if cur_sort == "sessions":
                cur_reverse = not cur_reverse
            else:
                cur_sort = "sessions"
                cur_reverse = _SORT_DEFAULTS["sessions"]
            cur_start = 0
            cur_end = min(actual_limit, total) if actual_limit > 0 else total
        elif cmd == "3":
            if cur_sort == "skill":
                cur_reverse = not cur_reverse
            else:
                cur_sort = "skill"
                cur_reverse = _SORT_DEFAULTS["skill"]
            cur_start = 0
            cur_end = min(actual_limit, total) if actual_limit > 0 else total
        elif cmd == "4":
            if cur_sort == "agent":
                cur_reverse = not cur_reverse
            else:
                cur_sort = "agent"
                cur_reverse = _SORT_DEFAULTS["agent"]
            cur_start = 0
            cur_end = min(actual_limit, total) if actual_limit > 0 else total
        elif cmd == "5":
            if cur_sort == "last_used":
                cur_reverse = not cur_reverse
            else:
                cur_sort = "last_used"
                cur_reverse = _SORT_DEFAULTS["last_used"]
            cur_start = 0
            cur_end = min(actual_limit, total) if actual_limit > 0 else total
        elif cmd == "c":
            cur_query = None
            cur_sort = "uses"
            cur_reverse = _SORT_DEFAULTS["uses"]
            cur_start = 0
            cur_end = min(actual_limit, total) if actual_limit > 0 else total
        elif cmd == "o":
            _open_dashboard_bg(payload)
        else:
            pass


def _open_dashboard_bg(payload: dict) -> None:
    path = ROOT / "data.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    port = 8765
    while True:
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            server.allow_reuse_address = True
            break
        except OSError:
            port += 1
    url = f"http://127.0.0.1:{port}"
    print(f"\nOpening dashboard: {url}")
    if not sys.stdout.isatty() or not sys.stdin.isatty():
        print("Press Enter to return...")
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
        return
    try:
        webbrowser.open(url)
    except Exception:
        pass
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print("Dashboard running in background. Return to table? (y/n): ", end="")
    sys.stdout.flush()
    try:
        ans = _read_key("").strip().lower()
    except (EOFError, KeyboardInterrupt):
        ans = "y"
    print()
    if ans == "n":
        raise SystemExit


def _toon_value(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    if value is None:
        return ""
    return str(value)


def render_toon(payload: dict, limit: int = 100, offset: int = 0, agent: str | None = None, search: str | None = None) -> None:
    rows = payload.get("rows", [])
    if agent:
        rows = [r for r in rows if r.get("agent") == agent]
    if search:
        term = search.lower()
        rows = [r for r in rows if term in r.get("skill", "").lower()]
    total = len(rows)
    start = max(0, offset)
    end = min(start + limit, total) if limit > 0 else total
    page = rows[start:end]
    lines = []
    s = payload.get("summary", {})
    keys = ["uses", "views", "skills", "agents"]
    lines.append(f"summary{{{','.join(keys)}}}: {','.join(_toon_value(s.get(k, 0)) for k in keys)}")
    lines.append("")
    if not page:
        lines.append("skills{0}:")
        print("\n".join(lines))
        return
    row_keys = ["agent", "skill", "uses", "sessions", "views", "patches", "last_used", "confidence"]
    lines.append(f"skills{{{len(page)}}}:")
    for k in row_keys:
        vals = [_toon_value(r.get(k)) for r in page]
        lines.append(f"  {k}[{len(vals)}]: {','.join(vals)}")
    if total > len(page):
        lines.append("")
        shown_start = start + 1
        shown_end = start + len(page)
        lines.append(f"# showing {shown_start}-{shown_end} of {total} | --offset {end} --limit {limit} for next")
    print("\n".join(lines))


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
    parser.add_argument("--table", action="store_true", help="Render data as a terminal table")
    parser.add_argument("--toon", action="store_true", help="Render data in TOON format for agents")
    parser.add_argument("--limit", type=int, default=None, help="Max rows to show (default: auto for table, 100 for toon)")
    parser.add_argument("--offset", type=int, default=0, help="Rows to skip")
    parser.add_argument("--agent", type=str, default=None, help="Filter by agent name")
    parser.add_argument("--search", type=str, default=None, help="Filter by skill name substring")
    parser.add_argument("--query", type=str, default=None, help="Global filter (agent=X, skill=Y, or text)")
    parser.add_argument("--sort", type=str, default="uses", choices=["uses", "sessions", "skill", "agent", "last_used"], help="Sort column")
    parser.add_argument("--reverse", action="store_true", default=None, help="Reverse sort order")
    parser.add_argument("--open", action="store_true", help="Also open the web dashboard")
    args = parser.parse_args()
    path = write_data()
    if args.json:
        print(path.read_text())
        return
    payload = json.loads(path.read_text())
    if args.table:
        interactive = args.table and sys.stdout.isatty() and sys.stdin.isatty()
        cli_reverse = None if args.reverse is None else not _SORT_DEFAULTS.get(args.sort, True)
        render_table(payload, limit=args.limit, offset=args.offset, query=args.query or args.agent or args.search, sort=args.sort, reverse=cli_reverse, interactive=interactive)
        if args.open and not interactive:
            _serve(payload, args)
        return
    if args.toon:
        toon_limit = args.limit if args.limit is not None else 100
        render_toon(payload, limit=toon_limit, offset=args.offset, agent=args.agent, search=args.search)
        if args.open:
            _serve(payload, args)
        return
    _serve(payload, args)


def _serve(payload: dict, args: argparse.Namespace) -> None:
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
