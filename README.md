# Poker Bot Battleground

A Lichess-style site where uploaded heads-up No-Limit Hold'em bots play each other under a fixed CPU budget per match. Bots talk to the engine over JSON lines on stdin/stdout and run sandboxed in gVisor. The design is in `docs/design-doc.md` and the build plan in `docs/mvp-build-plan.md`.

```bash
uv sync
uv run ruff check .
uv run pytest
uv run pbb check bots/call_bot      # protocol conformance check (your own bots only)
```

Only run your own bots locally. Uploaded or untrusted bots run inside the sandbox VM only.
