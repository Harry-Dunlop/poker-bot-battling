# Poker Bot Battleground — Design Doc

_Last updated: 2026-11-06 (21:00)_

A Lichess-style site where users upload poker bots that play other users' bots. Ratings decide which lobby a bot plays in. Each bot gets a fixed CPU budget per match, so an efficient bot beats one that just throws compute at the problem. The look is minimal: black and white, monospace, ASCII.

---

## 1. Decisions

| Area | Decision | Why |
|---|---|---|
| Game | Heads-up No-Limit Hold'em only (at launch) | Rules out collusion at multi-way tables |
| Variance | Duplicate poker: every deal played twice, seats swapped | Takes most of the card luck out of results |
| Match length | **1,000 hands** (500 deals × 2 seats) **in every mode, including Open** | Standard in ACPC, MIT and CMU events. For more statistical confidence, play more matches, not longer ones |
| Ratings | Glicko-2, **separate pool per game mode** | Handles high-variance results and new bots better than Elo |
| Lobbies | Rating bands within a mode | |
| Ladders | **Two ladders: Standard (restricted, light) and Open (beefy, push-the-limits)**. See §2 | Lets Standard stay a pure efficiency game while Open shows what's possible |
| Bot language | Python only at launch; JavaScript next | Each extra language means another sandbox image to maintain |
| Libraries | Fixed per ladder, baked into that ladder's image. No import blocklist | Missing packages can't be imported; the container, not import rules, is the security boundary |
| Bot I/O | JSON lines over stdin/stdout, one action per request | This is the only channel, which is how "poker actions only" is enforced |
| Compatibility | **(Proposed) MIT-style skeleton shim at launch; ACPC adapter later.** See §3.1 | No universal bot protocol exists; MIT bots are written against a skeleton class, so matching that API is what makes porting easy |
| Invalid output | Timeout, garbage, illegal action or oversized line → **fold** | |
| Crash / OOM / closed stdout | **Match forfeit**, logged for the bot author | |
| Compute limit | **Total CPU budget per bot per match** (chess-clock style), measured in CPU time from cgroups, not wall-clock | Fair even under server load; rewards managing your own budget |
| Startup phase | Uncharged init window before the clock starts (load models, numba JIT) | Otherwise numba/ONNX bots lose budget before hand 1 |
| Wall-clock cap | Hard backstop (e.g. 10 s per decision) | Catches bots that sleep or block without using CPU |
| No pondering | Bots can't compute on the opponent's time (enforced by the cgroup freezer) | Matches HPI rule. Honest reasons: halves server load (only one bot runs at a time) and keeps accounting/state machine simple. **Not a fairness necessity**: the budget is CPU time, so pondering would be charged anyway. Pondering is also of limited use in poker (opponent's action is the information; continuous bet sizes make precomputation branchy). Could be a separate mode later (don't freeze, charge CPU, cap cores; ~2× server cost) |
| Where bots run | Never on Harry's laptop or any machine with personal data. Dedicated runner box only; dev testing of other people's bots only inside a throwaway VM | A sandbox escape must land somewhere with nothing worth taking |
| Match storage | **Save every match.** Gzipped hand log per match in object storage (R2); one summary row per match in Postgres. See §7.4 | ~25–30 KB per match; storage is cheap if logs stay out of Postgres |
| Watching matches | **Decouple the match from the viewing.** Matches run at full speed; the site is a player that plays the hand log back at human pace. Live = the same player following the newest hand. See §7.5 | Pacing the match itself would tie up sandboxes (up to ~4 GB for Open) for hours |

## 2. Ladders and game modes

Two ladders, each with its own sandbox image, limits and Glicko-2 pools.

| | **Standard** (competitive, light) | **Open** (beefy, push the limits) |
|---|---|---|
| Purpose | Efficiency and cleverness under tight limits; closest to student competitions | Frontier bots: solvers, neural nets, big precomputed tables |
| Hands per match | 1,000 | 1,000 |
| Clocks (CPU per bot per match) | **Rapid 30 s** and **Regular 7 min** | **One clock, ~20 min** (proposal; replaces the old "Slow mode" idea) |
| Worst-case match length | ~1 min / ~14 min | ~40 min + startup |
| Startup phase (uncharged) | ~15 s | ~60 s |
| Memory per bot | 512 MB | 2 GB |
| Upload size (code + data) | ~25 MB | ~500 MB |
| Libraries | numpy, scipy, numba, eval7 + stdlib | Everything in Standard, plus phevaluator, scikit-learn, lightgbm, onnxruntime (CPU), OpenSpiel; torch (CPU) on request |
| Solver code | Honour rule: no copied solver libraries | Allowed. Nothing to hide, nothing to enforce |
| Server cost | Cheap | Expensive: limit entries per user per day, maybe gated (e.g. verified account or a minimum Standard rating) |

