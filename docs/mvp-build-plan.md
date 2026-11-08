# MVP Build Plan: Poker Bot Battleground

_For Claude when building. Last updated: 2026-11-08_
_Read order: CLAUDE.md → docs/claude-context.md → this file → docs/design-doc.md sections referenced by the current milestone only._

## Resume protocol (do this every build session)
1. Read CLAUDE.md, docs/claude-context.md (standing instructions, corrections) and this file.
2. Find the first unchecked task in **Status**. Work only on that milestone.
3. Confirm the repo's tests are green before changing anything (`uv run pytest`).
4. Finish a task → tick it here, add one line to **Build log**, update docs/claude-context.md "Current status". Commit in the same turn.
5. If a task needs a decision not in docs/design-doc.md: pick the simplest option, mark it `(proposed)` in **Decisions made while building**, and tell Harry in chat.

## Preconditions (blocking)
- [x] Harry confirms **Python** for engine/runner/CLI (design-doc §5). Confirmed 2026-11-07.
- [x] Harry confirms game params: **blinds 1/2, stack 400 (200 bb), stacks reset every hand.** Confirmed 2026-11-08.

## MVP scope
**In:** Standard ladder, Rapid mode only (30 s CPU / 1,000 hands, 15 s startup, 512 MB), Python bots, upload → queue → sandboxed match → Glicko-2 → leaderboard → replay player.
**Out (post-MVP):** Open ladder, Standard-Regular, live follow + live stats view (§7.1), MIT shim, ACPC, JS bots, SSH, premiere/match wall, duplicate diff view.

