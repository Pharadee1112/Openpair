# OpenPair — Architecture Documentation

> สร้างจากการอ่าน SRD v1.1 (PDF) และ source code ใน `src/`
> Last updated: 2026-05-22

---

## 📌 Vision หลัก

> OpenPair คือ **Middleware "จราจรทางอากาศ"** — คั่นกลางระหว่าง Application ของ user กับ AI Models ต่าง ๆ เพื่อให้งานไปเจอ model ที่เหมาะสมที่สุดโดยอัตโนมัติ

เป้าหมาย 3 ข้อ:
- **ลดต้นทุนสูงสุด 85%** — ไม่ส่งงานง่ายไปหา GPT-4o ทุกครั้ง
- **เพิ่มความเร็ว** — งานง่าย → model เล็ก → ตอบเร็ว
- **รักษาคุณภาพ** — ระบบ fallback + judge คอย verify

---

## 🧱 Layer Architecture (ตาม SRD)

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1 — Frontend / CLI                                   │
│  Python 3.10+, Click/Typer                                  │
│  รับ input จาก user, แสดงผล, จัดการ config                 │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  Layer 2 — Python API Layer                                 │
│  Python Library (pip install openpair)                      │
│  Public API สำหรับ developer, type hints, async support     │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  Layer 3 — Binding Layer   ← lib.rs ทำหน้าที่นี้           │
│  PyO3 + Maturin                                             │
│  สะพานเชื่อม Python ↔ Rust                                 │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  Layer 4 — Core Engine (Rust)  ← classifier + registry +   │
│                                   router ทำงานที่นี่        │
│  Classification Logic, Decision Engine                      │
│  No GC, < 5ms routing latency                               │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  Layer 5 — External AI APIs                                 │
│  OpenAI / Anthropic / Google / Ollama                       │
│  ปลายทางที่รับ prompt และส่งคำตอบกลับ                      │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔬 Core Engine (Rust) — ภายในละเอียด

### Module 1 — `src/classifier.rs` : วัดความซับซ้อน

**SRD spec (3.1.2 Intent Classifier):**
- Complexity Score 1–10
- วัดจาก: Prompt Length + Vocabulary Diversity + Chain-of-Thought Requirement

**Implement จริง — 5 เกณฑ์:**

| เกณฑ์ | คะแนนสูงสุด |
|---|---|
| ความยาว (จำนวนคำ) | 3 pts |
| ความยากของคำ (avg word length) | 2 pts |
| Keywords วิเคราะห์ (`analyze`, `design`, `trade-off`, …) | 2 pts |
| Keywords โค้ด (`function`, `class`, `database`, …) | 2 pts |
| คำถามหลายข้อ / numbered list | 1 pt |

**Gap ที่ยังไม่ implement:**
- ❌ Semantic Router (BERT / Sentence-Transformers + Cosine Similarity)
- ❌ Task Type Detection: Generative vs. Extractive vs. Reasoning
- ❌ Context Requirement Check (ตรวจว่า prompt ยาวเกิน 16K tokens ไหม)
- ❌ Sensitivity Check (ตรวจ private data / compliance)

---

### Module 2 — `src/registry.rs` : ฐานข้อมูล Models

**SRD spec (3.2):**
- เก็บ: Model Name, Provider, Capabilities, Pricing, Context Window, Avg Latency
- รองรับ Hot-Reload + Custom Model (Ollama)

**Models ที่ register ไว้แล้ว:**

| Model | Provider | Tier | Context | Cost/1K input |
|---|---|---|---|---|
| Claude 3 Haiku | anthropic | Small | 200K | $0.00025 |
| GPT-4o Mini | openai | Small | 128K | $0.00015 |
| Gemini 1.5 Flash | google | Small | 1M | $0.000075 |
| Claude 3.5 Sonnet | anthropic | Mid | 200K | $0.003 |
| Gemini 1.5 Pro | google | Mid | 1M | $0.00125 |
| GPT-4o | openai | Top | 128K | $0.005 |
| Claude 3.5 Sonnet | anthropic | Top | 200K | $0.003 |
| Gemini 1.5 Pro | google | Expert | 1M | $0.00125 |

