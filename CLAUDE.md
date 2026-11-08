# CLAUDE.md: Poker Bot Battleground

You are building this project from scratch with no prior context. Read these in order before doing anything:

1. `docs/claude-context.md`: standing instructions from Harry, his preferences, decision log, known mistakes to avoid.
2. `docs/mvp-build-plan.md`: the milestones (M0–M7), the resume protocol, and the current status. Work only on the first unchecked milestone.
3. `docs/design-doc.md`: the full design. Read only the sections the current milestone needs.

## Rules that always apply
- Harry wants direct, opinionated guidance and copy-paste-ready output. Keep answers short (about a screen or two).
- Answer in chat first. Update the docs after, in the same turn, without asking. Keep `docs/claude-context.md` and `docs/mvp-build-plan.md` current, and tick milestones as they finish.
- Keep the design doc lean: decisions, numbers, constraints and open questions only.
- Never run uploaded or untrusted bot code outside the sandbox VM, not even to test it. Never run bots on Harry's personal machine.
- Commit only when Harry asks. Work on a branch, not `main`.

## Before writing code
Harry must confirm two things (see `docs/mvp-build-plan.md` → Preconditions):
- Python for the engine, runner and CLI (the plan assumes it).
- Game params: blinds 1/2, stacks of 400 reset each hand.

If he hasn't confirmed them, ask before M1. Don't guess.

## Stack, short version
- Engine, runner, CLI: Python 3.12, uv, pytest, hypothesis, ruff. Hand evaluation via eval7.
- Website: Next.js + TypeScript + Supabase (Postgres). Match logs in Cloudflare R2.
- Bots talk to the engine over JSON lines on stdin/stdout.
- Terminal look is plain CSS: monospace, black and white, ASCII.
