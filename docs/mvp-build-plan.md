# MVP Build Plan: Poker Bot Battleground

_For Claude when building. Last updated: 2026-11-07 (00:55)_
_Read order: CLAUDE.md → docs/claude-context.md → this file → docs/design-doc.md sections referenced by the current milestone only._

## Resume protocol (do this every build session)
1. Read CLAUDE.md, docs/claude-context.md (standing instructions, corrections) and this file.
2. Find the first unchecked task in **Status**. Work only on that milestone.
3. Confirm the repo's tests are green before changing anything (`uv run pytest`).
4. Finish a task → tick it here, add one line to **Build log**, update docs/claude-context.md "Current status". Commit in the same turn.
5. If a task needs a decision not in docs/design-doc.md: pick the simplest option, mark it `(proposed)` in **Decisions made while building**, and tell Harry in chat.

## Preconditions (blocking)
- [ ] Harry confirms **Python** for engine/runner/CLI (design-doc §5). If Rust: M1–M3 change language; M4–M7 unchanged.
- [ ] Harry confirms game params (proposed): **blinds 1/2, stack 400 (200 bb), stacks reset every hand.** Same as MIT.

## MVP scope
**In:** Standard ladder, Rapid mode only (30 s CPU / 1,000 hands, 15 s startup, 512 MB), Python bots, upload → queue → sandboxed match → Glicko-2 → leaderboard → replay player.
**Out (post-MVP):** Open ladder, Standard-Regular, live follow + live stats view (§7.1), MIT shim, ACPC, JS bots, SSH, premiere/match wall, duplicate diff view.

## Status
| M | Milestone | Status |
|---|---|---|
| 0 | Repo skeleton | ☐ |
| 1 | Engine core (pure) | ☐ |
| 2 | Protocol + local bot runner + CLI | ☐ |
| 3 | Hand log + scoring | ☐ |
| 4 | Sandbox runner | ☐ |
| 5 | Web: upload, queue, ratings, leaderboard | ☐ |
| 6 | Replay player | ☐ |
| 7 | Private beta | ☐ |

## Repo layout (target)
```
pbb/
├── pyproject.toml          # uv; python 3.12; deps: eval7, pytest, hypothesis, ruff
├── engine/
│   ├── cards.py            # Card parse/format ("Ah"), Deck from seed
│   ├── rules.py            # HandState: pure, immutable-ish; legal_actions(), apply(action)
│   ├── match.py            # duplicate scheduling: deal i → seed; play seat A/B
│   ├── evaluate.py         # wraps eval7; only file that imports it
│   └── scoring.py          # bb/100, 95% CI, duplicate-adjusted line
├── protocol/
│   ├── messages.py         # build/parse JSON lines; strict validation
│   ├── fsm.py              # §3.0 transition TABLE (dict), not ifs
│   └── connection.py       # BotConnection: process I/O, seq, timeouts, CPU accounting hook
├── runner/
│   ├── local.py            # subprocess backend (dev only, own bots only)
│   ├── docker.py           # gVisor backend: spawn, cgroup freeze, cpu.stat
│   └── worker.py           # Postgres claim loop → match → log to R2 → result row
├── ratings/glicko2.py
├── cli/main.py             # pbb match A B --hands --seed --out ; pbb check BOT
├── bots/                   # random_bot, call_bot, equity_bot (examples + test fixtures)
├── tests/
│   ├── engine/ protocol/ runner/
│   └── nasty_bots/         # fork bomb, sleep, spin, flood, net, oom, bad json, no flush
├── images/standard/Dockerfile
└── web/                    # Next.js + Supabase (M5–M6)
```

## M0: Repo skeleton
- [ ] uv project, ruff, pytest, hypothesis; GitHub Actions running tests + ruff
- [ ] README: one paragraph + "run tests" command
**Done when:** CI green on an empty test.

## M1: Engine core (pure, no I/O)
Interface sketch:
- `HandState.new(seed_cards, button, stacks, blinds)`
- `.legal_actions() -> Legal(fold, check, call, min_raise, max_raise)`
- `.apply(Action) -> HandState` (raises on illegal)
- `.is_terminal`, `.payoffs`

Tasks:
- [ ] Cards + seeded deck (`random.Random(seed)`; never global RNG)
- [ ] Heads-up order: **button posts SB and acts first preflop, last postflop** (common bug)
- [ ] No-limit raise rules: min-raise = last raise size; all-in under min allowed; raise amount is **total "raise to"**, not increment (decide once, document in protocol)
- [ ] All-in runout, showdown, split pots, fold ends hand
- [ ] Duplicate: deal *i* uses seed `hash(match_seed, i)`; played twice with seats swapped
**Done when:** unit tests for every rule above, plus a Hypothesis test (random legal action sequences → chips conserved, never negative stack, always terminates).

