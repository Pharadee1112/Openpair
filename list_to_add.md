# OpenPair — สิ่งที่จะเพิ่มเติม (Feature Backlog)

> ไฟล์นี้เก็บ feature และ plan ที่อยากทำในอนาคต ยังไม่ได้อยู่ใน SRD หลัก  
> Last updated: 2026-06-02

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
- [ ] Unit test: call_ollama() mock response
- [ ] Unit test: fallback เมื่อ Ollama ไม่ available
- [ ] Integration test (optional): Ollama รันจริง → ได้ response จริง
- [ ] Benchmark: เปรียบ open-source (OpenRouter) vs closed-source cost/quality

### Priority

**Priority: MEDIUM** — Thai benchmark เสร็จแล้ว OpenRouter เพิ่มได้เร็ว Ollama เพิ่มได้ทีหลัง

### ลำดับแนะนำ

1. **OpenRouter ก่อน** — ง่ายสุด แค่ caller + registry entries ใหม่
2. **Ollama** — เพิ่ม availability check + fallback logic

---

> Next session: เริ่มที่ OpenRouter ก่อน แล้วค่อยทำ Ollama fallback
