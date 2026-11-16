# OpenPair

**Developer-first AI routing with Pair, a local avatar interface**  
**Documentation revision:** 17 November 2026  
**Codebase status:** `v0.1.0` declared in `pyproject.toml`; Pair UI is a **proposed next-generation feature, not yet released**.  
**Repository:** https://github.com/Pharadee1112/Openpair  
**Primary users:** Developers running their own language models on personal workstations.

> **Project abstract — proposed local-first release**  
> OpenPair is a Python/Rust AI-routing toolkit being extended into a developer-first, local-first interaction environment. Its next interface will introduce **Pair**, an original pixel-art avatar inside a retro terminal-style web UI launched from the command line. Developers will connect models already running on their machines through Ollama, LM Studio, or configurable OpenAI-compatible local endpoints, use a code-friendly multi-turn chat, and inspect routing and fallback events without surrendering control of model execution. The project preserves OpenPair's existing Rust classification, Python client, CLI, benchmark infrastructure, and cloud-provider compatibility, while making **local models the default within the new UI**. Pair is an interface companion, not another AI model or autonomous coding agent. The goal is transparent, low-friction developer interaction with minimal extra resource use.

**Read this first:** This README combines a verified inventory of the existing `master` branch (audited 17 November 2026) with an implementation specification for future releases. Status labels mean **Implemented**, **Partial**, **Planned**, or **Verify**. A planned command or API is not available today. Source inspection is not a substitute for running tests on your target platform.

## 1. Product boundaries and design principles

### The product is

- A developer-focused interface for using developer-owned or developer-operated AI models.
- A local web experience **started from the terminal**, initially with the proposed command `openpair ui`. The interface runs in a browser at `127.0.0.1`; it is **not** a native terminal drawing engine.
- A continuation of the current Python package and Rust routing core; not a rewrite.
- Transparent about the selected model, endpoint, reason for selection, response status, and fallback.
- A friendly but unobtrusive pixel-avatar experience with an original character named **Pair**.

### The product is not (initial scope)

- A consumer chatbot, hosted SaaS product, or managed model marketplace.
- An autonomous agent that reads files, edits repositories, runs shell commands, or executes generated code.
- A replacement for Ollama, LM Studio, or another model runtime.
- An AI safety/dark-pattern detector. AI Watchdog inspires **status communication**, not detection functionality.
- A promise that a local model is automatically private if its underlying runtime sends data elsewhere; the UI will disclose the actual endpoint and enforce local-only defaults.

**Non-negotiable UX rule:** The UI must **never silently send a request to a cloud provider** after the developer has selected local-only mode. A failed local model must surface an error or request explicit permission to use a remote endpoint.

## 2. What the existing project has already built

The following is based on code and docs visible on `master`; it does **not** claim the new interface or production packaging is complete.

| Area | Status | Evidence and current behavior |
|---|---|---|
| Rust complexity classifier (1–10) | **Implemented** | `src/classifier.rs`, exposed through `src/lib.rs` |
| Thai-language detection and routing preference | **Implemented** | `src/classifier.rs`, `src/registry.rs`, `src/router.rs` |
| Static Gemini/Groq model registry and tier selection | **Implemented** | `src/registry.rs`; current registry models are coded, not discovered dynamically |
| Python/Rust bridge via PyO3 and maturin | **Implemented** | `Cargo.toml`, `pyproject.toml`, `src/lib.rs` |
| Python public API: `OpenPair.route()` and `OpenPair.call()` | **Implemented** | `python/openpair/client.py` |
| Real provider callers, error handling, and cloud fallback | **Implemented** | `caller.py`, `client.py`, `errors.py`; registered defaults primarily use Gemini/Groq |
| Local Ollama request path | **Partial for new vision** | Local `call_ollama()` and fallback exist; Ollama is currently appended **last**, not a general selectable model catalog |
| Per-instance exact-request LRU response cache | **Implemented** | `python/openpair/client.py`; callers can disable with `use_cache=False` |
| One-shot CLI command `openpair "prompt"` | **Implemented** | `python/openpair/cli.py`; `--route-only`, `--provider`, `--system`, `--max-tokens` |
| Thai-language benchmark + checkpoint/resume | **Implemented** | `run_benchmark.py`, `python/openpair/benchmark/`, benchmark result files |
| Automated Rust/Python test suites and CI definition | **Implemented/configured** | `src/` tests, `tests/`, `.github/workflows/ci.yml`; passing state must be checked in GitHub Actions |
| Dynamic discovery of installed local models | **Planned** | No runtime-independent discovery/registry in current Python client |
| Multi-turn local chat sessions and token streaming | **Planned** | Current `OpenPair.call()` makes one request and returns a full result |
| Pair avatar, local browser UI, and `openpair ui` | **Planned** | No `ui` package, Flask app, or `ui` subcommand in the current tree |
| Local-only policy / selectable local-first routing | **Planned** | Existing routing chooses from the static cloud registry first |
| Versioned GitHub releases / PyPI release process | **Verify** | Package version `0.1.0` is declared; tags, publishing history, and released wheels must be checked separately |

