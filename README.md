# OpenPair

**English** | [ภาษาไทย](README_TH.md)

Intelligent AI router — automatically picks the cheapest model that can actually handle a given prompt (currently free-tier Gemini + Groq), with automatic fallback when a provider is rate-limited, including a local Ollama fallback.

## The problem

When people use several LLM providers, most hard-code a single model. They overpay on easy prompts or get too little quality on hard ones, and when a provider rate-limits, requests simply fail.

OpenPair addresses this by:
- **Scoring prompt complexity** (1–10) and choosing the cheapest model at a sufficient tier, instead of sending every prompt to a top-tier model. Since 2026-10-02 the registry contains only models that are genuinely free to use from **Gemini + Groq** (OpenAI/Anthropic/OpenRouter were removed from the registry; their caller code remains).
- **Detecting Thai** and routing it to the model that handles Thai best, based on the Thai benchmark in this repo. Every registry model has been measured: `gemini-3.1-flash-lite`, `openai/gpt-oss-20b`, `openai/gpt-oss-120b` on the 600-case full suite, and `gemini-3.6-flash` on the 20-case core suite.
- **Automatic fallback**: if the primary provider returns 429 (rate limit) or 503 (overloaded), the next provider in the chain is tried — no retry logic to write yourself.
- **Ollama as the last resort**: if every cloud provider is rate-limited at once, or no API key is set, but Ollama is running locally, OpenPair falls back to the local model.

## Architecture

```
src/                      ← Rust core: complexity scoring, model registry, routing decision
  classifier.rs           ← complexity score 1–10 + Thai detection
  registry.rs             ← every model, its tier, price, thai_score
  router.rs               ← decides which tier + model fits this prompt
  main.rs                 ← demo binary (routing only, no real API calls)

python/openpair/          ← Python wrapper around the Rust core (PyO3 + maturin)
  client.py               ← OpenPair class — .route() (decision only) / .call() (real call + auto-fallback)
  caller.py               ← real API calls per provider (openai / anthropic / google / groq / ollama)
  config.py               ← API keys from .env / env vars
  errors.py               ← which errors are retryable (429/503) and which raise immediately
  benchmark/              ← Thai quality benchmark (6 categories — core 20 cases / full 600 cases)
    data/*.json           ← extended cases, one file per category (with core = 100 per category)
    checkpoint.py         ← resume support — saves each case to .jsonl so progress survives quota exhaustion or a killed process
```

The routing decision (tier + model + price) is computed in Rust for speed; real API calls, retries and fallback live in Python.

## Install

Requires a Rust toolchain and Python 3.9+.

```bash
git clone https://github.com/Pharadee1112/Openpair.git
cd Openpair

python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

pip install maturin
maturin develop --release     # build Rust core → python/openpair/_core*.pyd/.so
pip install -e ".[dev]"
```

> **Important**: after every change to `src/*.rs`, run `maturin develop --release` again — `cargo build` alone is not enough, because Python imports the `.pyd`/`.so` built for a separate target.

## Configuration

```bash
cp .env.example .env
```

Then set at least one key:

```
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AI...
GROQ_API_KEY=gsk_...          # optional, free and very fast
OLLAMA_BASE_URL=http://localhost:11434   # optional, this is the default
OLLAMA_MODEL=llama3.1                    # optional, `ollama pull` this model first
```

You do not need every provider — one key is enough. More providers mean better fallback.

## Usage (Python)

```python
from openpair import OpenPair

client = OpenPair()  # reads keys from .env

# Real API call — the router picks the model, with auto-fallback on rate limits
result = client.call("อธิบาย black hole ให้เข้าใจง่ายๆ")
print(result.response_text)
print(result.model_name, result.provider, f"${result.estimated_cost:.5f}")

# Routing decision only — no API call, no cost
decision = client.route("Write a Python class for a binary tree")
print(decision.model_name, decision.tier, decision.complexity_score)

# Force a specific provider
result = client.call("Hello!", preferred_provider="groq")

# Custom fallback order (usually unnecessary — there is a default chain)
result = client.call("Hello!", fallback_providers=["google", "groq"])
```

**Default fallback chain** (when `fallback_providers` is not given):
`[provider chosen by the router] → groq → google → ollama (only if a real server answers the ping)` — providers with no model in the registry (e.g. openai) are skipped even if a key is set.

## Usage (CLI)

```bash
openpair "อธิบาย recursion ให้เด็ก ป.6 ฟัง" --route-only
```
```
Model:    Gemini 3.1 Flash Lite (gemini-3.1-flash-lite)
Provider: google
Tier:     small
Score:    2/10
Reason:   Low complexity — using a fast, cost-efficient model [Thai]. Score: 2/10 → Gemini 3.1 Flash Lite (Thai routing priority).
```

`--route-only` prints only the decision — **no API call, no key needed** — useful to see how the router thinks.

```bash
openpair "อธิบาย recursion"                      # real call + auto-fallback
openpair "Hello!" --provider groq                 # force a provider
openpair "สรุปให้หน่อย" --system "ตอบสั้นๆ"        # system prompt
openpair "Hello!" --max-tokens 512                # length limit (default 2048)
```

The answer goes to stdout and model/price/latency info to stderr, so
`openpair "..." > answer.txt` writes only the answer to the file.

## Rust demo binary (routing preview only)

```bash
cargo run --bin openpair-demo -- "your prompt here"
```

Shows only the routing decision (score, tier, model, estimated price) — **no real API call**, no key needed.

## Thai quality benchmark