Notes:
- **Standard bots can enter Open** (the Open image is a superset). Open bots can't enter Standard.
- Separate rating per mode: Standard-Rapid, Standard-Regular, Open.
- Clock budget is sent in `match_start`, so one codebase can scale its search to fit any mode.
- Don't split further at launch (e.g. Open-Rapid). Too many pools thins out matchmaking.
- **Why Open stays at 1,000 hands, not 2,000:** the budget is per match, so 2,000 hands at the same budget halves thinking time per decision, and 2,000 hands at double the budget means ~80-min matches holding ~4 GB of RAM. Glicko-2 also learns more from two 1,000-hand matches (two rating updates, two different opponents) than from one 2,000-hand match. The extra thinking time per decision is what makes Open "beefy", not more hands.
- Per-decision averages assume ~2,000 decisions per bot per match (~4 per hand). **Not measured yet.** Rapid ≈ 15 ms, Regular ≈ 200 ms, Open ≈ 600 ms per decision.
- Standard-Rapid (30 s / 1,000 hands) matches MIT Pokerbots' clock, so ported MIT bots' time management carries over (§3.1).

### 2.1 Library policy

- The image *is* the allow-list. No pip, no network, so nothing else can be installed.
- **No import blocklist.** Stdlib modules (`os`, `subprocess`, `socket`, `ctypes`) stay; the container makes them harmless.
- **Uploads: `.py` files + data files only. Reject compiled code** (`.so`, `.pyd`, wheels). With `/tmp` noexec, bots can't bring native libraries. Open additionally accepts model files (`.onnx`, weights).
- **Can't be enforced technically:** pasted pure-Python library code inside `bot.py`, code hidden in data files and `exec`'d, or `ctypes` tricks. Every competition has this limit; that's why solver bans are honour rules. Enforcement for Standard = code size cap + occasionally reading top leaderboard bots (the code is on the server).
- Open skips: jax, tensorflow (heavy, duplicate onnxruntime), pandas/polars (too slow per decision), anything needing a GPU, network or runtime build.

### 2.2 What real competitions allow (for reference)

| Event | Libraries | Limits |
|---|---|---|
| CMU AI Poker 2025 | Approved set, requests allowed; pretrained models permitted | 1 vCPU, 2 GB, 7 min/agent/match |
| MIT Pokerbots | eval7 expected (engine dependency); official list not verified | 30 s / 1,000 hands, 1 GB |
| Build4Good (MIT fork) | numpy, numba only | 180 s per match |
| IIIT Bangalore Pokerbots | stdlib, NumPy, SciPy only | |
| fullhouse engine event | eval7, numpy, scipy, treys, scikit-learn; requests allowed | 2 s/action, 768 MB, 0.5 CPU |
| HPI | No solver libraries; equity calculators OK; no pondering | 2 vCPU, 8 GB |

## 3. Bot protocol (draft)

```json
// engine → bot, once per match (startup phase runs after this, before the clock starts)
{"type":"match_start","match_id":"m_123","ladder":"standard","mode":"rapid","hands":1000,
 "cpu_budget_ms":30000,"startup_ms":15000,"seat":0}

// bot → engine when initialised (or startup_ms expires → forfeit)
{"ready":true}

// engine → bot, each decision
{"type":"action_request","hand_id":4812,"street":"flop","hole":["Ah","Kd"],
 "board":["7c","2h","Ks"],"pot":120,"to_call":40,"stack":960,"opp_stack":880,
 "legal":["fold","call","raise"],"min_raise":80,"max_raise":960,"time_bank_ms":4200}

// bot → engine (exactly one line)
{"action":"raise","amount":160}
```
Still to define: `hand_result` messages (showdown cards, chip deltas) and `match_end`.

Rejected transports/formats: msgpack/protobuf, sockets, shared memory.

Rules that matter more than the format (all estimates, unmeasured):
- **Flush after every reply** (run Python with `-u`; the MIT shim flushes). Unflushed stdout is the classic "bot hangs" bug.
- Strict alternation: one request, one reply, no async messages.
- Keep messages small, short keys, only what's needed to decide.
- Put a `v` (protocol version) field in `match_start`, and a `seq` number on every `action_request` that the bot echoes back (see §3.0).
- The real per-message cost is the gVisor/pipe round trip (~1-2 ms guess ≈ a few seconds of engine wall-clock per match). The frozen idle bot isn't charged for it. **Measure once the engine runs**; if slow, fix the runtime, not the format.

