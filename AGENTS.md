# Useless Skills agent guide

## Purpose

Local dashboard that aggregates skill usage from Hermes, OpenCode, Codex, Claude Code, Pi, Continue, Cline, Cursor, Roo Code, and Windsurf when their data is available. Hermes and OpenCode expose structured counters; other agents are measured by counting explicit `SKILL.md` file reads, so their numbers are minimums.

## Project structure

```text
useless-skills/
├── README.md                         # User-facing overview and CLI docs
├── app.py                            # Entry point, collectors, table/toon rendering
├── VERSION                           # Current semantic version
├── CHANGELOG.md                      # Release notes by version
├── versioning.py                     # SemVer tag helpers and VERSION read/write
├── changelog.py                      # Extract release notes for a version
├── .github/workflows/release.yml     # Tag-triggered release with SHA256SUMS
├── useless-skills                    # Launcher script (./useless-skills ...)
├── tests/
│   ├── test_app.py                   # Core unit + rendering tests
│   └── test_release.py               # Versioning/changelog tests
└── data.json                         # Generated dashboard payload (gitignored changes)
```

## Conventions

- The launcher is `./useless-skills`, which runs `python3 app.py` from the project root.
- `build_payload()` scans agent session logs; results are cached under `.cache/` keyed on input mtimes so repeat runs are instant. Use `--no-cache` to force a rescan.
- `scan_jsonl_paths` only counts files that mention `SKILL.md`, to avoid scanning unrelated logs.
- Keep `VERSION` and the top `## X.Y.Z` section of `CHANGELOG.md` in sync; the release workflow fails if they disagree with the pushed tag.