```bash
python run_benchmark.py                                    # default models (Gemini)
python run_benchmark.py --models gemini-3.6-flash          # specific model
python run_benchmark.py --category qa                      # one category
python run_benchmark.py --detail                           # per-case detail
python run_benchmark.py --suite full                       # full 600-case suite (100 per category)
python run_benchmark.py --suite full --cases qa_52,qa_53   # only these cases (or @file with one id per line)
```

### Suites: `core` and `full`

- **`core`** (default) — the original 20 cases, kept comparable with earlier results and cheap on quota.
- **`full`** — 600 cases (qa / translation / summarization / classification / code_thai / creative, 100 each). The extension lives in `python/openpair/benchmark/data/*.json` and focuses on current content:
  - **Current news (Sep 2026)** — floods, Asian Games gold, exports, ADB, 30-day visa, diesel prices, etc. **The article text is in the prompt** (this measures Thai reading/summarising/translation, not whether the model knows recent news, which depends on its training cutoff).
  - **Teen/social-media slang 2025–2026** — ตัวมัม, มองบน, ป้ายยา, ทัวร์ลง, ฮ้อป, situationship, rizz, no cap, etc. (meaning questions, English→Thai slang translation, formal↔teen register rewriting, sentiment with sarcasm).
  - **Thai idioms / regional dialects** — traditional idioms still in use, plus Isan/Northern/Southern in writing.
  - **Code in a Thai context** — national ID checksum, Buddhist↔Common Era years, baht amounts in words, PromptPay QR, Thai mobile numbers.
- ⚠️ `full` = 600 requests per model — Gemini free-tier quotas can take several days (resume helps); Groq is much faster.
- ⚠️ News and slang cases age; review them every 6–12 months. Scores from `full` are not directly comparable with `core` (different cases).

Results suggest a `thai_score`, which you update in `src/registry.rs` by hand (no auto-patch yet).

### Resume — continue after running out of quota

Every case result is saved immediately to a checkpoint file (`<output without extension>.checkpoint.jsonl`), keyed by `(model_id, case_id)`:

- **Running the same command again** skips finished cases automatically and calls the API only for the rest — adding new cases and rerunning costs nothing for the old ones.
- If the Google API reports the **daily quota** is exhausted (not a temporary rate limit), the run stops immediately instead of retrying in vain; finished results are already saved. Rerun after the quota resets (usually midnight Pacific Time).
- To start over without resuming: add `--fresh`.
- Custom checkpoint path: `--checkpoint path/to/file.jsonl`.

```bash
python run_benchmark.py --fresh                             # ignore the old checkpoint
python run_benchmark.py --checkpoint my_ckpt.jsonl          # custom checkpoint file
```

## Testing

```bash
cargo test                    # Rust — 26 tests
pytest -m "not live"          # Python — 126 tests (mocked, no API key needed)
pytest tests/test_live.py -m live   # 3 tests that call real APIs (real keys; uses free-tier quota)
```

Live tests are in `tests/test_live.py` (`@pytest.mark.live`); each calls `pytest.skip()` itself when its provider's key is missing from `.env`.

> **Note**: plain `pytest` (no `-m`) runs all 129 tests, including the 3 live tests (`test_live_google` / `test_live_groq` / `test_live_thai_routing`) that **call real APIs** — free tier, so no cost, but they use daily quota. Add `-m "not live"` to avoid that.

## Current status / known limitations

- **CLI is ready** — `openpair "..."` is a real shell command (`[project.scripts]` in `pyproject.toml` → `openpair = "openpair.cli:main"`); see "Usage (CLI)" above.
- **OpenRouter** has a caller (`run_benchmark.py --models openrouter:<org/model>`) but is not in the registry/routing — benchmark use only.
- **Ollama fallback** has been tested against a real Ollama server (2026-10-09, `qwen2.5:3b`); the automated tests still use the `FakeOllama` mock in `tests/conftest.py`.
- **Benchmark resume/checkpoint** (`python/openpair/benchmark/checkpoint.py`) — an interrupted run can be rerun with the same command without spending quota on finished cases; see "Resume" above.
- **Gemini free-tier quotas are per model** (not per project). For example, `gemini-3.1-flash-lite` and `gemini-3.6-flash` had quota left on the test date, but `gemini-3.1-pro-preview` returned 429 `limit: 0` — **the free tier has no quota for that model at all** — so it was removed from the registry (2026-10-02). The Expert tier has no model of its own; the router uses the Top-tier model. Models whose daily quota is genuinely used up (limit > 0) can be rerun after the reset; the resume system skips finished cases.
- **Thai benchmark status** (2026-10-02): every registry model measured — `gemini-3.1-flash-lite` 9, `openai/gpt-oss-20b` 9, `openai/gpt-oss-120b` 9 (full 600-case suite), `gemini-3.6-flash` 6 (core suite). Thai routing (2026-10-17): **every complexity level → flash-lite**, because on the 598-case full suite flash-lite beats gpt-oss at every difficulty (9.40 vs 8.79/8.71); if Gemini is rate-limited, the request falls back to Groq as usual.

## Research paper

The behavioural study of models on the 600-case Thai benchmark lives in `paper/` — drafts [`DRAFT.md`](paper/DRAFT.md) (English) / [`DRAFT_TH.md`](paper/DRAFT_TH.md) (Thai) and reproducible analyses: `ANALYSIS.md`, `HUMAN_REVIEW.md`, `STABILITY.md`. The dataset card is at [`hf_dataset/README.md`](hf_dataset/README.md).

## Roadmap

See `list_to_add.md` for planned work (YAML-based model config). Fine-tuning is deliberately outside the scope of the current work (this work measures where models fail, not how to improve them); a plan for follow-up work is in `finetune/README.md`.