**Tier Mapping:**

```
Score 1–3  → Small  (fast, cheap)
Score 4–6  → Mid    (balanced)
Score 7–9  → Top    (quality)
Score 10   → Expert (best + long context)
```

**Gap ที่ยังไม่ implement:**
- ❌ Hot-Reload จาก YAML/JSON config
- ❌ Average Latency field
- ❌ Capabilities Tags (เช่น `["code", "vision", "reasoning"]`)
- ❌ Ollama / Local model support
- ❌ Constraint Checker (context window check, budget cap, rate limit)

---

### Module 3 — `src/router.rs` : ตัวตัดสินใจหลัก

**Decision flow:**

```
prompt
  │
  ▼
score_complexity()        ← classifier.rs
  │
  ▼
ModelTier::from_score()   ← Small / Mid / Top / Expert
  │
  ▼
registry.preferred_for_tier(tier, preferred_provider)
  ├── ถ้า user บอก provider → เลือกตัวนั้น
  └── ถ้าไม่บอก → เลือกราคาถูกสุดใน tier
  │
  ▼
RoutingDecision {
  model_id, model_name, provider,
  tier, complexity_score,
  reason, cost_per_1k_input
}
```

**Gap ที่ยังไม่ implement:**
- ❌ Quality Threshold: `Score = Quality − λ × Cost`
- ❌ LLM Cascade (fallback chain Small → Mid → Top → Expert)
- ❌ LLM-as-a-Judge (verify คุณภาพคำตอบ)
- ❌ Decision Cache (LRU Cache สำหรับ prompt ซ้ำ)
- ❌ Cost Budget Cap

---

### Module 4 — `src/lib.rs` : Python Binding Entry Point

expose ให้ Python เรียกได้ 2 function:

```python
import openpair_core

result = openpair_core.route("write me a function")
# → RoutingDecision(model='GPT-4o Mini', tier='small', score=3, cost=$0.00015/1K)

score = openpair_core.score_complexity("hello world")
# → 1
```

---

### Module 5 — `src/main.rs` : CLI Demo Binary

```bash
cargo run --bin openpair-demo -- "Design a microservices system"

# Output:
# ──────────────────────────────────────────
#   OpenPair Routing Engine (Rust Demo)
# ──────────────────────────────────────────
#   Prompt : Design a microservices system
#   Score  : 7/10
#   Tier   : top
#   Model  : GPT-4o (openai)
#   Cost   : $0.00500/1K input tokens
#   Reason : High complexity — using a top-tier reasoning model...
# ──────────────────────────────────────────
```

---

## 🔄 Data Flow เต็มรูปแบบ (SRD vs ที่ implement แล้ว)

| Step | Layer | Action | สถานะ |
|---|---|---|---|
| 1 | Python API | รับ input (Prompt, Config, API Keys) | ❌ ยังไม่มี |
| 2 | Binding Layer | Serialize Python Object → Rust Struct | ✅ lib.rs |
| 3 | Core Engine | Tokenize + Embed (BERT/ST) | ❌ Phase 3 |
| 4 | Core Engine | Cosine Similarity vs. Route Groups | ❌ Phase 3 |
| 5 | Core Engine | Complexity Scoring | ✅ classifier.rs |
| 6 | Core Engine | Constraint Check (Context, Budget) | ❌ ยังไม่มี |
| 7 | Core Engine | Decision: เลือก Optimal Model | ✅ router.rs |
| 8 | Python API | Call Provider API | ❌ ยังไม่มี |
| 9 | Judge Module | ตรวจสอบคุณภาพ (Optional) | ❌ Phase 2/3 |
| 10 | Python API | ส่งผลลัพธ์ + Metadata กลับ | ❌ ยังไม่มี |

---

## 🗺️ Roadmap เทียบกับสถานะจริง

