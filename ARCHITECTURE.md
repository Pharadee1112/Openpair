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
│  PyO3 + Maturin = ทำหน้าที่ แปลงโค้ด Rust ของแก้มให้กลายเป็น      |
                    Python Library แบบสมบูรณ์               |
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
│  OpenAI / Anthropic / Google / Groq / Ollama                │
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
| Claude Haiku 4.5 | anthropic | Small | 1M | $0.001 |
| GPT-5.4 Nano | openai | Small | 1M | $0.0002 |
| Gemini 3.1 Flash Lite | google | Small | 1M | $0.00025 |
| Llama 3.1 8B | groq | Small | 128K | $0.00005 |
| Claude Sonnet 5 | anthropic | Mid | 1M | $0.003 |
| Gemini 3.6 Flash | google | Mid | 1M | $0.0015 |
| Llama 3.3 70B | groq | Mid | 128K | $0.00059 |
| GPT-5.5 | openai | Top | 1M | $0.005 |
| Claude Opus 5 | anthropic | Top | 1M | $0.005 |
| GPT-OSS 120B | groq | Top | 131K | $0.00015 |
| Gemini 3.1 Pro | google | Expert | 1M | $0.002 |

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
# → RoutingDecision(model='Llama 3.1 8B', tier='small', score=1, cost=$0.00005/1K)

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
#   Score  : 3/10
#   Tier   : small
#   Model  : Llama 3.1 8B (groq)
#   Cost   : $0.00005/1K input tokens
#   Reason : Low complexity — using a fast, cost-efficient model...
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
        │                │ API call            │
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

## 🤔 Tech Stack Decisions — ทำไมถึงเลือก Tech นี้?

### ทำไมถึงใช้ทั้ง Python และ Rust พร้อมกัน?

Python กับ Rust **ไม่ได้ใช้แทนกัน** — แต่ทำคนละหน้าที่:

```
User พิมพ์ prompt
       ↓
  [ Python ]  ← รับ input, เรียก API, แสดงผล (ขอบนอก)
       ↓  PyO3 bridge
  [ Rust   ]  ← ตัดสินใจว่าส่งไป model ไหน < 5ms (สมองกลาง)
       ↓
  [ OpenAI / Claude / Gemini ]
```

| ภาษา | ทำไมต้องมี | ทำไมอีกภาษาทำแทนไม่ได้ |
|---|---|---|
| **Rust** | routing < 5ms, ไม่มี GC pause, 1,000 req/sec | Python มี GIL + GC pause ควบคุมเวลาไม่ได้ |
| **Python** | `pip install`, ML ecosystem, AI SDK ทั้งหมด | Rust ไม่มี PyTorch / HuggingFace / LangChain |

### ทำไมไม่ใช้ JavaScript แทน Python?

OpenPair คือ **Python Library Middleware** ไม่ใช่ Web App:

```python
# นี่คือ product จริง — ลูกค้า import ใน Python codebase ของตัวเอง
import openpair
result = openpair.route("Design a database schema")
```

เหตุผลที่ Python ไม่ใช่ JS:
1. **ลูกค้าเขียน Python** — AI Engineer ใช้ LangChain, PyTorch, HuggingFace ทั้งหมดอยู่ใน Python
2. **Phase 3 ต้องการ ML libs** — BERT, sentence-transformers, NumPy/FAISS มีเฉพาะใน Python
3. **AI SDK ดีที่สุดอยู่ใน Python** — OpenAI, Anthropic, LangChain เต็ม feature

> JavaScript จะถูกใช้ใน **Phase 4 Web Dashboard (React + TypeScript)** — แต่นั่นคือ "หน้าบ้านสำหรับ CTO ดู Analytics" ไม่ใช่ core product

### pip-only = ใช้ได้แค่ Python ใช่ไหม? เป็น painpoint ไหม?

**ใช่ ระยะสั้น — แต่ Phase 4 แก้ด้วย REST API:**

```
ตอนนี้ (Phase 1-2):        Phase 4:
Python dev  ✅              Python dev  ✅ pip install
Node.js dev ❌              Node.js dev ✅ fetch("api.openpair.io")
Go dev      ❌              Go dev      ✅ http.Get(...)
                            ทุกภาษา    ✅ REST API
```

Pattern นี้คือ standard ของ dev tools ทั่วไป (OpenAI, Stripe ก็เริ่มแบบนี้)

**อัปเดต 2026-07-28 — ข้อด้านบนนี้ล้าสมัยแล้ว** ตอนนี้ทำ real API calls ได้จริงแล้ว (`python/openpair/caller.py` รองรับ OpenAI, Anthropic, Google, Groq + Ollama fallback) มี CLI (`openpair` entry point) และมี API key management ผ่าน `ApiKeys`/`.env` ที่เหลือจริงๆ ตอนนี้คือ:
- ❌ ยังไม่มี REST API server (pip-only ยังจริงอยู่)
- ❌ ยังไม่มี decision cache สำหรับ prompt ซ้ำ

---

## ✅ สรุป: ทำแล้ว vs ยังขาด

> อัปเดต 2026-07-28 — ตารางเดิมล้าสมัยมาก (era ที่ยังไม่มี API call จริง) แก้ให้ตรงกับโค้ดปัจจุบัน

| ทำแล้ว ✅ | ยังขาด ❌ |
|---|---|
| Rule-based complexity scoring (`src/classifier.rs`) | BERT semantic embeddings |
| Model registry (`src/registry.rs`, 2026 models) | YAML config + hot-reload |
| Tier-based routing decision | Constraint checker + budget cap |
| PyO3 Python binding | LLM-as-a-Judge quality verification |
| จริง API calls (OpenAI/Anthropic/Google/Groq) | Decision Cache (LRU) |
| Ollama local fallback | Web Dashboard |
| CLI (`openpair` command, `--provider`, ฯลฯ) | REST API server (multi-language clients) |
| Thai benchmark วัดจริงแล้ว 4/10 model ใน registry (ดู `list_to_add.md`) | Thai benchmark ให้ครบทุก model (ติด rate limit / ไม่มี key) |
| CI (GitHub Actions: rust-test + python-test) | |
