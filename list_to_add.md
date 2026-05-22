# OpenPair — สิ่งที่จะเพิ่มเติม (Feature Backlog)

> ไฟล์นี้เก็บ feature และ plan ที่อยากทำในอนาคต ยังไม่ได้อยู่ใน SRD หลัก  
> Last updated: 2026-05-22

---

## 🇹🇭 Thai Language Benchmark System

> **สำคัญมาก** — OpenPair ต้องการ benchmark ภาษาไทยโดยเฉพาะ  
> เพราะ model แต่ละตัวมีความสามารถภาษาไทยไม่เท่ากัน และนี่คือ competitive advantage ของเรา

---

### 📋 แผนที่จะทำ

#### 1. Thai Benchmark Core (`thai_benchmark/`)

สร้าง benchmark ภาษาไทยมาตรฐานสำหรับ task ที่ OpenPair ต้องตัดสินใจ routing:

| Task Category | ตัวอย่าง Prompt ภาษาไทย | วัด Metric อะไร |
|---|---|---|
| **Classification** | "จัดหมวดหมู่ข้อความนี้: ..." | Accuracy, F1 Score |
| **Summarization** | "สรุปบทความนี้เป็นภาษาไทย: ..." | ROUGE Score, ความสั้น-กระชับ |
| **Q&A** | "ตอบคำถามนี้เป็นภาษาไทย: ..." | Correctness, ความเป็นธรรมชาติ |
| **Translation** | "แปลข้อความนี้เป็นภาษาไทย: ..." | BLEU Score, ความถูกต้อง |
| **Creative Writing** | "เขียนเรื่องสั้นภาษาไทย: ..." | Fluency, Coherence |
| **Code + Thai** | "อธิบาย code นี้เป็นภาษาไทย: ..." | Technical Accuracy |

---

#### 2. Per-Model Benchmark Results

รัน benchmark กับทุก model ใน registry แล้วเก็บผล:

```
Model               Thai Accuracy   Thai Fluency   Cost/1K tokens   Thai Score
─────────────────────────────────────────────────────────────────────────────
GPT-4o              ?%              ?/10            $X.XX            ?
GPT-4o-mini         ?%              ?/10            $X.XX            ?
Claude 3.5 Sonnet   ?%              ?/10            $X.XX            ?
Claude 3 Haiku      ?%              ?/10            $X.XX            ?
Gemini 1.5 Pro      ?%              ?/10            $X.XX            ?
Gemini 1.5 Flash    ?%              ?/10            $X.XX            ?
```

> เป้าหมาย: ให้ OpenPair routing รู้ว่า task ภาษาไทยควรส่งไป model ไหน

---

#### 3. Customizable Benchmark (`custom_benchmark/`)

ให้ user เพิ่ม benchmark เองได้ เหมาะกับ domain เฉพาะ:

```python
# ตัวอย่าง Custom Thai Benchmark
from openpair.benchmark import ThaiCustomBenchmark

bench = ThaiCustomBenchmark()

# เพิ่ม test case เอง
bench.add_case(
    prompt="อธิบาย quantum computing เป็นภาษาไทยง่าย ๆ",
    expected_keywords=["ควอนตัม", "บิต", "ซ้อนทับ"],
    category="technical_thai",
    difficulty="medium"
)

# รัน benchmark กับ model ที่เลือก
results = bench.run(models=["gpt-4o-mini", "claude-haiku"])
bench.report()  # แสดงผลตาราง
```

---

#### 4. Thai Benchmark CLI

```bash
# รัน Thai benchmark มาตรฐาน
openpair benchmark --lang th

# รัน เฉพาะ model ที่ต้องการ
openpair benchmark --lang th --models gpt-4o-mini,claude-haiku

# รัน custom benchmark จากไฟล์
openpair benchmark --custom ./my_thai_tests.yaml

# export ผลลัพธ์
openpair benchmark --lang th --output report.json
```

---

#### 5. Thai Routing Enhancement

หลังจากได้ผล benchmark แล้ว → นำมาปรับ routing logic:

```python
# ถ้า task เป็นภาษาไทย + complexity ต่ำ → ส่งไป model ที่ Thai Score ดีที่สุดราคาถูก
# ถ้า task เป็นภาษาไทย + complexity สูง → ส่งไป model ที่ Thai Accuracy สูงสุด

THAI_ROUTING_PRIORITY = {
    "simple_thai": "gemini-flash",      # ถูก + Thai OK
    "medium_thai": "claude-haiku",       # กลาง + Thai ดี
    "complex_thai": "claude-sonnet",     # แพงกว่า + Thai ดีมาก
}
```

---

### 🧪 Test Plan

- [ ] สร้าง Thai test dataset ขั้นต่ำ 100 cases ต่อ category
- [ ] รัน automated benchmark ทุก model ใน registry
- [ ] เปรียบเทียบ Thai performance vs cost
- [ ] Integration test: Thai input → routing → correct model
- [ ] Regression test: หลัง update ผล benchmark ต้องไม่แย่ลง

---

### 📦 Files ที่จะสร้าง

```
openpair/
├── benchmark/
│   ├── __init__.py
│   ├── thai_benchmark.py      ← Thai standard benchmark
│   ├── custom_benchmark.py    ← User-defined benchmark
│   ├── runner.py              ← รัน benchmark กับ model
│   └── reporter.py            ← แสดงผลตาราง/export
├── data/
│   └── thai_test_cases/
│       ├── classification.yaml
│       ├── summarization.yaml
│       ├── qa.yaml
│       └── translation.yaml
└── tests/
    └── test_thai_benchmark.py
```

---

### 🎯 Priority

**Priority: HIGH** — เพราะ:
1. OpenPair จะโดดเด่นจาก competitor ถ้ามี Thai-aware routing
2. ตลาดไทยยังไม่มีเครื่องมือแบบนี้
3. ใช้ข้อมูล benchmark จริงทำให้ routing decision น่าเชื่อถือขึ้น

---

> 💡 หมายเหตุ: เริ่มทำหลัง Phase 2 (API calls จริงได้แล้ว) เพราะต้องเรียก model จริงเพื่อวัดผล
