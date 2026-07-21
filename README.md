# OpenPair

Intelligent AI router — automatically picks the cheapest model that can actually handle a given prompt, across OpenAI, Anthropic, Google, and Groq, with automatic fallback (including a local Ollama fallback) when a provider is rate-limited.

## ปัญหาที่แก้

เวลาใช้ LLM หลาย provider พร้อมกัน คนส่วนใหญ่จะ hardcode เลือก model เดียวไว้ตายตัว — ทำให้จ่ายแพงเกินไปสำหรับ prompt ง่ายๆ หรือได้คุณภาพไม่พอสำหรับ prompt ที่ซับซ้อน แถมพอ provider ไหน rate-limit ก็ request พังทันที

OpenPair แก้ปัญหานี้ด้วย:
- **ประเมินความซับซ้อนของ prompt** (1–10) แล้วเลือก model ที่ถูกที่สุดในระดับที่พอไหว แทนที่จะยิง GPT-4-class ทุกครั้ง
- **ตรวจจับภาษาไทย** และเลือก model ที่รองรับภาษาไทยได้ดี (มี Thai-quality benchmark วัดจริงอยู่ในโปรเจกต์)
- **Fallback อัตโนมัติ**: ถ้า provider หลักโดน rate limit (429) หรือ overloaded (503) จะลองยิง provider ถัดไปในเชนให้อัตโนมัติ ไม่ต้องเขียน retry logic เอง
- **Ollama เป็นด่านสุดท้าย**: ถ้า cloud provider ทั้งหมดโดน rate limit พร้อมกัน หรือไม่มี API key เลย แต่มี Ollama รันอยู่ในเครื่อง จะ fallback ไปใช้ local model โดยอัตโนมัติ

## Architecture

```
src/                      ← Rust core: complexity scoring, model registry, routing decision
  classifier.rs           ← ให้คะแนนความซับซ้อน 1–10 + ตรวจภาษาไทย
  registry.rs             ← รายชื่อ model ทุกตัว, tier, ราคา, thai_score
  router.rs                ← ตัดสินใจว่า tier ไหน + model ไหนเหมาะกับ prompt นี้
  main.rs                  ← demo binary (routing เฉยๆ ไม่เรียก API จริง)

python/openpair/           ← Python wrapper รอบ Rust core (ผูกกันผ่าน PyO3 + maturin)
  client.py                ← OpenPair class — .route() (ดูผลไม่เรียก API) / .call() (เรียกจริง + auto-fallback)
  caller.py                ← ยิง API จริงไปแต่ละ provider (openai / anthropic / google / groq / ollama)
  config.py                ← จัดการ API keys จาก .env / env vars
  errors.py                ← ตรวจว่า error ไหน retry ได้ (429/503) ไหน raise ทันที
  benchmark/                ← ระบบวัดคุณภาพภาษาไทยของแต่ละ model (20 test cases, 6 หมวด)
```

Routing decision (tier + model + ราคา) คำนวณฝั่ง Rust เพื่อความเร็ว ส่วนการเรียก API จริง, retry, fallback ทำฝั่ง Python

## ติดตั้ง

ต้องมีทั้ง Rust toolchain และ Python 3.9+

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

> **สำคัญ**: ทุกครั้งที่แก้โค้ดใน `src/*.rs` ต้องรัน `maturin develop --release` ใหม่เสมอ — แค่ `cargo build` ไม่พอ เพราะ Python import ตัว `.pyd`/`.so` ที่ build แยกกันคนละ target

## Configuration

```bash
cp .env.example .env
```

แล้วใส่ key อย่างน้อย 1 ตัว:

```
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AI...
GROQ_API_KEY=gsk_...          # optional, ฟรี + เร็วมาก
OLLAMA_BASE_URL=http://localhost:11434   # optional, default นี้อยู่แล้ว
OLLAMA_MODEL=llama3.1                    # optional, ต้อง `ollama pull` model นี้ไว้ก่อน
```

ไม่จำเป็นต้องมีครบทุก provider — มี key ตัวเดียวก็ใช้งานได้ ยิ่งมีหลาย provider ยิ่ง fallback ได้ดีขึ้น

## วิธีใช้ (Python)

```python
from openpair import OpenPair

client = OpenPair()  # อ่าน key จาก .env อัตโนมัติ

# เรียก API จริง — router เลือก model ให้เอง + auto-fallback ถ้าโดน rate limit
result = client.call("อธิบาย black hole ให้เข้าใจง่ายๆ")
print(result.response_text)
print(result.model_name, result.provider, f"${result.estimated_cost:.5f}")

# ดู routing decision อย่างเดียว ไม่เรียก API จริง ไม่เสียตังค์
decision = client.route("Write a Python class for a binary tree")
print(decision.model_name, decision.tier, decision.complexity_score)

# บังคับ provider เฉพาะเจาะจง
result = client.call("Hello!", preferred_provider="groq")

# กำหนด fallback order เอง (ปกติไม่ต้องทำ — มี default chain อยู่แล้ว)
result = client.call("Hello!", fallback_providers=["anthropic", "openai"])
```