### 3.0 Message flow as a state machine (proposed)

The engine keeps one small state machine per bot connection, so out-of-order or muddled messages are protocol violations, not ambiguity.

```
 SPAWNED ──send match_start──> STARTING
 STARTING ──{"ready":true}──> IDLE            (startup_ms expires → FORFEIT)
 IDLE ──send action_request──> THINKING       (clock starts, bot unfrozen)
 THINKING ──valid action──> IDLE              (clock stops, bot frozen)
 THINKING ──illegal / garbage / timeout──> IDLE, engine applies fold
 any state ──crash / EOF / OOM──> FORFEIT
 IDLE ──send match_end──> DONE
```

- **Engine speaks first, always.** A bot may only send a line in THINKING (or `ready` in STARTING). Anything else is a violation.
- **One reply per request.** The first line ends THINKING; extra lines are ignored (repeat offenders flagged).
- **Only one bot is ever THINKING.** The other is IDLE and frozen: gives strict alternation and "no pondering" for free.
- **`seq` number on every request, echoed in the reply.** A late reply to an old request (e.g. after a timeout) is discarded instead of being read as the answer to the next one.
- **Stray output is quarantined.** Bot `print()` debug output goes to capped stderr or is ignored; only well-formed JSON lines count.
- **Layers above:** match machine `QUEUED → STARTING_BOTS → RUNNING → SCORING → DONE` (+ `ABORTED`), and a per-hand machine `PREFLOP → FLOP → TURN → RIVER → SHOWDOWN` (or early end on a fold).
- **Implement as data:** a table of `(state, event) → (next_state, action)`, not nested ifs. Easy to test, and the conformance check (`pbb-cli check`) can replay the same table against a bot.

### 3.1 Compatibility with existing bots (proposed)

**There is no universal poker-bot protocol.** What exists:

| Protocol | Who uses it | Format |
|---|---|---|
| **ACPC** | Academic / research bots (Annual Computer Poker Competition, CFR bots) | Text lines over TCP, e.g. `MATCHSTATE:0:30:cc/:9s8h|/8c8d5c` (seat, hand no., betting, cards); bot replies with the state plus its action |
| **MIT Pokerbots** | MIT 6.9630 and forks (Build4Good, IIIT etc.) | MIT's own text protocol over a TCP socket (short clause codes like `T#.###` clock, `P#` seat); changes between years |

