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

Hermes and OpenCode provide structured counters. Other agents are measured by explicit `SKILL.md` file reads, so their numbers are minimums.
