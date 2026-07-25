# OpenPair — สิ่งที่จะเพิ่มเติม (Feature Backlog)

> ไฟล์นี้เก็บ feature และ plan ที่อยากทำในอนาคต ยังไม่ได้อยู่ใน SRD หลัก  
> Last updated: 2026-07-25

---

## DONE — CI fix + Registry 2026 refresh + Classifier accuracy (2026-07-25)

> ตรวจโค้ดจริงแล้ว ตรงกับที่รายงานทั้ง 3 ข้อ — commit `8360447`, `9d58553`, `048ae65`, `d190394`, ทั้งหมด push แล้ว (`git status` clean)

- [x] **ซ่อม CI** — `maturin develop` พังบน CI เพราะต้องมี venv ที่ไม่มีใน CI → เปลี่ยนเป็น `pip install ".[dev]"` ใน `.github/workflows/ci.yml` — ยืนยันแล้วว่าไฟล์ workflow ใช้ `pip install ".[dev]"` จริง (rust-test + python-test)
- [x] **อัปเดต `src/registry.rs`** — โมเดล 2024 ตายหมด เปลี่ยนเป็นรุ่นปัจจุบัน (Haiku 4.5, Sonnet 5, Opus 5, GPT-5.4 Nano, GPT-5.5, Gemini 3.1 Flash-Lite/3.6 Flash/3.1 Pro, Groq เดิม) — ยืนยันแล้วว่าไม่มี id ปลอม `claude-3-5-sonnet-top` เหลืออยู่ในไฟล์
- [x] **แก้ `src/classifier.rs`** — ยืนยันแล้วว่ามีครบทั้ง 5 จุด: length buckets ละเอียดขึ้น (8 bucket แยก Thai char-count กับ English word-count), keyword ใช้ stem+tokenize+`starts_with`, น้ำหนัก complex keyword เพิ่มเป็น 0.8, ภาษาไทยข้าม avg-word-length และใช้ char count แทน, เพิ่ม test ครบ (10 test functions รวม `complex_13_word_sentence_scores_moderately_high`)

**หมายเหตุแก้ไขความเข้าใจผิด:** ที่คิดว่า `--version` flag "โค้ดเสร็จแล้วแค่ยังไม่ push" — ตรวจแล้วไม่จริง ไม่มี `__registry_snapshot__` ใน `__init__.py` และไม่มี `--version` ใน CLI เลย ไม่มี commit ไหนเคยเพิ่มด้วย ต้อง**เขียนใหม่ทั้งหมด** ไม่ใช่แค่ push

---

## ยังค้างอยู่ (next action — เริ่มตรงนี้เมื่อกลับมา)

- [ ] **เพิ่ม `--version` flag ให้ CLI จริง** — ยังไม่มีโค้ดเลย (ดูหมายเหตุด้านบน) ต้องเพิ่ม `__registry_snapshot__ = "2026-07-25"` ใน `python/openpair/__init__.py` + `--version` ใน `cli.py` (argparse `action="version"`) แล้ว `pip install -e .` + commit + push จุดประสงค์: ให้ผู้ใช้ระบุได้ว่ารันด้วย registry วันไหน (reproducibility สำหรับ paper)
- [ ] **อัปเดต README** — ยืนยันแล้วว่ายังมีจุดอ้างของเก่า: บรรทัด 10 "GPT-4-class" (ควรเป็นชื่อรุ่นปัจจุบัน), บรรทัด 11 "Thai-quality benchmark วัดจริงอยู่ในโปรเจกต์" (ยังไม่ได้วัดจริง ยังรอ benchmark), เช็คตัวอย่าง output ในไฟล์ด้วยว่าอ้างโมเดล/ราคาเก่าหรือไม่
- [ ] **ตัดสินใจเรื่อง score ที่เหมาะสม** — "Design a distributed database..." ได้ 5/10 ตอนนี้ → Llama 3.3 70B ตอบดีมากที่ $0.00003 คำถามคือควรดันเป็น 8 ไหม (→ โมเดลแพงกว่า) — **ต้องรอผล benchmark ก่อน ห้ามเดาเอง**
- [ ] รัน benchmark ครบทุก model (ติด rate limit ตอนทดสอบครั้งก่อน)
- [ ] อัปเดต `thai_score` ใน `registry.rs` ด้วยผลจริงจาก benchmark
- [ ] Custom benchmark (ให้ user เพิ่ม test case เอง)

