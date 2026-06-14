# CourtVision AI Agent Guide

## Collaboration

- Treat the user as a junior developer collaborating with AI, not outsourcing
  their thinking.
- Prefer clean, maintainable, production-style code and practical reasoning.
- Explain root causes and tradeoffs when debugging.
- Keep Codex as the primary editor, verifier, and final decision-maker.
- Under the three-brain protocol, Claude, Gemini, and Antigravity are read-only
  advisory CLIs unless the user explicitly delegates edits.

## Product Boundaries

- CourtVision AI is replay-first and must not imply licensed low-latency NBA
  coverage.
- Public fixtures are synthetic or curated historical replay.
- Player identity is attribution only for shot quality.
- Defender-aware quality requires licensed tracking data.

## Checkpoint Protocol

Before ending a substantial work session or approaching the context limit:

1. Finish the current coherent change; do not commit known-broken code.
2. Run the relevant tests, linting, type checks, builds, and migrations.
3. Update `HANDOFF.md` with completed work, exact verification results, known
   blockers, and the next safe resume point.
4. Review `git status` and the staged diff for secrets, generated files, and
   unrelated user changes.
5. Commit the completed increment with a descriptive message.
6. Push the current branch to
   `https://github.com/jnehohwa/courtvision-ai`.
7. Confirm the local branch is synchronized with its upstream before stopping.

Do not manufacture empty commits purely to inflate activity. Each commit should
represent a coherent, verified engineering increment.

On this machine, GitHub CLI commands must use:

```bash
export GH_CONFIG_DIR="$HOME/Library/Application Support/gh"
```

The default `~/.config` directory is owned by `root`, so `gh` cannot persist
configuration there.
