# Claude working context: Poker Bot Battleground

_For Claude. Read this at the start of any session in this repo, then read docs/design-doc.md for the full design. **When building, read docs/mvp-build-plan.md and follow its resume protocol.**_
_Last updated: 2026-11-08_

## Standing instructions from Harry
- **Keep docs/design-doc.md and this file up to date** whenever a useful decision, finding, number or correction comes up. Do it in the same turn, without waiting to be asked (don't end with "want me to add this to the doc?"). Bump "Last updated". **Update both files**, not just the design doc. When building, also tick progress in `docs/mvp-build-plan.md`.
- **Keep the design doc lean:** record decisions, numbers, constraints and open questions only. Don't write explanations of rejected alternatives or reasoning I can re-derive. A one-line "rejected: X" is enough.
- **Answer the question in chat first; doc updates come after, quietly.**
- Harry wants direct, opinionated guidance and copy-paste-ready output, not hedged advice.
- Harry writes tersely and uses abbreviations (e.g. "cbi"). If a message is ambiguous, answer the most likely reading briefly and ask, rather than redesigning things on a guess.
- When Harry says "don't write any code", give prose only, no snippets.
- Harry is often on mobile: keep answers to about a screen or two.

## About Harry (relevant to this project)
- Glasgow-based freelance web dev and first-year Strathclyde student. Stack: React/Next.js/Node/Supabase/PHP/MySQL/Java. Comfortable with the full stack; still new to infra and security. **No Rust, Go or (apparently) Python experience.**
- Interested in Rust for career transferability, not speed (speed is irrelevant for this project).
- Freelance client work means his main machine holds client credentials and customer data, so keep uploaded bots well away from it.
- Wants the platform to let people **push the limits** of poker bots, and to match real competition conditions (MIT/CMU etc.).
- Wants existing competition bots (e.g. MIT Pokerbots) to be portable onto the engine.

## Current status
- **Phase: building. M1 engine done 2026-11-08** (`pbb/engine/`: cards, evaluate (eval7), rules `HandState`, match duplicate schedule; 121 tests green). **Next: finish M2** = `pbb match` + equity_bot.
- CI hardening 1–3 done 2026-11-08 (uncommitted): policy guard test, image smoke job, Dependabot. Branch protection on `main` is Harry's to switch on.
- Python confirmed. The bot↔engine "walkie-talkie" (Harry's name for it) is built ahead of M1: `pbb/protocol/{messages,fsm,connection}.py`, `pbb/runner/{local,docker}.py`, `images/standard/Dockerfile`, call/random bots, `pbb check`. 63 tests green on Harry's Windows machine (own harmless fixture bots only). Docker/gVisor backend written but untested (VM only). First commit `4273145` on `dev` 2026-11-08, **not pushed** (CI unverified until push).
- Dev env: I installed uv via `pip --user` into Python 3.14 (not on PATH); in Harry's VS Code terminal `python` is the activated `.venv` (3.12, no uv), so `python -m uv` fails for him. Told him to `winget install astral-sh.uv` and use plain `uv`. uv-managed Python 3.12 runs the project.
- MVP scope: Standard-Rapid only; Open, Regular, live follow/stats, MIT shim, JS, SSH all post-MVP.
- Web side: Next.js + Supabase + TypeScript (effectively settled). Match logs proposed for Cloudflare R2.
- Sandbox threat model in design-doc §4 (4.1–4.7).
- **Two ladders** (design-doc §2): Standard and Open.
- **Proposals awaiting Harry's reaction:** match view (§7.1–7.3), storage (§7.4), match player (§7.5), compatibility shims (§3.1), MVP plan and its "decisions made while building".

## Decision log (newest first)
| Date | Decision | Notes |
|---|---|---|
| 2026-11-08 | (Proposed) CI hardening list in mvp-build-plan; biggest item = branch protection requiring CI. Open: allow nasty bots under gVisor on GitHub's ephemeral runners? | Harry worried security regressions sneak through |
| 2026-11-08 | **Game params confirmed:** blinds 1/2, stack 400 (200 bb), reset every hand | Harry: "go for it" |
| 2026-11-08 | (Proposed) Fold illegal when check is free; invalid reply then = check, not fold. Raise cap = effective stack | From building M1 |
| 2026-11-08 | (Proposed) **CI yes, CD web only.** GitHub Actions: pytest + ruff (+ later image build-only, TS parser contract test); never run uploaded bots in CI. Web: Vercel auto-deploy + preview branches; Supabase migrations manual. Runner box: manual deploy for MVP, no deploy SSH key in Actions; later a pull model (box polls signed tag) | Harry asked if CI/CD is worth it |
| 2026-11-07 | **Python confirmed** for engine/runner/CLI | Harry, via question prompt |
| 2026-11-07 | (Proposed) Protocol details from building the walkie-talkie: reply carries `seq`; non-JSON lines = ignored debug, malformed JSON = fold; budget gone → engine folds without waking bot; unread stdin > 64 KB → forfeit | Full list in mvp-build-plan "Decisions made while building" |
| 2026-11-07 | (Proposed) **MVP build plan** in `docs/mvp-build-plan.md`: start with pure engine + local CLI; MVP = Standard-Rapid only. Proposed defaults: blinds 1/2, stack 400 reset per hand (MIT-like), `raise.amount` = raise-to total, eval7 wrapped in one module, Glicko-2 per match, upload validation on runner | Harry asked where I'd start building. Proposals stay in the plan until Harry confirms |
| 2026-11-06 | **No shared memory**; pipes only | Bottleneck is always bot think time |
| 2026-11-06 | Harry agreed: keep the freeze (no pondering) for v1 | |
| 2026-11-06 | **Keep "no pondering" for v1, reframed:** the freeze is about server load and simple accounting, not fairness (budget is CPU time, so pondering is charged anyway). Possible later pondering mode: no freeze, charge CPU, cap cores, ~2× cost | Only HPI's ban is sourced; MIT/ACPC policy unverified |
| 2026-11-06 | **Model message flow as a state machine** (per bot: SPAWNED → STARTING → IDLE ⇄ THINKING → DONE, FORFEIT on crash/EOF/OOM/startup timeout). Engine speaks first; one reply per request; `seq` echoed; stray stdout quarantined; transition table as data (design-doc §3.0) | Harry's idea |
| 2026-11-06 | **Stay with JSON lines over stdin/stdout.** Add `v` to `match_start`; flush after every reply; strict alternation; small messages | Real cost is gVisor/pipe round trip, not parsing |
| 2026-11-06 | (Proposed) **Compatibility:** JSON lines native; `pbb.compat.mit` skeleton shim at launch; ACPC adapter later; `pbb-cli check` conformance test | No universal standard; MIT changes variant yearly |
| 2026-11-06 | (Proposed) **Decouple the match from the viewing.** Matches run at full speed; client-side player plays the log at human pace; live = tail mode | Pacing the match would hold sandboxes for hours |
| 2026-11-06 | (Proposed) **Save every match.** Gzipped log in R2; summary row in Postgres; no per-action rows | |
| 2026-11-06 | (Proposed) Live match view panels (design-doc §7.1–7.3) | |
| 2026-11-06 | Open stays at **1,000 hands** | |
| 2026-11-06 | Two ladders: Standard (Rapid 30 s / Regular 7 min, 512 MB) and Open (~20 min, 2 GB) | Open numbers are proposals |
| 2026-11-06 | Uncharged startup phase before the clock starts | |
| 2026-11-06 | Memory cap: 512 MB Standard, 2 GB Open | |
| 2026-11-06 | Runner schedules by free memory | |
| 2026-11-05 | No import blocklist; image is the allow-list; `.py` + data only | |
| 2026-11-05 | Never run user bots on Harry's laptop/personal machine | |
| 2026-11-05 | Upload rules (design-doc §4.2) | |
| 2026-11-05 | Runner holds only narrow queue credential (+ put-only R2 key) | |
| 2026-11-05 | Website never executes bots | |
| 2026-11-05 | (Proposed, unconfirmed) Python engine/runner for v1; optional Rust port later | |
| 2026-11-05 | (Proposed, unconfirmed) Postgres SKIP LOCKED queue, no Redis | |
| 2026-11-05 | Terminal look = CSS; SSH would be an extra front end | |
| 2026-11-05 | Separate Glicko-2 pool per mode | |
| 2026-11-05 | Match = 1,000 hands (500 duplicate deals) | |
| 2026-11-05 | Compute limit = total CPU budget per match + wall-clock backstop | |
| 2026-11-05 | Freeze idle bot via cgroup.freeze, not `docker pause` | |
| 2026-11-05 | Sandbox: Docker + gVisor, no network, read-only, cap-drop, non-root, stdin/stdout only | |
| 2026-11-05 | Heads-up NLHE only, Python bots only, at launch | |

## Corrections I've made (don't repeat these mistakes)
- I earlier said "no pondering" was a fairness rule. Wrong: with a CPU-time budget pondering is charged anyway; the freeze mainly saves server load and keeps accounting simple.
- I originally sized examples at 2,000 hands and ~12 decisions/hand. Use 1,000 hands and ~4 decisions/hand (still unverified).
- My first runner snippet called `docker pause`/`unpause`. Too slow; use the cgroup freezer.
- Memory exhaustion does not extend decision time. CPU budget is the limit; OOM → forfeit.
- Don't sell Rust or Go to Harry on speed.
- I misread "cbi for python and rust" as "can't be bothered". Harry meant a pros/cons comparison. Don't guess at terse messages.
- **Repeatedly** ended answers with "want me to add this to the doc?" instead of just updating. Stop asking; update both files.
- When Harry asked about personal risks of an escape, I wrote it into the doc instead of answering in chat, and he interrupted. Answer in chat first.
- Harry once interrupted a write to this file; that did **not** mean "stop updating it".
- "1000 matches" in Harry's wording meant the **1,000 hands per match** limit.
- On Windows, `sys.executable` in a uv venv is a trampoline that spawns the real Python; suspending it mid-spawn kills the bot. Launch local bots with `sys._base_executable` (`bot_python()`).
- Harry rejected me running `git init` + `remote add` for him; he did it himself. Ask before git setup commands.

## Unverified assumptions (check before relying on them)
- Dependabot supports the `uv` ecosystem (believed GA 2025; not checked).
- ~4 decisions per hand in heads-up NLHE.
- Match lengths (Rapid ~1 min, Regular ~14 min, Open ~40 min) are worst cases.
- "Many heads-up hands end preflop" is general poker knowledge, not measured.
- Smart-pacing hold times are illustrative.
- Hand log ~100 B/hand, ~25–30 KB gzipped per match (measure in M3).
- 1,000 matches/day is illustrative.
- gVisor round trip ~1–2 ms per decision; ~50–100 MB overhead per sandbox (measure in M4).
- cgroup path `/sys/fs/cgroup/system.slice/docker-<id>.scope/` (find in M4).
- `pokerkit` / `treys` still maintained (not checked). eval7 0.1.11 installs on Python 3.12 Windows (checked 2026-11-08; Linux image unchecked).
- MIT Pokerbots' official library list; MIT skeleton API names from memory.
- "MIT shim ≈ 1 day of work" is my estimate.
- `--network=none` keeps loopback under gVisor (not checked).
- Open ladder numbers are proposals.
- phevaluator / OpenSpiel / onnxruntime install cleanly in slim Python 3.12 (not checked).
- UK GDPR/ICO comment in design-doc §4.7 is general awareness, not legal advice.
- Mockup numbers in design-doc §7.1 and §7.5 are illustrative.
- Pricing (checked 2026-11-06 via third-party summaries): Supabase free = 500 MB DB / 1 GB files / 5 GB egress, pauses after a week idle; R2 free = 10 GB, 1M writes, 10M reads, free egress, $0.015/GB-month after.

## Open questions
See docs/design-doc.md §9 and docs/mvp-build-plan.md preconditions. Biggest: Open ladder limits and gating; where the dev/beta runner lives; stats computed in runner vs browser; hand-log format (draft in plan); replays public vs owners-only.

## Session notes
- 2026-11-05: Design rebuilt from project brief and memory. Sandboxing, hardware, match length, competition rules, game modes, stack comparison, Python vs Rust; recommendation Python v1.
- 2026-11-05/06: Competition library rules researched; two ladders (§2); Open stays 1,000 hands.
- 2026-11-06: Website design: match view (§7.1–7.3), storage (§7.4), watching/playback (§7.5); compat (§3.1); protocol (JSON lines kept, state machine §3.0, pondering reframed, no shared memory).
- 2026-11-07 (00:54): Harry asked where I'd start building an MVP. Answered in chat (pure engine + local CLI first). Wrote `docs/mvp-build-plan.md` with resume protocol, milestones M0–M7, done-when criteria, repo layout, draft formats, known traps, build log.
- 2026-11-07: Harry set up git locally (branch `dev`, origin `harry-dunlop/poker-bot-battling`), confirmed Python, asked me to build the "walkie-talkie" (sandboxed bot only able to answer with JSON when asked). Built protocol + backends + tests; see Current status.
- 2026-11-07 (01:05): Harry asked to get the docs into a repo. Attached `Harry-Dunlop/poker-bot-battling`, cloned to `/home/claude/poker-bot-battling`, copied the three project docs into `docs/`.
- 2026-11-08: Explained CI/CD (CI yes, CD web only), game params, how reset-per-hand works. Harry confirmed params; built M1 engine.