**Default fallback chain** (ใช้เมื่อไม่ได้ระบุ `fallback_providers` เอง):
`[provider ที่ router เลือก] → groq → google → openai → anthropic → ollama (ถ้า ping เจอ server จริง)`

## วิธีใช้ (CLI)

```bash
openpair "อธิบาย recursion ให้เด็ก ป.6 ฟัง" --route-only
```
```
Model:    Claude 3 Haiku (claude-3-haiku-20240307)
Provider: anthropic
Tier:     mid
Score:    4/10
Reason:   Medium complexity — using a balanced quality/cost model [Thai].
```

`--route-only` แสดงแค่ผลการตัดสินใจ **ไม่เรียก API ไม่ต้องมี key** — ใช้ดูว่า router คิดยังไง

```bash
openpair "อธิบาย recursion"                      # เรียกจริง + auto-fallback
openpair "Hello!" --provider groq                 # บังคับ provider
openpair "สรุปให้หน่อย" --system "ตอบสั้นๆ"        # ใส่ system prompt
openpair "Hello!" --max-tokens 512                # จำกัดความยาว (default 2048)
```

คำตอบออก stdout ส่วนข้อมูล model/ราคา/latency ออก stderr — เพราะฉะนั้น
`openpair "..." > answer.txt` จะได้แต่คำตอบล้วนๆ ในไฟล์

## Rust demo binary (routing preview เท่านั้น)

```bash
cargo run --bin openpair-demo -- "your prompt here"
```

แสดงแค่ผล routing decision (score, tier, model, ราคาประมาณ) **ไม่เรียก API จริง** — ใช้ดูว่า router ตัดสินใจยังไงแบบเร็วๆ โดยไม่ต้องมี API key

## Benchmark คุณภาพภาษาไทย

```bash
python run_benchmark.py                                    # รันทุก model default (Gemini)
python run_benchmark.py --models gemini-2.5-flash           # เจาะจง model
python run_benchmark.py --category qa                       # เจาะจงหมวด
python run_benchmark.py --detail                            # แสดงผลละเอียดทุก test case
```

ผลจะถูก suggest กลับมาเป็น `thai_score` ให้ไปอัปเดตใน `src/registry.rs` เอง (ยังไม่ auto-patch)

## Testing

```bash
cargo test                    # Rust — 16 tests
pytest -m "not live"          # Python — 77 tests (mocked, ไม่ต้องมี API key)
pytest -m live                # 5 tests ที่เรียก API จริง (ต้องมี key จริง, เสียเงินจริง)
```

> **หมายเหตุ**: พิมพ์ `pytest` เฉยๆ (ไม่ใส่ `-m`) จะพยายามรันทั้ง 82 ตัว — ตัว live test ที่ไม่มี key ตรงกันจะถูก skip อัตโนมัติ แต่ตัวที่มี key จริงใน `.env` (เช่น groq/google) **จะยิง API จริงและเสียเงินจริง** ไม่ใช่แค่ "รวมไว้เฉยๆ" ถ้าไม่ได้ตั้งใจจะเสียเงิน ให้ใส่ `-m "not live"` เสมอ

## สถานะปัจจุบัน / ข้อจำกัดที่รู้อยู่แล้ว

- **CLI พร้อมใช้แล้ว** — `openpair "..."` เป็นคำสั่ง shell จริง (`pyproject.toml` มี `[project.scripts]` → `openpair = "openpair.cli:main"`) ดูวิธีใช้ในหัวข้อ "วิธีใช้ (CLI)" ด้านบน
- **OpenRouter** ยังไม่ implement (มีแผนอยู่ใน `list_to_add.md`)
- **Ollama fallback** implement แล้วแต่ยังไม่เคยทดสอบกับ Ollama server จริง (test ทั้งหมดเป็น mock ผ่าน `FakeOllama` fixture ใน `tests/conftest.py` — ไม่ใช่ server จริง) — ถ้าเจอบั๊กให้เริ่มเช็คตรงนี้ก่อน
- `gemini-2.5-flash` free tier มี quota **20 requests/วัน ต่อ project ต่อ model** — รัน benchmark ซ้ำในวันเดียวกันจะชน quota แน่นอน
- `src/registry.rs` มีทั้ง `thai_score` ที่มาจาก benchmark จริงและค่าประมาณ (ดู comment ในไฟล์) — อย่าเชื่อว่าทุกค่าวัดจริงหมด

## Roadmap

ดู `list_to_add.md` สำหรับแผนที่ยังไม่ได้ทำ (OpenRouter, YAML-based model config)