## M2: Protocol + local runner + CLI
- [ ] messages.py: `match_start` (with `v`), `action_request` (with `seq`), `hand_result`, `match_end` (drafts below)
- [ ] fsm.py: (state, event) → (next_state, action) table from design-doc §3.0
- [ ] connection.py: line cap (e.g. 4 KB), strict JSON, seq echo check, invalid → fold, EOF/crash → forfeit, stderr capped
- [ ] runner/local.py: subprocess, `python -u`; wall-clock per decision; CPU via psutil child cpu_times (approximate, dev only)
- [ ] Example bots: random, call, equity (eval7 Monte Carlo with budget scaling from `cpu_budget_ms`)
- [ ] `pbb match` and `pbb check` (handshake + one hand + match_end)
**Done when:** `pbb match bots/equity_bot bots/call_bot --hands 1000 --seed 1` finishes, is deterministic for the same seed, and equity_bot wins clearly. `pbb check` passes all example bots and fails the nasty_bots for bad JSON and missing flush.

Draft messages (proposed):
```json
{"type":"hand_result","hand_id":4812,"deltas":[40,-40],"showdown":{"0":["Ah","Kd"],"1":["9d","9c"]},"board":["7c","2h","Ks","4d","9h"]}
{"type":"match_end","result":"complete","hands":1000,"cpu_used_ms":14200}
```

## M3: Hand log + scoring
Log line per hand (proposed, terse, ACPC-flavoured):
`<hand_id> <deal> <seatA_bot> | <holeA> <holeB> | <board> | <actions per street, / separated> | <deltaA> | <cpu_ms per decision, A;B>`
- [ ] Writer in engine; reader/parser in Python, then a TS port in M6 (shared fixture file as the contract test)
- [ ] scoring.py: bb/100 ± 95% CI (per-deal duplicate sums as samples), significant yes/no
**Done when:** a 1,000-hand log round-trips through the parser; measure the real gzipped size and record it in design-doc §7.4.

## M4: Sandbox runner (throwaway VM only, never Harry's laptop)
- [ ] images/standard/Dockerfile: python 3.12 slim + numpy, scipy, numba, eval7; thread env vars = 1
- [ ] docker.py: exact `docker run` from design-doc §4.1; cgroup.freeze 1/0; cpu.stat usage_usec before/after; startup phase uncharged
- [ ] Find the real cgroup path on the VM (unverified assumption)
- [ ] Nasty bot suite passes: fork bomb (pids cap), `sleep` (wall-clock kill), spin (CPU budget → folds then out), stdout flood (line cap), socket connect (fails), write outside /tmp (fails), allocate 1 GB (OOM → forfeit), import ctypes (harmless)
- [ ] Measure ms per decision of gVisor round trip and decisions/hand; record in design-doc
**Done when:** a full match runs in gVisor with correct CPU accounting, and every nasty bot ends in the expected outcome.

## M5: Web (Next.js + Supabase + TS)
- [ ] Auth (Supabase, GitHub or email). Tables: profiles, bots, bot_versions, matches, ratings
- [ ] Upload: zip → Supabase Storage; **validation happens on the runner** (§4.2 rules), not on the web server
- [ ] Matchmaker: cron / Postgres function that pairs active bots of close rating into `matches` (status queued)
- [ ] worker.py: SKIP LOCKED claim (§5) → match → gzip log to R2 → result row → Glicko-2 update (per match for MVP)
- [ ] Runner credential: insert-and-update only on matches/ratings via RPC; R2 key put-only
- [ ] Pages: leaderboard, bot page (rating history sparkline, recent matches), match page (summary)
- [ ] Monospace, black and white CSS
**Done when:** two accounts upload bots, matches run unattended, and the leaderboard updates.

## M6: Replay player
- [ ] Fetch log from R2 → parse (TS) → pure `stateAt(events, t)`
- [ ] ASCII table component (§7.5), play/pause/seek, speeds 1x/5x/20x, smart pacing, CPU think bars
**Done when:** any finished match replays smoothly on mobile width (~48 chars).

## M7: Private beta
- [ ] Dedicated runner box (Hetzner auction), firewall per §4.5
- [ ] Starter kit page: protocol doc, example bot, `pbb check`
- [ ] Invite ~10 people; collect bugs

## Known traps (from earlier corrections)
- Use cgroup freeze, never `docker pause`.
- 1,000 hands, ~4 decisions/hand (unverified); don't size things at 2,000.
- Out of memory → forfeit, never extra time.
- Never run uploaded bots outside the sandbox VM, even "just to test".
- Don't pitch Rust on speed.
- Engine time isn't charged to bots; don't optimise the engine before M4 measurements.

## Decisions made while building (proposed until Harry confirms)
- Blinds 1/2, stack 400, reset each hand.
- `raise.amount` = total raise-to amount.
- eval7 for hand evaluation, wrapped in one module.
- Glicko-2 updates per match for MVP.
- Upload validation on the runner, not the web server.

## Build log
- 2026-11-07: Plan written. No code yet. Waiting on preconditions.