| Phase | Timeline | เป้าหมาย | สถานะ |
|---|---|---|---|
| **Phase 1** MVP | Weeks 1–4 | Rust core + PyO3 + CLI + rule-based router | ✅ 14/16 tests pass |
| **Phase 2** Logic | Weeks 5–9 | Registry YAML + Constraint + LLM Cascade + Stats | ⏳ บางส่วนทำแล้ว |
| **Phase 3** Semantic | Weeks 10–15 | BERT embeddings + Cosine Similarity + LLM Judge | ❌ ยังไม่เริ่ม |
| **Phase 4** Production | Weeks 16–22 | PyPI + FastAPI + React Dashboard + OpenTelemetry | ❌ ยังไม่เริ่ม |

---

## 📊 Diagram ภาพรวม

```
        ┌──────────────────────────────────────┐
        │         OpenPair (เป้าหมายสุดท้าย)   │
        │                                      │
        │  [Python CLI]  [Web Dashboard]       │
        │       │              │               │
        │  [Python API Layer]                  │
        │       │                              │
        │  [PyO3 Binding] ← lib.rs ✅          │
        │       │                              │
        │  ┌────▼──────────────────────────┐   │
        │  │     Rust Core Engine          │   │
        │  │  ┌─────────┐ ┌─────────────┐ │   │
        │  │  │classifier│ │  registry   │ │   │
        │  │  │  .rs ✅  │ │   .rs ✅   │ │   │
        │  │  └────┬─────┘ └──────┬──────┘ │   │
        │  │       └──────┬───────┘        │   │
        │  │         ┌────▼────┐           │   │
        │  │         │router.rs│ ✅         │   │
        │  │         └────┬────┘           │   │
        │  │  [BERT ❌] [Cache ❌] [Judge ❌]│  │
        │  └─────────────┬────────────────-┘   │
        │                │                     │
        │   ┌────────────┼────────────┐        │
        │   ▼            ▼            ▼        │
        │ OpenAI     Anthropic     Google      │
        │ (❌ not     (❌ not      (❌ not     │
        │  called)    called)      called)     │
        └──────────────────────────────────────┘
```

---

## ⚡ Non-Functional Requirements (เป้าหมาย)

| Metric | Target |
|---|---|
| Routing Decision Latency | < 5 ms (P99) |
| Embedding Computation | < 50 ms |
| Memory Footprint | < 100 MB |
| Throughput | ≥ 1,000 req/sec |
| Cache Hit Rate | ≥ 40% |
| Cold Start Time | < 500 ms |

---

## 🔒 Security Requirements

- ❌ ไม่เก็บ API Key ใน plain text — ใช้ Environment Variables
- ❌ No Prompt Logging by default
- ❌ Local Model (Ollama) support สำหรับ data privacy
- ❌ Input Sanitization (Prompt Injection prevention)

---

## 🌐 Future: Web Application (Phase 4)

| Layer | Technology |
|---|---|
| Frontend | React 18+ + TypeScript + Shadcn/UI + Tailwind |
| Charts | Recharts |
| Backend | FastAPI (Python) |
| Auth | JWT + OAuth2 (GitHub, Google SSO) |
| Database | PostgreSQL + Redis |
| Queue | Celery + Redis |
| Infra | Docker → Kubernetes |
| Monitoring | Grafana + Prometheus + Sentry |

### SaaS Pricing Model

| Tier | Price | Features |
|---|---|---|
| Open Source | Free | CLI + Library, Community Support |
| Starter | $29/mo | Web Dashboard, 5M tokens/mo, 3 Users |
| Pro | $99/mo | Unlimited Routing, Analytics, 10 Users, SLA 99.9% |
| Enterprise | Custom | On-Premise, SSO, Dedicated Support, SLA 99.99% |

---

## ✅ สรุป: ทำแล้ว vs ยังขาด

| ทำแล้ว ✅ | ยังขาด ❌ |
|---|---|
| Rule-based complexity scoring | BERT semantic embeddings |
| Model registry (hardcoded) | YAML config + hot-reload |
| Tier-based routing decision | LLM Cascade fallback chain |
| PyO3 Python binding | จริง API calls (OpenAI/Claude/Google) |
| CLI demo | Python library public API |
| 14/16 tests pass | Constraint checker + budget cap |
| | LLM-as-a-Judge quality verification |
| | Decision Cache (LRU) |
| | Web Dashboard |
