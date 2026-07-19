# Useless Skills

![Useless Skills Dashboard](assets/useless-skills-screenshot.webp)

Local dashboard that aggregates skill usage from Hermes, OpenCode, Codex, Claude Code, Pi, Continue, Cline, Cursor, Roo Code, and Windsurf when their data is available.

## Launch

```bash
cd ~/dev/useless-skills
./useless-skills
```

Options:

```bash
./useless-skills --port 9000
./useless-skills --no-open
./useless-skills --json
```

## CLI table

```bash
./useless-skills --table
```

Renders a terminal table of skill usage. In a real terminal it becomes interactive.

```bash
./useless-skills --table --query "agent=Codex" --sort sessions --limit 20 --offset 40
./useless-skills --table --search seo --reverse
./useless-skills --table --open
```

### Interactive shortcuts

| Key | Action |
|-----|--------|
| `n` / `p` | Next / previous page |
| `f` | Filter (`agent=X`, `skill=Y`, or plain text) |
| `1`-`5` | Sort by `uses`, `sessions`, `skill`, `agent`, `last_used` (press again to toggle ASC/DESC) |
| `c` | Clear filters and sort |
| `o` | Open web dashboard in background |
| `q` | Quit |

Press `Ctrl+C` during prompts to return to the table instead of crashing.

### CLI flags

| Flag | Description |
|------|-------------|
| `--limit N` | Max rows (default: terminal height for table, `100` for toon) |
| `--offset N` | Skip N rows |
| `--query` | Global filter (`agent=X`, `skill=Y`, or text) |
| `--search` | Substring match on skill name (backward-compat shorthand) |
| `--agent` | Filter by agent name (backward-compat shorthand) |
| `--sort` | `uses`, `sessions`, `skill`, `agent`, `last_used` |
| `--reverse` | Reverse default sort order |

## TOON output

```bash
./useless-skills --toon
```

Compact columnar format for agents. Defaults to 100 rows.

```bash
./useless-skills --toon --limit 50 --offset 100 --query Codex
```

Hermes and OpenCode provide structured counters. Other agents are measured by explicit `SKILL.md` file reads, so their numbers are minimums.