**ตัดสินใจแล้วว่ายังไม่ทำ:** แยก registry ออกเป็น YAML — เข้าใจภาพแล้ว (แยกข้อมูลออกจากโค้ด แก้ราคาโดยไม่ต้อง compile) แต่เป็นงานใหญ่ (ต้อง `serde_yaml` + error handling) ถ้าทำ ให้ไฟล์ติดไปกับโปรเจกต์ + มีค่า default ในตัว (โปรแกรมไม่พังถ้า yaml หาย)

---

## DONE — CLI + Test Coverage + CI (2026-07-20)

> ทำครบทั้ง 5 ข้อแล้ว

- [x] เขียน `cli.py` + `[project.scripts]` → มี CLI ให้ test ก่อน — `python/openpair/cli.py`, entry point `openpair = "openpair.cli:main"` ใน `pyproject.toml`
- [x] เขียน `tests/test_cli.py` ด้วย capsys → พิสูจน์ว่า CLI ทำงาน — 8 tests ผ่านหมด
- [x] เขียน FakeOllama fixture → พิสูจน์ว่า Ollama fallback ทำงาน (ไม่ต้องลง Ollama) — `tests/conftest.py` (`fake_ollama` fixture) + `tests/test_ollama_fallback.py`, 6 tests ผ่านหมด
- [x] ตั้ง GitHub Actions → คอมไม่ต้องแบก — `.github/workflows/ci.yml` (`rust-test` = `cargo test`, `python-test` = `maturin develop --extras dev` + `pytest -m "not live"`), verify คำสั่งจริงในเครื่องแล้วก่อน push
- [x] Live smoke test 1 ตัวด้วย Groq key → พิสูจน์ end-to-end ต่อของจริงได้ — รันทั้ง `test_live_groq` (pytest) และ CLI จริง (`openpair "..." --provider groq`) ได้ response จริงกลับมา

**บั๊กที่เจอระหว่างทำ:** CLI crash บน Windows console ที่ใช้ legacy codepage (cp874) เวลา print ตัวอักษร Unicode อย่าง `→` ใน routing reason — แก้ด้วย `sys.stdout/stderr.reconfigure(errors="replace")` ใน `cli.py`

~~ยังไม่ได้ push ขึ้น GitHub~~ — push แล้ว (ยืนยัน 2026-07-25, `git status` clean บน `master`)

---

## DONE — Thai Language Benchmark System

> สร้างเสร็จแล้วใน Phase 2.5

### สิ่งที่สร้างไปแล้ว

```
python/openpair/benchmark/
├── dataset.py    ← 20 Thai test cases, 6 หมวด (classification, summarization, qa, translation, creative, code)
├── scorer.py     ← keyword_score + thai_ratio + length score
├── runner.py     ← auto-retry เมื่อเจอ 429 rate limit
└── reporter.py   ← ตารางสรุปผลแบบ text
```

### Thai Routing Priority ที่ใช้อยู่ใน registry.rs

```
simple_thai  → gemini-2.5-flash-lite   (thai_score: 9, ราคาถูกสุด)
medium_thai  → claude-3-haiku           (thai_score: 7, balanced)
complex_thai → claude-3-5-sonnet        (thai_score: 9, ดีที่สุด)
```

### Test Status
- Python unit tests: 18/18 pass
- Benchmark unit tests: 31/31 pass
- Live API (Gemini): 2/2 pass

### สิ่งที่ยังค้างอยู่ (next action)
- [ ] รัน benchmark ครบทุก model (ติด rate limit ตอนทดสอบ)
- [ ] อัปเดต thai_score ใน registry.rs ด้วยผลจริง
- [ ] Custom benchmark (ให้ user เพิ่ม test case เอง)

---

## Ollama + OpenRouter Integration

> เพิ่ม local model (Ollama) และ open-source cloud model (OpenRouter) เข้า routing

### ทำไมถึงเพิ่ม

| | Ollama | OpenRouter |
|---|---|---|
| จุดเด่น | ฟรี, local, ไม่มี privacy concern | open-source models ร้อยกว่าตัว ง่าย ไม่ต้องลง |
| use case | dev/test โดยไม่เสียค่า API | benchmark open-source vs closed-source |

### โครงสร้างที่ต้องแก้ (3 ไฟล์)

#### 1. `src/registry.rs` — เพิ่ม model entries