## Status
| M | Milestone | Status |
|---|---|---|
| 0 | Repo skeleton | ◐ CI file written, not yet seen green (needs first push) |
| 1 | Engine core (pure) | ✅ 2026-11-08 (`pbb/engine/`, 58 engine tests incl. Hypothesis) |
| 2 | Protocol + local bot runner + CLI | ◐ transport done (built ahead of M1 at Harry's request); `pbb match` + equity_bot wait for engine |
| 3 | Hand log + scoring | ☐ |
| 4 | Sandbox runner | ◐ docker.py + Dockerfile written, untested (VM only) |
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
- [x] uv project, ruff, pytest, hypothesis; GitHub Actions running tests + ruff (`.github/workflows/ci.yml`; unverified until pushed)
- [x] README: one paragraph + "run tests" command
**Done when:** CI green on an empty test.

### CI hardening (proposed 2026-11-08)
- [ ] Branch protection on `main`: require CI green (Harry, GitHub settings)
- [x] Sandbox policy guard `tests/runner/test_sandbox_policy.py`: required flags, forbidden-flag list, resource ceilings per ladder, single ro mount, env = thread vars only, fixed command
- [x] CI job `image`: build images/standard, run `images/smoke/main.py` via `scripts/image_smoke.py` with production flags but runc (checks uid, no caps, no_new_privs, ro fs, /tmp noexec, no network, libs incl. numba on ro fs). Written; first verified run = next push
- [x] Dependabot `.github/dependabot.yml` (uv, actions, docker base image; weekly, targets `dev`)
- [ ] M4: CI job installs runsc on GitHub runner, runs `-m vm_only` nasty bots (own bots only; **needs Harry's OK**: loosens "VM only" to "ephemeral VM")
- [ ] After M2: nightly big Hypothesis run + same-seed match twice → identical logs
- Never in CI: uploaded bots. Deferred: Trivy, CodeQL.

## M1: Engine core (pure, no I/O)
Interface sketch:
- `HandState.new(seed_cards, button, stacks, blinds)`
- `.legal_actions() -> Legal(fold, check, call, min_raise, max_raise)`
- `.apply(Action) -> HandState` (raises on illegal)
- `.is_terminal`, `.payoffs`

Tasks:
- [x] Cards + seeded deck (`random.Random(seed)`; never global RNG)
- [x] Heads-up order: **button posts SB and acts first preflop, last postflop** (common bug)
- [x] No-limit raise rules: min-raise = last raise size; all-in under min allowed; raise amount is **total "raise to"**, not increment (decide once, document in protocol)
- [x] All-in runout, showdown, split pots, fold ends hand
- [x] Duplicate: deal *i* uses seed `sha256(match_seed, i)`; played twice, bot 0 on button then bot 1, same cards by position
**Done when:** unit tests for every rule above, plus a Hypothesis test (random legal action sequences → chips conserved, never negative stack, always terminates).

## M2: Protocol + local runner + CLI
- [x] messages.py: `match_start` (with `v`), `action_request` (with `seq`), `hand_result`, `match_end` (drafts below)
- [x] fsm.py: (state, event) → (next_state, effect) table from design-doc §3.0
- [x] connection.py: line cap 4 KB, strict JSON, seq echo check, invalid → fold, EOF/crash → forfeit, stderr capped 64 KB, CPU budget polled every 5 ms
- [x] runner/local.py: subprocess, `python -u`; psutil suspend/resume + cpu_times (approximate, dev only)
- [x] Example bots: random, call. [ ] equity (needs eval7 → after M1)
- [x] `pbb check` (handshake + one scripted hand + match_end). [ ] `pbb match` (needs engine)
- [x] Harmless misbehaving fixture bot `tests/fixtures/behave.py` (17 modes) + tests: 63 pass on Windows
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
- [x] images/standard/Dockerfile: python 3.12 slim + numpy, scipy, numba, eval7; thread env vars = 1 (versions unpinned: pin on VM)
- [x] docker.py: exact `docker run` from design-doc §4.1 (+ `--cidfile`, tmpfs nosuid/nodev); cgroup.freeze 1/0 waiting for `frozen 1`; cpu.stat usage_usec; startup uncharged (in connection.py). **Written, not run.** Arg builder unit-tested
- [ ] Hostile bots in `tests/nasty_bots/`, marked `vm_only` (pytest skips them by default)
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
- ~~Blinds 1/2, stack 400, reset each hand.~~ Confirmed 2026-11-08.
- Fold is illegal when check is free (engine raises). M2: an invalid reply when check is legal → engine **checks**, not folds.
- Raise bounds capped at the opponent's covering amount (effective stack); can't raise an all-in player; a short all-in raise doesn't change the min-raise size.
- Hand ids 1-based; hand 2i+1/2i+2 share deal i; seat = bot (bot 0 always seat 0), button alternates.
- Engine and protocol share one `Action` type (`pbb.engine.rules.Action`).
- `raise.amount` = total raise-to amount.
- eval7 for hand evaluation, wrapped in one module.
- Glicko-2 updates per match for MVP.
- CI = pytest + ruff on push (later: `docker build` images/standard, TS parser contract test). CI never runs uploaded bots. Web CD via Vercel (M5); runner deployed by hand, no deploy key in GitHub Actions.
- Upload validation on the runner, not the web server.
- Bot reply = `{"seq":n,"action":"fold|check|call|raise","amount":int}`; `amount` only on raise.
- Non-JSON stdout lines = stray debug print: ignored + flagged, the clock keeps running. JSON that fails reply validation (bad shape, illegal, out of range, future seq), or an oversized line → invalid → fold.
- Stale seq (late reply after a timeout) discarded; extra replies flagged.
- CPU budget used up → connection returns no action without waking the bot; engine folds (outcome `budget`).
- Engine stdin backlog > 64 KB (bot not reading) → forfeit.
- Startup: anything other than `{"ready":true}` is ignored; only timeout/death forfeits.
- `hand_result` is written while the bot is frozen; it reads it at the next thaw.
- Local backend runs the base interpreter, not the venv/uv launcher (Windows trampoline broke suspend). Local bots get stdlib only.

## Build log
- 2026-11-07: Plan written. No code yet. Waiting on preconditions.
- 2026-11-07: Python confirmed. Built the walkie-talkie ahead of M1: M0 skeleton, protocol (messages/fsm/connection), local + docker backends, Dockerfile, call/random bots, `pbb check`. 63 tests green locally; docker backend untested (needs VM). Not committed.
- 2026-11-08: Game params confirmed. M1 engine done: `pbb/engine/{cards,evaluate,rules,match}.py`, eval7 0.1.11 installs on 3.12/Windows. 121 tests green (58 engine incl. 500-example Hypothesis run). Committed `4273145` on `dev` (first commit; not pushed).
- 2026-11-08: CI hardening 1–3: sandbox policy guard (18 tests, 139 total green), image build + smoke job, Dependabot. Image job unverified until pushed (no Docker on Harry's machine).