**Why MIT bots can't drop in as-is:**
1. **MIT changes the poker variant every year** (2024: auction for an extra card; 2026: 3 hole cards, discard one face up after the flop). A variant bot has no strategy for plain heads-up NLHE, whatever the protocol.
2. **MIT bot authors never touch the protocol.** They subclass a skeleton `Bot` (`handle_new_round`, `get_action(game_state, round_state, active)`, `handle_round_over`) and return `FoldAction` / `CallAction` / `CheckAction` / `RaiseAction(n)`. The `skeleton/` folder does the socket parsing. (Exact names from memory; check against the target year's skeleton.)

**Plan:**
- **Native protocol stays JSON lines** (above). Easier to debug and version than either.
- **Launch: `pbb.compat.mit` skeleton shim.** Same class names, method signatures, state objects and action types as the MIT skeleton, but speaking our JSON over stdin/stdout. A NLHE-capable MIT-style bot (pre-variant year, or adapted) swaps its `skeleton/` folder for ours and uploads. Doubles as the starter kit: a familiar API for new users. ~1 day of work.
- **Later: ACPC adapter**, a per-bot option (`protocol: acpc`). The engine converts JSON ↔ `MATCHSTATE` strings. ACPC bots connect over a socket; `--network=none` containers still have loopback, so a small relay inside the container gives them a localhost port. Nothing leaves the box.
- **Conformance check in the CLI** (`pbb-cli check bot/`): scripted handshake + one hand + match end, so "will my bot work?" is answered before upload.
- Compat layers translate **messages only**. The engine still validates every action, and CPU accounting is unchanged (shim time is charged to the bot, which is fine since it's tiny).

## 4. Sandboxing

Principle: **assume a bot will eventually escape, and make sure that when it does there is nothing worth reaching.** Defence in depth, outside in.

### 4.1 Container (per match)

Each bot gets its own fresh container per match. The container starts once per match, not once per hand. Image and memory depend on the ladder (`bot-python-standard` / `bot-python-open`; 512m / 2g).

```bash
docker run -i --rm --name bot-$MATCH-$SEAT \
  --runtime=runsc --network=none --read-only \
  --tmpfs /tmp:size=16m,noexec \
  --memory=512m --memory-swap=512m --cpus=1 --pids-limit=64 \
  --cap-drop=ALL --security-opt=no-new-privileges --user 65534:65534 \
  -v /srv/bots/$BOT_ID:/bot:ro \
  bot-python-standard:3.12 python -u /bot/main.py
```

- **gVisor (`runsc`)**: system calls go to a user-space kernel, not the host kernel. The most important layer.
- **No network, read-only filesystem, non-root user, all capabilities dropped.**
- **Dependencies are baked into the image.** No `pip install` at runtime. Users can request additions.
- **Thread caps:** set `OMP_NUM_THREADS` / `NUMBA_NUM_THREADS` etc. to 1 so numpy/numba/onnxruntime don't spawn threads they can't use.
- **The idle bot is frozen** while its opponent thinks. Write to the cgroup freezer directly (`cgroup.freeze` = 1/0), because `docker pause` takes tens of ms and adds up to minutes over a match.
- **CPU is measured** as `usage_usec` from the container's `cpu.stat`, read before and after each decision. Startup phase is measured separately and not charged.
- **The engine validates every action.** The sandbox never decides what's legal.
- **Deleted after every match**, so nothing persists between runs.

### 4.2 Upload handling

Treat uploads as data, not code, until they are inside the sandbox.
- Cap upload size per ladder (§2) and file count.
- `.py` + data files only (Open: also model files). Reject compiled binaries.
- Reject archives with symlinks, `..` or absolute paths (zip slip).
- **Never run `setup.py`, `requirements.txt`, or any install/build step.**
- Accept file uploads only, not git URLs (submodules, LFS, hooks).
- Store on the runner read-only, owned by a different user from the one the bot runs as.
- The web server stores files and never executes them.

### 4.3 Narrow channel

stdin/stdout only. The engine treats everything it receives as hostile: cap line length, strict parsing, validate every action (invalid → fold), and cap stderr/log output so a bot can't fill the disk.

### 4.4 Time limits as security

CPU budget, startup cap, per-decision wall-clock cap and a hard kill at match end also stop hangs, sleeps and crypto mining from tying up the box.

### 4.5 Host hardening (runner box)

- Separate machine from the website and database. **Holds no secrets except a narrow queue credential** (and a write-only log-bucket key, §7.4). Wipe and reinstall if compromised.
- Automatic security updates, especially gVisor, Docker and the kernel.
- Firewall: no inbound except SSH (ideally via Tailscale); outbound only to Supabase and the log bucket (R2).
- Never expose the Docker socket; only the runner process gets Docker access (that is effectively root).
- Monitor CPU, disk and outbound traffic. A spike in outbound traffic is the alarm.
- Queue credential is scoped so it can only claim matches and post results, not read user data or touch other tables. The R2 key is scoped to put objects in the match-log bucket only.

### 4.6 What not to rely on

- Code scanning or import blocklists: Python has endless ways round them.
- Python-level sandboxes (RestrictedPython, `exec` with stripped builtins): repeatedly broken.
- Plain Docker without gVisor: every container shares the real kernel, so one kernel bug is an escape.

### 4.7 If a bot does escape: what's at risk

Depends entirely on what is on the machine it lands on.

| Where it lands | What the attacker gets |
|---|---|
| **Harry's laptop / home PC (never do this)** | Everything: files, browser sessions and saved passwords, SSH keys, GitHub tokens, Supabase/Vercel logins, **freelance clients' code, credentials and customer data**, email, ransomware. Plus every other device on the home network |
| **Bare dedicated runner (the plan)** | A compute box: crypto mining, spam/attack traffic from your IP (abuse report, host suspends the account, possible bill); read other users' uploaded bots; tamper with match results and ratings; abuse the queue credential if it's over-scoped |
| **Runner with extra secrets on it (avoid)** | All of the above plus whatever is there: a service-role Supabase key means the whole user database |

Non-technical consequences:
- Harry is the operator: abuse from his server comes back to his name/account (host, ISP).
- If user data leaks, UK GDPR applies and the ICO may need to be told. Collect as little as possible.
- Reputation: one public incident early on could kill trust in the site.

## 5. Stack

**Status: not confirmed.** The web side is settled in practice: Next.js + Supabase + TypeScript, plain monospace CSS. The open choice is the language for the **engine, runner and local CLI**: **Python (recommended for v1)** or **Rust**.

### Language per part (current proposal)

| Part | Language | Notes |
|---|---|---|
| Website pages and server side | TypeScript (Next.js) + CSS | Harry's existing stack. The terminal look is just CSS |
| Database, match queue | SQL (Supabase Postgres) | Queue = table claimed with `FOR UPDATE SKIP LOCKED`, no Redis |
| Match logs / replays | Gzipped files in Cloudflare R2 | One file per match; free egress. See §7.4 |
| Engine, runner, Glicko-2, local CLI | **Python (v1)** or **Rust** | See comparison below |
| Sandbox images, server setup | Dockerfile + Bash | One image per ladder |
| Bot protocol | JSON lines over stdin/stdout | Language-agnostic |
| Compat shims | Python (`pbb.compat.mit`); ACPC adapter later | §3.1 |
| User bots + starter bot | Python at launch, JavaScript next | |
| Live spectating | Runner writes `match_events`; browser subscribes via Supabase Realtime | No custom websocket server |
| Match player (replay + live follow) | TypeScript, client-side | One shared ASCII table component; see §7.5 |
| SSH front end (later, optional) | Go (Charm Wish / Bubble Tea) | Separate small service on the same database |

### Python vs Rust for engine + runner

| | **Python** | **Rust** |
|---|---|---|
| Speed to build | Fastest; easy to change while the design is moving | Slower; every change means fighting the compiler |
| Learning cost | Low | ~3–4× Go. Ownership and async are the hard parts |
| Same language as bots | Yes: bot authors can `pip install` the engine and test locally | No: they'd download a binary (`pbb-cli`) |
| Libraries | Mature: `pokerkit`, `treys` (check they're maintained), a Glicko-2 package, Docker SDK, numpy | Fewer, less battle-tested poker libs; write more yourself |
| Engine bugs | Caught at runtime → needs good tests | Many illegal states can't compile |
| Performance | Slower, but irrelevant: engine time isn't charged to bots and is tiny next to bot think time | Faster, not noticeable |
| Deployment | Python + deps (venv) on the runner box | One static binary |
| Career value | Broad, always useful | Strong for systems/defence, but junior roles are scarce (UK-excl-London sample: ~59% of Rust ads Senior, ~6% Junior) |

**Recommendation (proposed, unconfirmed): Python for v1.** The hard parts are the sandbox, CPU accounting and ratings, not the poker rules, and the protocol will change several times. **Optional later:** once the protocol settles, port the engine to Rust, using the Python engine as a test oracle.

Speed is *not* a reason to pick Rust here. Bot thinking time dominates every match.

If Rust is chosen anyway: keep the runner synchronous (threads + `std::process`) to avoid async Rust at first, and avoid all-Rust.

```
pbb/
├── engine/      # rules, hand eval, duplicate dealing (Python v1)
├── runner/      # Postgres queue → sandboxes → results
├── images/      # Dockerfiles: bot-python-standard, bot-python-open
├── cli/         # local two-bot matches + conformance check for bot authors
├── compat/      # mit/ skeleton shim (launch), acpc/ adapter (later)
└── web/         # Next.js + Supabase
```

Queue claim query:
```sql
update matches set status = 'running', runner_id = $1, started_at = now()
where id = (
  select id from matches where status = 'queued'
  order by created_at for update skip locked limit 1
) returning *;
```

### Other alternatives considered
- **B. Go everywhere** (Go + htmx + Postgres): obvious pick *if* an SSH front end is wanted. Costs learning a new language.
- **C. Laravel + MySQL:** Harry's coursework stack, but live spectating takes more work.
- **D. Elixir/Phoenix LiveView:** best fit for real-time spectating, steepest learning curve.

**On the terminal look:** it's just CSS. SSH is an *additional* front end, not a replacement.

## 6. Infrastructure

Only one bot per match runs at any moment, so each match uses about 1 core. **Memory is the tighter limit**, because both bots stay resident: a Standard match needs up to ~1 GB, an Open match up to ~4 GB.

| Box | Example mix |
|---|---|
| 2 cores / 4 GB | 2 Standard matches, no Open |
| 4 cores / 8 GB | 4 Standard, or 1 Open + 2 Standard |
| 8 cores / 16 GB | 8 Standard, or 2 Open + 4 Standard |

- The runner should claim matches by available memory, not just a fixed slot count (or run separate Standard and Open worker slots).
- **Dev / private beta:** a spare machine or throwaway VM that holds nothing personal. Not the main laptop (see §4.7).
- **Public launch:** a **dedicated server** (e.g. a Hetzner auction box), not shared vCPUs. Hetzner dedicated-vCPU cloud prices rose about 169% in June 2026 (CCX13: €15.99 → €42.99/mo); auction prices rose only about 3%.
- **Web/DB:** Vercel + Supabase free tiers, off the runner box. Supabase free = 500 MB database, 1 GB file storage, 5 GB egress; free projects pause after a week of inactivity. Pro ($25/mo) = 8 GB database, 100 GB files.
- **Match logs:** Cloudflare R2. Free tier = 10 GB storage, 1M writes, 10M reads per month, free egress; then $0.015/GB-month.

## 7. UI

Monospace font, black and white, ASCII cards (`[A♠][K♦]`). Sparklines and bars use block characters (`▁▂▃▄▅▆▇█`, `█░`) so everything stays text. Leaderboards per ladder and mode. Stretch goal: an SSH front end (`ssh play.<domain>`).

### 7.1 Live match view (proposed)

The page answers three questions: **am I winning (and is it luck)? am I running out of clock? why?**

```
 pbb ── m_123 ── standard/rapid ── hand 412/1000
 ───────────────────────────────────────────────
 tightbot_v3 (1612)   vs   shove_mcgee (1588)

 RESULT  +3.2 bb/100  ±9.1 (95%)  not significant
 chips   ▁▂▂▃▅▄▅▆▆▇▆▇█  +1,310
 skill   ▁▁▂▂▃▃▃▄▄▄▅▅▅  +  840  (duplicate-adj.)

 CLOCK   you [██████████░░░░░░░░░░] 14.2 / 30s
         opp [████████████████░░░░] 23.9 / 30s
         you're 8% ahead of pace

 THINK   ms/decision  pre 3  flop 11  turn 19  riv 24

 STYLE          you    opp
 vpip           54%    91%
 pfr            41%    88%
 aggression     2.1    6.4
 fold to raise  38%    12%
 showdown won   57%    44%

 NOW  #412 · flop · pot 120
   you [A♠][K♦]  board [7♣][2♥][K♠]  opp [9♦][9♣]
   > opp raises 160 … you thinking (4 ms)

 BIG POTS  #88 -940  #203 +1,200  #377 +610  [replay]
```

| Panel | Shows | Why |
|---|---|---|
| Result | bb/100 with 95% confidence interval, "significant / not significant" in words | 1,000 hands is noisy; stops overreacting to one bad run |
| Chips vs skill lines | Raw cumulative chips, plus a duplicate-adjusted line (sum of both seats per deal) | Standout feature: duplicate dealing cancels out card luck, so show it |
| Clock | CPU used vs budget for both bots, plus pace = (hands played ÷ 1,000) × budget | Makes the efficiency game visible; ahead/behind pace beats the raw number |
| Think time | Average ms per decision by street (owner also gets a histogram) | Shows where the budget goes and spots spikes |
| Style HUD | VPIP, PFR, aggression factor, fold to raise, showdown win % | Standard poker-tracker stats that poker players read instantly |
| Now | Current hand, all hole cards, last action | |
| Big pots | Largest swings, link to replay | |

### 7.2 Post-match

- **Duplicate diff view:** pick a deal, show both bots' lines on the same cards side by side, highlight the point where they split ("you folded the turn, they called and won 600"). Best learning tool on the site.
- Hand list with filters (biggest losses, all-ins, timeouts) → ASCII replay as a scrolling hand history.
- **Owner-only panel:** capped stderr log, CPU per decision, counts of timeouts and invalid actions turned into folds.

### 7.3 Practical notes

- **Show all hole cards live.** Bots have no network, so nothing can leak back to them.
- **Rapid is too fast to watch** (~16 hands/s if bots use their full budget). Live view shows totals plus the current hand; watching "like a real match" is the paced player in §7.5.
- **Runner writes one `match_events` row per hand** (not per action), plus a stats snapshot every ~25 hands. Comfortably within Supabase Realtime.
- **Mobile:** stack panels vertically. The mockup is ~48 characters wide.
- **Featured "TV" match** on the homepage (like Lichess TV): pick the highest-rated live match, the closest one, or a big upset. A metric decides what's *featured*, never what's *kept*.

### 7.4 Match storage (proposed)

**Save every match.** Storage is only a problem if hand logs go into Postgres as rows.

| Item | Size | Where |
|---|---|---|
| Hand log (compact one-line-per-hand text, ACPC-style: actions, cards, chip delta, CPU per decision) | ~100 B/hand → ~100 KB raw → **~25–30 KB gzipped per match** | One file per match in R2, e.g. `logs/<match_id>.txt.gz` |
| Match summary (bots, result, rating change, final stats snapshot, log key) | ~1–2 KB | One Postgres row per match |
| Live `match_events` | Per hand during the match | Postgres, **deleted** once the runner uploads the log at match end |

Rough scale at 1,000 matches/day: logs ~30 MB/day ≈ 11 GB/year (≈ R2 free tier; 100 GB ≈ $1.50/mo). Summaries ~1–2 MB/day, which fills Supabase's free 500 MB in about a year (by then on Pro anyway).

- **Don't:** store one Postgres row per action. ~4,000 rows/match with indexes ≈ 0.5 MB/match, so one busy day would fill the free tier.
- **Retention:** keep summary rows forever (rating history needs them). Keep every log for now. If it ever matters, prune logs older than 6 months for unstarred, low-rated matches.
- **Later, if needed:** store the deal seed + actions only and regenerate cards on replay. Not worth it for v1; gzip is enough.
- Browser fetches the log file directly from R2 (public-read or signed URL) and renders the replay/diff client-side.

### 7.5 Watching a match like a real match (proposed)

**Core idea: decouple the match from the viewing.** The match runs at full speed with the compute limits unchanged. The site is a *player* that plays the hand log back at human pace. "Live" is the same player following the newest hand a few seconds behind.

**Why not pace the match itself:** the runner would hold both containers (up to ~4 GB for Open) for hours for nothing. CPU budgets are CPU time and the idle bot is frozen, so pausing wouldn't break fairness, but the box is the scarce resource.

**How long a match takes (worst case, bots use their full budget; not measured):** Rapid ~1 min, Regular ~14 min, Open ~40 min. At 1,000 hands, Open is about 2.4 s/hand, so **only Open is naturally watchable in real time**. Rapid and Regular finish faster than a human can follow; "live" on those means jumping to the latest hand or watching a recording.

| # | Mode | What it is | Cost |
|---|---|---|---|
| 1 | **Replay player** (build first) | Plays the saved log with play/pause, seek by hand, speed control | Front-end only; the log exists anyway |
| 2 | **Live follow** | Same player in tail mode, a few seconds behind the match. If the match outruns the viewer, jump to the latest hand rather than lag | Realtime events |
| 3 | **Smart pacing** | Hold time per hand depends on what happened: preflop fold ~0.3 s, big all-in showdown ~6 s. Many heads-up hands end preflop, so a match takes minutes, not an hour. Speed buttons (1x / 5x / 20x) on top | Client-side rule |
| 4 | **Real think time on screen** | Each bot shows a bar for its actual CPU time on each decision, so the clock visibly drains | Log already has CPU per decision |
| 5 | **Highlights mode** | Auto-play only all-ins, biggest pots, showdowns and the deals where the two seats' play diverged most | Client-side filter |
| 6 | **Premiere broadcasts** | Run a featured match (top-rated, upset) ahead of time, then broadcast it at a scheduled time at paced speed, like Lichess TV | Precomputed, so no sandbox tied up |
| 7 | **Match wall** | Grid of mini tables, each with a chip sparkline and current hand; click one to open the full table | Per-hand events for many matches |

**Recommendation:** build 1 + 3 + 4 as one player, add live follow (2) as tail mode of the same player, and leave 6 and 7 until after launch.

**Table rendering** (text/CSS, same component for replay and live):
```
 shove_mcgee            1,040  [D]
 [??][??]               CPU 23.9/30s

      [7♣][2♥][K♠][ ? ][ ? ]   pot 440

 tightbot_v3              960
 [A♠][K♦]               CPU 14.2/30s
 > opp raises 160 … thinking ▓▓░

 hand 412/1000  ◀◀ ▶ ▶▶ 5x [smart pace]
```

**Technical notes:**
- The player is a pure function of the event list plus a clock: state at hand *i*, street *s*, action *a*. Seek, speed and pause are just changes to the clock.
- **R2 objects can't be appended to**, so live matches stream per-hand events over Realtime. The page switches to the final log file once it's uploaded and `match_events` rows are deleted.
- Hold times and speeds are client-side settings, not stored on the server.
- Showing the opponent's hole cards is fine (see §7.3).

## 8. Build order

1. Engine + local CLI that plays two bot files against each other (writes the §7.4 log format from day one)
2. Sandbox runner with CPU accounting, startup phase and the cgroup freezer (Standard image first)
3. Uploads, queue, Glicko-2, log upload to R2
4. Leaderboard, lobbies, **match player** (§7.5: replay, smart pacing, think-time bars), then live follow and the live stats view (§7.1)
5. Starter kit: example bot, local test harness (`pbb-cli`) **with conformance check**, protocol docs, **MIT-style skeleton shim** (§3.1)
6. Open ladder: second image, memory-aware scheduling, entry limits
7. After launch: premiere broadcasts and match wall (§7.5); ACPC adapter (§3.1)

_The concrete MVP cut of steps 1–4 lives in `docs/mvp-build-plan.md`._

## 9. Open questions

- [ ] Confirm the engine/runner language: Python (recommended for v1) or Rust.
- [ ] Open ladder: exact clock (~20 min proposed), upload cap, and whether it's gated (verified account / minimum Standard rating).
- [ ] Is OpenSpiel definitely allowed in Open? (Proposed yes.)
- [ ] Measure real decisions per hand and ms per decision once the engine runs.
- [ ] Exact Rapid/Regular/Open budgets and startup windows after testing.
- [ ] Multi-way tables ever, or heads-up only for good?
- [ ] Free-tier limits: matches per user per day, per ladder and mode.
- [ ] `hand_result` / `match_end` message formats (need chip deltas, showdown cards and per-decision CPU to feed §7).
- [ ] Exact scope of the runner's Supabase credential (claim matches + post results only) and R2 key (put-only on log bucket).
- [ ] Where the dev/beta runner lives (spare machine vs cloud VM) so nothing personal is on it.
- [ ] Match view: compute stats in the runner (snapshots) or in the browser from per-hand rows? (Leaning runner.) Which result unit: bb/100 or mbb/hand (ACPC style)?
- [ ] Exact hand-log line format (ACPC `STATE:` style or own). Measure real gzipped size per match.
- [ ] Replays public to everyone, or only to the two bot owners? (Default proposal: public.)
- [ ] Smart-pacing rule: exact hold times per hand type and default speed. Tune by watching real matches once logs exist.
- [ ] Live follow delay (a few seconds proposed) and whether live viewers see a "broadcast delay" label.
- [ ] Premiere broadcasts: how matches get picked and scheduled, and whether to add chat or commentary (post-launch).
- [ ] Compat (§3.1): which MIT year's skeleton API to mirror (check exact class/method names), and whether the ACPC adapter is worth building at all.
- [ ] Pondering: keep banned (v1 plan), or offer a later mode that allows it (charged CPU, core cap)? Also check whether MIT/ACPC engines actually prevent background computation (not verified).
- [x] ~~Save all matches or only some?~~ → Save all; logs in R2, summaries in Postgres (§7.4).
- [x] ~~Memory cap 256 vs 512 MB~~ → 512 MB Standard, 2 GB Open.
- [x] ~~Open: 1,000 or 2,000 hands?~~ → 1,000. More matches, not longer ones.

## Sources

- [2006 AAAI Computer Poker Competition (1,000-hand duplicate matches)](https://www.martin.zinkevich.org/publications/competition.pdf)
- [ACPC server README](https://www.github.com/crissilvaeng/acpc-server)
- [ACPC MATCHSTATE example (computer-poker group)](https://groups.google.com/g/computer-poker/c/bEXkR2cxNFc)
- [MIT Pokerbots 2024 (30 s / 1,000 hands, 1 GB RAM; engine socket encoding)](https://github.com/gtowizard-ai/mitpoker-2024)
- [MIT Pokerbots engine 2026 (3 hole cards, discard after flop; Python/Java/C++ skeletons)](https://gh.r-mj.com/mitpokerbots/engine-2026)
- [CMU AI Poker Tournament 2025 (1 vCPU, 2 GB, 7 min / match, approved libraries)](https://cmudsc.netlify.app/archive/pokerai-2025)
- [CMU AI Poker 2025 opening slides (pretrained models permitted)](https://docs.google.com/presentation/d/14iDHopipj4dRjjb_u8xQQNbWMWBLnH8NmquFvaIE6qI/htmlpresent)
- [Build4Good Pokerbots (numpy/numba only)](https://gh.r-mj.com/pranjol11/Build4Good-Pokerbots)
- [fullhouse engine (library list, no compiled uploads)](https://github.com/uzlez/fullhouse-engine)
- [HPI poker rules (no solver libraries, no pondering)](https://hpi-poker.notion.site/Event-Rules-Submissions-173bcdee7a5e804b83daef756176f7a2)
- [IIIT Bangalore Pokerbots (stdlib, NumPy, SciPy)](https://www.startupgrantsindia.com/events/pokerbots)
- [Hetzner June 2026 price changes](https://byteiota.com/?p=16629)
- [ITJobsWatch: Rust jobs in the UK excluding London](https://www.itjobswatch.co.uk/jobs/uk%20excluding%20london/rust.do?p=6)
- [Supabase free tier limits 2026 (500 MB DB, 1 GB files, 5 GB egress, pause after a week)](https://automationatlas.io/answers/supabase-free-tier-limits-2026/)
- [Cloudflare R2 pricing 2026 (10 GB free, $0.015/GB-month, free egress)](https://upstash.com/kb/cloudflare-r2-pricing-in-2026-storage-operations-and-real-monthly-bills)