```rust
// OpenRouter — open-source models via cloud
ModelMeta { id: "meta-llama/llama-3.1-70b-instruct", provider: "openrouter", tier: Mid,   thai_score: 6, ... }
ModelMeta { id: "mistralai/mistral-7b-instruct",      provider: "openrouter", tier: Small, thai_score: 4, ... }
ModelMeta { id: "deepseek/deepseek-r1",               provider: "openrouter", tier: Top,   thai_score: 5, ... }

// Ollama — local models
ModelMeta { id: "llama3.1:8b",   provider: "ollama", tier: Small, cost_per_1k_input: 0.0, thai_score: 4, ... }
ModelMeta { id: "llama3.1:70b",  provider: "ollama", tier: Mid,   cost_per_1k_input: 0.0, thai_score: 5, ... }
```

#### 2. `src/router.rs` — เพิ่ม fallback chain สำหรับ Ollama

```
route_prompt()
  ├── ถ้า preferred_provider = "ollama"
  │     ├── Ollama available?  → ใช้ Ollama
  │     └── ไม่ available      → fallback cheapest cloud ใน tier เดียวกัน
  └── ปกติ → cheapest in tier (Ollama cost=0 จะชนะเสมอ ถ้า available)
```

> Availability check จะทำใน Python (caller.py) ไม่ใช่ Rust
> เพราะ ping HTTP จาก Rust ซับซ้อนกว่า และ router ยังคืน RoutingDecision ได้ตามปกติ

#### 3. `python/openpair/caller.py` — เพิ่ม 2 callers

```python
# OpenRouter — เหมือน Groq คือใช้ OpenAI SDK + base_url ต่างกัน
def call_openrouter(model_id, prompt, api_key, ...):
    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
    )
    ...

# Ollama — ใช้ OpenAI SDK + localhost, ไม่ต้องใช้ api_key
def call_ollama(model_id, prompt, ...):
    client = openai.OpenAI(
        api_key="ollama",           # dummy key
        base_url="http://localhost:11434/v1",
    )
    ...

# เพิ่มใน _CALLERS dispatcher
_CALLERS = {
    "openai":      call_openai,
    "anthropic":   call_anthropic,
    "google":      call_google,
    "groq":        call_groq,
    "openrouter":  call_openrouter,   # ใหม่
    "ollama":      call_ollama,       # ใหม่
}
```

#### 4. `python/openpair/config.py` — เพิ่ม keys/config

```python
class ApiKeys:
    def __init__(self, ..., openrouter=None, ollama_base_url=None):
        ...
        self.openrouter    = openrouter    or os.getenv("OPENROUTER_API_KEY")
        self.ollama_base_url = ollama_base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    def is_ollama_available(self) -> bool:
        """Ping Ollama server — ถ้าไม่รัน return False"""
        import urllib.request
        try:
            urllib.request.urlopen(f"{self.ollama_base_url}/api/tags", timeout=1)
            return True
        except Exception:
            return False
```

### Fallback Flow สมบูรณ์

```
prompt เข้ามา
  │
  ▼
router.rs → RoutingDecision(provider="ollama", model="llama3.1:8b")
  │
  ▼
caller.py make_call()
  ├── provider = "ollama"?
  │     ├── config.is_ollama_available() = True  → call_ollama()
  │     └── False → หา cheapest cloud ใน tier เดียวกัน → call นั้นแทน
  └── provider อื่น → ตามปกติ
```

### Test Plan

- [ ] Unit test: call_openrouter() mock response
- [x] Unit test: call_ollama() mock response — `tests/conftest.py` (`fake_ollama` fixture, patches `openai.OpenAI` + `is_ollama_available`) + `tests/test_ollama_fallback.py` (2026-07-20)
- [x] Unit test: fallback เมื่อ Ollama ไม่ available — same file, `TestClientFallsBackToOllama` (no-keys case + all-cloud-rate-limited case + "doesn't use Ollama when a cloud provider succeeds" case)
- [ ] Integration test (optional): Ollama รันจริง → ได้ response จริง
- [ ] Benchmark: เปรียบ open-source (OpenRouter) vs closed-source cost/quality

### Priority

**Priority: MEDIUM** — Thai benchmark เสร็จแล้ว OpenRouter เพิ่มได้เร็ว Ollama เพิ่มได้ทีหลัง

### ลำดับแนะนำ

1. **OpenRouter ก่อน** — ง่ายสุด แค่ caller + registry entries ใหม่
2. **Ollama** — เพิ่ม availability check + fallback logic

---

> Next session: เริ่มที่ OpenRouter ก่อน แล้วค่อยทำ Ollama fallback