**Critical technical nuance:** Current `OpenPair.call()` first asks the Rust registry for a Gemini/Groq model and may then fall back to Ollama. **Do not expose that call unchanged behind a UI labeled “local only.”** Introduce an explicit execution policy and local adapter path before the UI is connected to real user prompts.

### Current architecture (as implemented)

```text
One-shot CLI / Python caller
          |
          v
python/openpair/client.py   [routing, cache, fallback]
          |
          +--> PyO3 / maturin --> Rust classifier + registry + router
          |
          +--> python/openpair/caller.py
                       |--> Gemini / Groq (registered cloud candidates)
                       |--> Other provider callers (present, not all registered)
                       `--> Ollama (last-resort local fallback)
```

### Current repository map

| Path | Responsibility |
|---|---|
| `src/classifier.rs` | Prompt complexity scoring; Thai detection |
| `src/registry.rs` | Compiled model metadata, tiers, prices, Thai priority |
| `src/router.rs` | Pure Rust routing decisions |
| `src/lib.rs` | PyO3 exports for Python |
| `python/openpair/client.py` | Python client, routing, fallback, LRU cache |
| `python/openpair/caller.py` | Provider-specific request dispatch and latency |
| `python/openpair/config.py` | Environment API keys and Ollama settings |
| `python/openpair/cli.py` | Current single-prompt command-line interface |
| `python/openpair/benchmark/` | Benchmark cases, checkpoint logic |
| `run_benchmark.py` | Benchmark runner |
| `tests/` | Mocked and live Python tests |
| `.github/workflows/ci.yml` | Rust and non-live Python CI jobs |
| `paper/`, `hf_dataset/` | Research drafts and reproducibility materials |

The historical `ARCHITECTURE.md` and SRD document may describe future features as gaps or older states; use **code and tests** to settle a conflict. Update historical architecture notes when implementing a phase; do not delete benchmark or research artifacts.

### Known integration risks for the next developer

- **Ollama configuration consistency:** `ApiKeys` stores a configurable Ollama base URL, but `call_ollama()` reads `OLLAMA_BASE_URL` directly from the environment. Unify these paths before supporting configurable runtimes.
- **SDK dependency audit:** `caller.py` imports the `google.genai` API, while `pyproject.toml` declares `google-generativeai`; verify and align the actual required distribution in a clean environment.
- **Cache and conversation scope:** The present exact-request LRU cache is keyed on one prompt/provider/system/max-tokens tuple. Do not reuse it for multi-turn or multiple local endpoints without including complete context, model identity, runtime, and privacy scope; disabling it in chat mode is a safe first step.
- **Pinned local model:** The Rust registry does not contain Ollama model IDs. Passing `preferred_provider="ollama"` to today's `route()` is **not** equivalent to choosing an exact local model. The new adapter and policy layer must enforce selection independently of that static registry.
- **Build verification:** The declared package version and a configured CI workflow are evidence of code structure, not proof that current GitHub Releases exist or that the latest CI run succeeded. Confirm before issuing a release.

## 3. Current installation and commands (working baseline)

**Requirements:** Python 3.9+ (declared in `pyproject.toml`), Rust toolchain, and pip/maturin. Use a newer supported Python where practical; CI currently targets Python 3.12 on Ubuntu.

```bash
git clone https://github.com/Pharadee1112/Openpair.git
cd Openpair
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install maturin
maturin develop --release
python -m pip install -e ".[dev]"
```

After editing `src/*.rs`, rebuild the importable extension with `maturin develop --release` before testing Python behavior. Keep `.env` out of source control.

**Current CLI examples (available today):**

```bash
openpair "Explain recursion" --route-only
openpair "Explain recursion"             # real provider call; requires configured provider or local Ollama
openpair "สรุปให้อ่านง่าย" --provider groq
openpair "Hello" --system "Keep it concise" --max-tokens 512
```

**Current API examples (available today):**

```python
from openpair import OpenPair
client = OpenPair()
decision = client.route("Explain recursion")    # no API request
result = client.call("Explain recursion")       # returns complete answer
print(result.response_text, result.model_name, result.provider)
```

For cloud calls, configure applicable keys in `.env` / environment variables such as `GOOGLE_API_KEY` or `GROQ_API_KEY`. For the **existing** Ollama fallback, `OLLAMA_BASE_URL` defaults to `http://localhost:11434` and `OLLAMA_MODEL` defaults to `llama3.1`; ensure the model exists on the developer machine. These baseline instructions are not the proposed local-first onboarding flow.

**Current test commands:**

```bash
cargo test
pytest -m "not live"               # recommended: mocked/non-live Python suite
# Live tests make actual provider requests; run only intentionally:
pytest tests/test_live.py -m live
python run_benchmark.py --suite core
```

The full Thai suite has **600 cases per model**, supports checkpoint/resume, and can exhaust free quotas. Preserve benchmarking as an independent workflow; do not run live benchmarks in every CI job.

## 4. Target developer experience and user flow

### Primary flow: first launch with a local model

```text
Developer installs OpenPair + optional UI dependencies
  -> starts an Ollama/LM Studio model server separately
  -> enters `openpair ui`                 [PLANNED]
  -> local web app binds to 127.0.0.1
  -> browser opens to OpenPair / Pair
  -> app probes allowed local runtimes
     -> no runtime: show setup instructions + Retry (never invent models)
     -> runtime found: enumerate actual installed / available model IDs
  -> developer selects a model or later opts into Auto Local
  -> enters a prompt, including code blocks
  -> policy gate confirms local endpoint + chosen model
  -> model adapter sends request and exposes real progress
  -> Pair changes state based on adapter events
  -> response renders as safe Markdown/code, with copy action
  -> metadata shows provider, model, latency, tokens (when available)
  -> developer continues chat; session stays on this machine
```

### Returning developer flow

1. Run `openpair ui` again; optionally reuse local preferences **without storing API secrets in browser storage**.
2. Recheck the runtime/model on launch; a previously selected model may be unloaded or deleted.
3. Default to last valid local model, with a visible model switcher.
4. Let developers pin a model; do not override their pin with auto-routing.
5. If a local request fails, show a short explanation and an explicit **Retry / Choose model** action.

### Error and edge-case flow

- **No installed model:** display instructions for the detected runtime; never silently download multi-GB weights.
- **Server offline:** indicate unavailable state; keep the conversation view intact, and offer Retry.
- **No local endpoint available:** don't send to Gemini/Groq because cloud keys happen to exist.
- **Model unloaded/rate-limited/slow:** show the actual status; permit an *opt-in* fallback to another discovered local model.
- **Unsafe HTML in model response:** render text as escaped content or sanitised Markdown; never inject raw model/user text with `innerHTML`.
- **Long code output:** stream or render in chunks; syntax highlighting and copy should not corrupt indentation.
- **Ctrl+C / close server:** terminate gracefully and remove temporary resources.

### UX acceptance criteria

- A developer completes a first local prompt without a cloud API key.
- The UI always names the model actually called, not merely the planned route.
- User can switch models, copy code, and read errors without leaving the app.
- No mandatory mascot sounds, forced typing delay, or hidden background downloads.
- The original one-shot `openpair "prompt"` remains scriptable and pipes cleanly to stdout.

## 5. Pair: avatar behavior and interface specification

**Canonical name:** **Pair**. Pair is an **original** pixel-art companion and the visual identity for the developer interface, not a copied AI Watchdog dog or Avatar UI Core's Spectra artwork. Personality: curious, precise, warm, and concise. Its job is to communicate the truth about the system state, not to pretend it has emotions, authority, or additional reasoning power.

### Reference UI and layout

Inspiration: [Avatar UI Core](https://github.com/sito-sikino/avatar-ui-core). Borrow the **retro monochrome terminal aesthetic, two-dimensional avatar area, lightweight mouth/typing states, and modular frontend structure**; keep the final mascot artwork, iconography, copy, and brand original.

```text
+-------------------------------------------------------------------+
| OPENPAIR  |  LOCAL  |  MODEL: <actual-model-id>   [Settings] [Help] |
+-----------------------------------------------+-------------------+
| Developer / Pair conversation                 |  PAIR             |
|  USER> Review this Rust function...           |  [pixel avatar]   |
|  PAIR> Here are two issues...                 |  state: speaking  |
|  ```rust ... ```  [Copy]                      |  endpoint: local  |
|                                               |  details (toggle) |
+-----------------------------------------------+-------------------+
| > Message Pair...                                         [Send]   |
+-------------------------------------------------------------------+
| Runtime: Ollama  |  Actual model  |  Latency  |  Token usage*       |
+-------------------------------------------------------------------+
* Only if runtime reports a trustworthy value. No invented telemetry.
```

### Avatar state contract

| State / event | Pair behavior | What the label must mean |
|---|---|---|
| `idle` | Gentle idle blink | Ready to receive a prompt |
| `connecting` | Looking around / small pulse | Checking configured local server |
| `routing` | Thoughtful expression | Choosing a model; do not imply inference began |
| `generating` | Subtle speaking animation | Real generation/streaming in progress |
| `done` | Small happy acknowledgement | Full response completed successfully |
| `fallback` | Brief surprised reaction | Actual local model switch, with explanatory text |
| `error` | Concerned expression | Request failed or runtime disconnected |

Transitions must come from backend status/events, **not fixed animation timers that simulate success**. Pair never invents progress percentages. Honor reduced-motion preferences; sounds **off by default**. Typewriter animation may be used for short status phrases but **not** for arbitrarily delaying model answers or code.

### UI behavior rules

- Keyboard first: Enter to send, Shift+Enter for newline; support code paste.
- Display exact model ID, local/remote scope, and runtime status at all times.
- Provide clear neutral states when no server is connected or token metrics are absent.
- Preserve Markdown/code block formatting with safe rendering, copy buttons, and readable wrapping.
- Keep the mascot unobtrusive; on narrow screens, collapse it rather than shrinking code readability.
- Use local/static UI assets wherever possible; do not require third-party font or asset requests for offline use.

## 6. Target technical architecture and stack

### Build on what exists

| Layer | Current / intended technology | Decision |
|---|---|---|
| Routing core | Rust + PyO3 / maturin | **Keep**; provide capabilities/registry integration points rather than rewriting routing |
| Public API & model orchestration | Python 3.9+ | **Extend** with explicit local-only execution policy, discovery, structured events, multi-turn messages |
| Local model adapters | OpenAI-compatible Chat Completions API, OpenAI Python SDK | **Add** small adapter interface; start with Ollama and LM Studio |
| Local web server | Flask (optional dependency) | **Add** to package, loopback only; production-safe local serving without debug console |
| Frontend | Vanilla ES modules, HTML, CSS | **Add/adapt** from avatar-ui-core; avoid React unless clear requirements justify it |
| Avatar animation | Original pixel PNG/WebP, CSS/JS state machine | **Add** small sprite set; animations are only a display of events |
| Streaming | SSE or fetch streaming on same-origin localhost | **Add** after basic request path works; preserve backpressure/cancel behavior |
| Session state | In-memory per browser session for MVP | **Add**; no database or account system required |
| Settings | Environment variables + local config with safe defaults | **Extend**; keep secrets server-side, validate endpoint URLs |
| Testing | pytest, Rust unit tests, GitHub Actions | **Extend** fixtures for model adapters/UI and smoke tests |
| Packaging | `pyproject.toml`, optional `ui` extra, single CLI entry point | **Extend** without increasing baseline CLI dependencies |

**Standard local endpoints (examples, not guaranteed active):**

```text
Ollama:     http://127.0.0.1:11434/v1   (models discovery: GET /api/tags)
LM Studio:  http://127.0.0.1:1234/v1    (models discovery: GET /v1/models)
Custom:     explicit developer-supplied OpenAI-compatible /v1 base URL
```

Verify a server is reachable, model list is non-empty, and the selected model ID actually exists. Do **not** assume that every local model supports tool calling, streaming usage counters, vision, or a particular context length.

### Planned architecture

```text
`openpair ui` (proposed subcommand)
        |
        v
Local Flask app on 127.0.0.1 + browser frontend
        |                       |
        |                       `--> Pair state UI / code chat / user settings
        v
Execution policy: LOCAL_ONLY by default for UI
        |
        +--> Runtime discovery + endpoint validator
        |          |--> Ollama adapter
        |          |--> LM Studio adapter
        |          `--> Custom OpenAI-compatible adapter (explicitly enabled)
        |
        +--> Local model selection / optional auto-local routing
        |          `--> Existing Rust complexity scorer / future model metadata
        |
        `--> Session / stream / status events --> UI + Pair avatar

Existing one-shot CLI + cloud routing remain available as before.
```

### Suggested additive structure (not present today)

```text
python/openpair/
  local/
    discovery.py       # enumerate and probe only allowed endpoints
    adapters.py        # local chat adapters, capability and error normalization
    policy.py          # enforce LOCAL_ONLY and opt-in remote scope
    models.py          # dynamic model metadata (unknown is allowed)
  ui/
    server.py          # localhost Flask app; safe lifecycle
    api.py             # REST + stream endpoints, request validation
    sessions.py        # in-memory conversation state
    templates/index.html
    static/css/app.css
    static/js/app.js
    static/js/chat.js
    static/js/pair.js
    static/img/pair/   # original licensed pixel assets
  events.py            # typed event definitions for UI status
  cli.py               # preserve current syntax; add `ui` subcommand
```

A shared adapter should accept a list of conversation messages and a selected model, not only a single concatenated prompt. Avoid global shared chat state. Server must support cancellation, explicit timeouts, bounded concurrent requests, and sanitized errors.

### Proposed API contract (illustrative; NOT implemented)

```http
GET  /api/health             -> {"status":"ok", "mode":"local"}
GET  /api/runtimes           -> [{"id":"ollama", "status":"online", ...}]
GET  /api/models             -> [{"id":"...", "runtime":"ollama", ...}]
POST /api/chat               -> {"session_id":"...", "model_id":"...", "message":"..."}
POST /api/chat/stream        -> streamed message / state events
POST /api/chat/cancel        -> cancel the request in this session
```

Prefer documented structured event envelopes, e.g. `connected`, `routing`, `model_selected`, `generating`, `token`, `fallback`, `completed`, `failed`. The UI must not use raw exception strings or API keys as user-visible output. Keep health/model discovery read-only; mutation endpoints require same-origin and CSRF considerations even when bound to localhost.

## 7. Phased implementation plan and release targets

**Release policy:** Ship incrementally, after each phase passes its acceptance tests. Versions below are **proposed future targets**, not claims that tags or releases already exist. A single phase may require multiple pre-release builds.

### Phase 0 — Existing baseline / `0.1.0` (code present; verify green CI)

**Already implemented:** Rust scorer and registry; Python API and CLI; cloud provider calls with fallback; Ollama as last-resort fallback; Thai benchmark and checkpointing; tests and CI workflow definition.

**Handoff actions before changing code:**

- [ ] Run `cargo test` and `pytest -m "not live"` on a clean clone; record exact results.
- [ ] Confirm `openpair --version`, installation build, current branch and GitHub release/tag history.
- [ ] Confirm runtime behavior with a reachable Ollama server and an actually installed local model.
- [ ] Create a short decision log recording local-first policy and “browser launched from CLI” scope.
- [ ] Confirm project licensing and proper attribution before copying UI source or assets.

**Exit gate:** Baseline results documented; no unreviewed changes to current public CLI behavior.

### Phase 1 — Local runtime foundation / target `0.2.0`

**Goal:** A local-model request path with zero required cloud keys.

**Build:** Runtime discovery, Ollama adapter, explicit local-only execution policy, model selection with exact IDs, endpoint allowlist/validation, clear error mapping. Add LM Studio as the second adapter if the Ollama path is stable.

**Acceptance tests:**

- [ ] With cloud keys unset, a selected installed Ollama model returns a real response.
- [ ] `LOCAL_ONLY` rejects non-loopback endpoints unless developer explicitly overrides the policy.
- [ ] A missing runtime or model gives a useful error and does not call any cloud SDK.
- [ ] Runtime and adapter tests are fully mocked in CI; one optional, manual real-Ollama smoke test is documented.
- [ ] Existing `OpenPair.call()` remains backward compatible unless a documented change is approved.

**Release:** `v0.2.0-alpha.1` for development review, then `v0.2.0` after acceptance.

### Phase 2 — Pair visual foundation / target `0.3.0`

**Goal:** Launchable local browser UI and recognizable Pair identity.

**Build:** Optional `ui` package dependencies, `openpair ui`, Flask app, retro layout, chat input, original Pair sprite states, asset packaging, safe defaults, and mocked UI state tests. Start with static/mocked responses before connecting the UI to the Phase 1 adapter.

**Acceptance tests:**

- [ ] `openpair ui` starts a server bound to `127.0.0.1` and launches or prints the local URL.
- [ ] Debugger is disabled; UI still loads with no model server running.
- [ ] Pair displays `idle`, `connecting`, `generating`, `done`, and `error` from state events.
- [ ] Copyable code blocks, keyboard support, and reduced-motion preference work.
- [ ] No external fonts/assets are required for first launch.

**Release:** `v0.3.0-alpha.1` visual preview, then `v0.3.0`.

### Phase 3 — Working developer chat / target `0.4.0`

**Goal:** A real multi-turn chat experience with a user-selected local model.

**Build:** Local model selector, per-session conversation history, streaming or chunked rendering, safe Markdown/code display, Cancel/Retry, bounded request timeouts, actual usage metadata when available, and Pair event integration.

**Acceptance tests:**

- [ ] Two consecutive prompts preserve context within one session without mixing other sessions.
- [ ] Code formatting and copy retain exact text; malicious HTML is inert.
- [ ] Stream, final completion, cancellation, and error paths leave Pair in the correct state.
- [ ] Browser close or server shutdown releases resources.
- [ ] A localhost-only demo works without any cloud account.

**Release:** `v0.4.0-beta.1`, then `v0.4.0` when stable.

### Phase 4 — Intelligent local routing / target `0.5.0`

**Goal:** Make routing useful with the actual models installed, not a cloud-only static registry.

**Build:** Dynamic model catalog, manual pin versus Auto Local mode, capability-aware filtering, documented routing rationale, constrained local fallback, latency/cost metadata with unknown values shown honestly. Reuse the Rust complexity scorer; **do not treat prompt score as proof that a model can perform a task**.

**Acceptance tests:**

- [ ] Manual model pin remains honored until changed by the developer.
- [ ] Auto Local chooses only from available, eligible, developer-authorized local models.
- [ ] Fallback is restricted to local models in local-only mode; any remote option requires separate opt-in.
- [ ] Model removal, restart, and stale metadata are handled without pretending an unavailable model is online.
- [ ] Routing explanations name the rule/capability basis and acknowledge unbenchmarked choices.

**Release:** `v0.5.0-beta.1`, then `v0.5.0`.

### Phase 5 — Hardening and stable release / targets `0.9.0-rc.1` -> `1.0.0`

**Goal:** Make the developer experience reliable and supportable.

**Build:** Cross-platform packaging validation, quality/security audit, dependency and license attribution, accessibility review, docs/videos, changelog, release automation, and optional usability evaluation.

**Acceptance tests:**

- [ ] Clean installation and `openpair ui` smoke test on Windows, macOS, and Linux.
- [ ] No dependency on cloud credentials for local UI installation or operation.
- [ ] Public CLI API/backward-compatibility test suite remains green.
- [ ] No Flask debugger, permissive external server bind, unsafe HTML injection, or unapproved telemetry.
- [ ] Documentation, quickstart, migration notes, license notices, and release artifacts match the published version.
- [ ] A signed-off release candidate is tested before publishing `v1.0.0`.

**Release:** `v0.9.0-rc.1` and subsequent release candidates if necessary, then `v1.0.0` only after all gates pass.

## 8. Versioning, branching, and release engineering

Use **Semantic Versioning**: `MAJOR.MINOR.PATCH`, with `-alpha.N`, `-beta.N`, or `-rc.N` prerelease suffixes when appropriate. In `0.x`, APIs may evolve but breakage should still be documented. Major versions after `1.0.0` must signal incompatible public-API changes.

**Single version source:** Prefer `pyproject.toml` as authoritative. The current package also declares `__version__ = "0.1.0"` in `python/openpair/__init__.py`; prevent divergence by deriving or checking one against the other. Do not confuse a model-registry snapshot date with the package release version.

**Proposed branch and PR workflow:**

1. Branch from `master` using `feat/local-adapters`, `feat/pair-ui`, `fix/...`, or `docs/...`.
2. Make focused PRs; include issue, implementation notes, screenshots for UI changes, and test evidence.
3. Keep existing CLI tests and Rust tests green before merge. Add targeted tests for each feature.
4. Merge only after review and CI; never commit `.env` or local session logs.
5. Update `CHANGELOG.md`, `README.md`, version metadata, and GitHub Release notes for every tagged release.
6. Create an annotated tag `vX.Y.Z` from the tested commit; publish a GitHub release with accurate scope, migration guidance, and known limitations. Add wheels/PyPI publishing only after reproducible build validation.

**Minimum release checklist**

- [ ] All acceptance criteria for the phase completed and manually verified.
- [ ] `cargo test` passes; `pytest -m "not live"` passes; new UI tests pass.
- [ ] `python -m build` / maturin wheel build succeeds in designated release environment.
- [ ] Changelog, README installation snippets, and package version match.
- [ ] License/attribution and dependency inventory reviewed.
- [ ] Release tag and GitHub Release notes created; do not call unreleased features “available.”

### Example changelog template

```markdown
## [0.2.0] - YYYY-MM-DD
### Added
- Local Ollama model selection and local-only execution policy.
### Changed
- <Document a genuine behavior change.>
### Fixed
- <Only completed bug fixes.>
### Security
- <Relevant hardening, if any.>
### Known limitations
- Pair browser UI is not included until a later phase.
```

## 9. Security, privacy, and performance gates

**Do not blindly copy all Avatar UI Core backend behavior.** The reference is a useful UI foundation, but its sample app has a single global chat and uses a Flask development-server configuration. Implement separate sessions, validate inputs, render user/model text safely, and keep the web debugger disabled in distributed builds.

| Concern | Required guardrail |
|---|---|
| Local network exposure | Bind UI to `127.0.0.1` by default, not `0.0.0.0`; remote access requires explicit advanced configuration |
| Remote fallback | Local-only policy checked at **every** call/redirect; disclose and require opt-in for cloud transport |
| Untrusted model text | Escape/sanitize HTML, avoid inserting raw strings with `innerHTML`, constrain Markdown renderer |
| Local endpoint safety | Validate scheme/host/port, prevent SSRF-style access to arbitrary hosts or internal metadata services |
| Browser-to-local API | Check origin / host; apply CSRF defenses to mutation endpoints; no wildcard CORS by default |
| API keys and settings | Keep secrets server-side; never write keys to URL/query string, logs, or browser storage |
| Session privacy | In-memory MVP sessions; no opt-out-required analytics or prompt retention by default |
| Dependence on external assets | Bundle UI assets locally so offline use remains possible |
| UI performance | Small original sprites, no second inference model for animation, optional motion/sound |
| Request resilience | Connection/read timeouts, bounded concurrency, cancellation, no endless retry loop |

**Performance metrics are targets, not measurements:** Track UI startup time, initial render time, memory overhead above the model runtime, first-token latency, completed-response latency, and failed/fallback request counts. Establish real baselines before publishing numeric performance claims.

## 10. Developer work order and definition of done

**Recommended first PR sequence:**

1. Add a local-only policy and Ollama model discovery with tests (`v0.2.0` foundation).
2. Establish a narrow adapter protocol shared by Ollama and later LM Studio.
3. Add optional Flask UI dependencies and a minimal `openpair ui` launcher; preserve `openpair "prompt"`.
4. Integrate an original Pair design and event-driven state controller.
5. Connect real local chat, then streaming and multi-turn sessions.
6. Add intelligent automatic local routing **after** manual selection is trustworthy.
7. Harden and release in versioned increments.

A feature is **done** only when it has a reproducible test, documented behavior, useful failure handling, a clean installation path, and an explicit status change from Planned to Implemented in this document. PR reviewers should reject UI changes that imply nonexistent model capabilities or silently weaken the local-only boundary.

### Contributor PR template (copy into the PR description)

```markdown
## Phase / release target
## Problem and scope
## Files changed
## UX screenshots or before/after example
## Tests executed and results
## Privacy/security impact
## Compatibility impact
## Known limitations
## Documentation updated
```

## 11. References, implementation notes, and attribution

**Project sources (code audited 17 Nov 2026)**

- [OpenPair repository](https://github.com/Pharadee1112/Openpair)
- [Rust routing core](https://github.com/Pharadee1112/Openpair/tree/master/src)
- [Python client and CLI](https://github.com/Pharadee1112/Openpair/tree/master/python/openpair)
- [CI workflow](https://github.com/Pharadee1112/Openpair/blob/master/.github/workflows/ci.yml)
- [Avatar UI Core (MIT)](https://github.com/sito-sikino/avatar-ui-core) — interface inspiration and potentially reusable frontend structure; preserve license and copyright notice for reused material.
- [AI Watchdog](https://github.com/patthai/AI-watchdog) and [Web-LLM-Dark-Pattern-Demo](https://github.com/patthai/Web-LLM-Dark-Pattern-Demo) — conceptual inspiration only; **do not import code/assets without a license review**.

**Official engineering references**

- [Ollama local API and OpenAI-compatible endpoint](https://docs.ollama.com/api)
- [Ollama API model listing (`/api/tags`)](https://github.com/ollama/ollama/blob/main/docs/api.md)
- [LM Studio OpenAI-compatible API](https://lmstudio.ai/docs/developer/openai-compat)
- [Python packaging: `pyproject.toml` and optional dependencies](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
- [Flask server security](https://flask.palletsprojects.com/en/stable/server/)
- [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html)
- [GitHub release process](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository)

**License note:** Avatar UI Core declares MIT licensing. The OpenPair root was not observed to contain a `LICENSE` file during this audit. Confirm the project's intended distribution license with maintainers before shipping adapted third-party code or a publicly redistributed package. Keep source attribution separate from authorship of the new Pair character.

---

**Maintainer note:** Treat this as the source-of-truth handoff document for the proposed **Pair local-first interface**. Check off phases only after merged implementation and tests, update the inventory on each release, and never relabel future behavior as already shipped.
