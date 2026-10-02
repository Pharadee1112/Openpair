# OpenPair — สิ่งที่จะเพิ่มเติม (Feature Backlog)

> ไฟล์นี้เก็บ feature และ plan ที่อยากทำในอนาคต ยังไม่ได้อยู่ใน SRD หลัก  
> Last updated: 2026-10-02

---

## สถานะปัจจุบัน (2026-10-02) — เริ่มอ่านตรงนี้

**ทำได้ต่อ (ไม่ต้องเสียเงิน):**
- [ ] **OpenRouter: ทดสอบกับของจริง + เพิ่ม model ใน registry** — โค้ดฝั่ง caller/config เสร็จแล้ว (ดู DONE 2026-10-02) ต้องมี `OPENROUTER_API_KEY` ใน `.env` ก่อน (ตอนนี้ยังไม่มี) แล้วค่อย: เช็ค model id จริงจาก `https://openrouter.ai/api/v1/models` → benchmark ด้วย `--models openrouter:<id>` → ใส่ใน `registry.rs` พร้อม thai_score ที่วัดจริง
- [ ] **ตรวจความหมายสแลง `qa_52` ("ฮ้อป") กับ `qa_53` ("คลินิกจัดฟันใกล้ฉัน")** — ทั้ง 3 model ตอบไม่ตรง keyword และแต่ละตัวเดาความหมายไม่เหมือนกัน ต้องให้คนไทยยืนยันว่าความหมายที่ตั้งไว้ถูกจริงไหม ถ้าถูก = model ไม่รู้จักสแลงใหม่ (เคสดี เก็บไว้) ถ้าผิดหรือไม่มีคนใช้จริง = แก้ keyword หรือเปลี่ยนเคส
- [ ] ทบทวนเคสข่าว/สแลงทุก 6–12 เดือน (ข้อมูลเก่าเร็ว) — รอบถัดไปประมาณ มี.ค.–ก.ย. 2570

**ติดอยู่ / พักไว้:**
- [ ] Ollama กับของจริง — ต้องติดตั้ง Ollama เองก่อน (user ไม่ให้ติดตั้งอัตโนมัติ)
- [ ] `gemini-3.1-pro-preview` — ต้องเปิด billing (เสียเงิน) user พักไว้ 2026-10-02
- [ ] Fine-tuning — รอ GPU มหาวิทยาลัย ห้ามรันบนเครื่องนี้ แผนอยู่ที่ `finetune/README.md`

**ตัดสินใจแล้ว:** benchmark แค่ Gemini + Groq (free tier) ไม่วัด OpenAI/Anthropic — thai_score ของ `claude-*` / `gpt-*` เป็นค่าประมาณ

**วัด thai_score จริงแล้ว (registry.rs):** `gemini-3.1-flash-lite` 9, `openai/gpt-oss-120b` 9, `openai/gpt-oss-20b` 9 (ชุด full 600 เคส), `gemini-3.6-flash` 6 (ชุด core 20 เคส) — ที่เหลือเป็นค่าประมาณ

---

## DONE — รันชุด full + calibrate keyword + OpenRouter caller (2026-10-02)

- [x] **รันชุด full 600 เคสครบ** — `gemini-3.1-flash-lite` 600/600 (`benchmark_results_gemini_full.json`), Groq `gpt-oss-120b` 600/600 + `gpt-oss-20b` 598/600 (`benchmark_results_groq_full.json`) — 2 เคสสุดท้ายของ 20b ได้คำตอบว่างทุกครั้ง (EmptyResponse) ถือว่าจบที่ 598 คะแนนไม่เปลี่ยน — commit `8d89ab1` push แล้ว
- [x] **registry.rs**: `gpt-oss-20b` thai_score 8→9 (`b7d1eb5`), 120b / flash-lite คง 9 — รัน `maturin develop --release` แล้ว CLI ใช้ค่าใหม่
- [x] **ตัด `gemini-3.6-flash` ออกจากชุด full** (free quota น้อยเกินไป) คะแนนคง 6 จากชุด core
- [x] **Calibrate expected_keywords** — จาก 600 เคส มีแค่ **3 เคส** ที่ทั้ง 3 model ไม่ผ่าน (ทุกเคสพลาดที่ keyword ไม่ใช่ thai_ratio/length) = keyword ส่วนใหญ่ใช้ได้:
  - `cls_50` (ดาต้าเซ็นเตอร์ใช้ไฟ 270 MW / ค่าไฟแพง) — เฉลยเดิม `เทคโนโลยี` แต่ 2 model ตอบ `พลังงาน` ซึ่งสมเหตุสมผลกว่า → **แก้เฉลยเป็น `พลังงาน` แล้ว** (ผลใน `*_full.json` ยังคิดด้วยเฉลยเดิม ต่างกันไม่ถึง 0.02 คะแนน/model ไม่ได้ rescore)
  - `qa_52`, `qa_53` (สแลง) — ยังไม่แก้ ต้องให้คนตรวจ (ดูสถานะปัจจุบันด้านบน)
- [x] **OpenRouter (ฝั่งโค้ด)** — `call_openrouter()` ใน `caller.py` (OpenAI SDK + `base_url=https://openrouter.ai/api/v1`), `ApiKeys.openrouter` / `OPENROUTER_API_KEY` ใน `config.py`, `OpenPair(api_keys={"openrouter": ...})`, `run_benchmark.py --models openrouter:<org/model>` (ต้องมี prefix เพราะ id แบบ `org/model` ชนกับ Groq) — เทส mock ใน `tests/test_client.py::TestOpenRouter` + `tests/test_run_benchmark.py`, `pytest -m "not live"` ผ่าน 118/118
  - **ยังไม่ได้เพิ่ม model OpenRouter ใน `registry.rs` โดยตั้งใจ** — router เลือก model ถูกสุดใน tier เป็น default ถ้าใส่ model ฟรี/ราคาต่ำโดยยังไม่ได้วัด thai_score มันจะชนะทุก tier ทันที และ id ที่ไม่ได้เช็คกับ API จริงอาจ 404 แบบที่เคยเจอกับ `gemini-3.1-pro` — เพราะเหตุนี้ OpenRouter จึงยังไม่อยู่ใน fallback chain ของ `client.call()` ด้วย ตอนนี้ใช้ได้ผ่าน `make_call()` / `run_benchmark.py` เท่านั้น

---

## DONE — ขยาย Thai benchmark เป็น 600 เคส (2026-09-28)

- [x] **ชุด `full` 100 เคสต่อหมวด** (core 20 + ใหม่ 580) เก็บที่ `python/openpair/benchmark/data/<category>.json`, โหลดผ่าน `get_suite("full")`, รันด้วย `python run_benchmark.py --suite full` — default ยังเป็น `core` (20 เคส) เพื่อไม่ให้ผลเก่าเทียบไม่ได้และไม่เปลือง quota
- [x] เนื้อหา: ข่าวปัจจุบัน ก.ย. 2569 ~140 เคส (ใส่เนื้อข่าวในโจทย์), สแลง/ภาษาวัยรุ่น ~110 เคส, สำนวนไทย + ภาษาถิ่น, โค้ดบริบทไทย
- [x] test ใหม่ `TestFullSuite` ใน `tests/test_benchmark.py` (100 เคส/หมวด, id/prompt ไม่ซ้ำ, ป้าย classification ไม่เป็น substring กัน)
- [x] `run_benchmark.py` บังคับ stdout เป็น UTF-8 แล้ว — ไม่ crash บน Windows console ภาษาไทย (cp874) อีก
- [x] ~~ยังไม่ได้รันชุด full กับ model จริง~~ — รันครบและ calibrate keyword แล้ว 2026-10-02 (ดู DONE ด้านบน)
- ทบทวนเคสข่าว/สแลงทุก 6–12 เดือน → ย้ายไปอยู่ใน "สถานะปัจจุบัน"

---

## DONE — รัน benchmark จริง 5 model + อัปเดต thai_score + เจอ/แก้ model id ผิด + `--version` flag (2026-07-28)

> รันจริงด้วย `run_benchmark.py` (20 Thai test cases ต่อ model) ใช้ `GOOGLE_API_KEY` + `GROQ_API_KEY` ที่มีอยู่ใน `.env` — ไม่มี `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` เลยยังวัดฝั่ง OpenAI/Anthropic ไม่ได้

- [x] **Groq ทั้ง 3 model** — `llama-3.1-8b-instant` (avg 8.60/10, thai_score 8→**9**), `llama-3.3-70b-versatile` (avg 8.44/10, thai_score 9→**8**), `openai/gpt-oss-120b` (avg 9.15/10, thai_score 8→**9**) → บันทึกที่ `benchmark_results_groq_2026.json`, อัปเดต `src/registry.rs` แล้ว
- [x] **Gemini 2 model** — `gemini-3.1-flash-lite` (avg 9.01/10, thai_score ยืนยัน **9** ตรงกับค่าเดิม), `gemini-3.6-flash` (avg 5.74/10, thai_score เดิม (ประมาณ) 4 → จริง **6**) → บันทึกที่ `benchmark_results_gemini_2026.json` / `benchmark_results_gemini_2026_part2.json` — ผลคือ quota 20 request/วันเป็น **ต่อ model** ไม่ใช่รวมทั้ง project จึงรันได้มากกว่า 1 model/วัน
- [x] **เจอบั๊ก: `gemini-3.1-pro` ไม่มีจริงใน Google API** — เรียกแล้วได้ 404 NOT_FOUND ทุก request (ไม่ใช่ปัญหาคุณภาพ เป็น model id ผิด) เช็ค `client.models.list()` จริงแล้วพบว่าตัวจริงชื่อ `gemini-3.1-pro-preview` → แก้ id ใน `src/registry.rs` แล้ว **ไม่ได้** เอา thai_score=1 ที่ระบบแนะนำมาใส่ (มันมาจาก error ล้วนๆ ไม่ใช่คุณภาพจริง) thai_score ของ `gemini-3.1-pro-preview` ยังเป็นค่าประมาณเดิม (7) รอวัดจริงพรุ่งนี้
- [ ] **`gemini-3.1-pro-preview` ยังไม่ได้วัดจริง** — พยายามรันแล้วแต่ค้างนาน (~50 นาทีไม่จบ, 20 cases) น่าจะติด rate limit ของ preview model ที่เข้มกว่าปกติ → ยกเลิก (kill process) แล้วตามคำขอ user ให้ **รันใหม่วันถัดไป** — **ลองรันอีกรอบ 2026-09-28 → ยังรันไม่ได้**: error 429 ระบุ `limit: 0` (free_tier_requests / input_token_count, model: gemini-3.1-pro) = free tier **ไม่มี quota ให้ model นี้เลย** ไม่ใช่ quota วันนั้นหมด รอวันถัดไปก็ไม่ช่วย ต้องเปิด billing (paid tier) ใน Google AI Studio ก่อนถึงจะวัดได้ — ไม่ได้เอา thai_score=1 ที่ระบบแนะนำไปใส่ (มาจาก error ล้วน)
- [x] **ลบผลลัพธ์เก่าที่อ้าง model ตายแล้ว** — `benchmark_results.json` และ `benchmark_results_gemini25flash.json` อ้าง `gemini-2.5-flash*` ที่ไม่มีใน registry แล้ว ลบทิ้ง แทนที่ด้วยไฟล์ 2026
- [x] **แก้ README** — บรรทัด "GPT-4-class" เปลี่ยนเป็นชื่อรุ่นปัจจุบัน, ระบุชัดว่า Thai benchmark วัดจริงแล้วกี่ model ไม่ใช่ "วัดจริงหมดแล้ว"
- [x] **แก้ ARCHITECTURE.md** — ลบ/แก้ตารางเก่าที่บอกว่า "ยังเรียก API จริงไม่ได้" (ล้าสมัยมาก ตอนนี้เรียกได้จริงทั้ง 4 provider + Ollama fallback + CLI) เพิ่มบรรทัด อัปเดต 2026-07-28
- [x] **`--version` flag** — เพิ่ม `__registry_snapshot__ = "2026-07-28"` ใน `python/openpair/__init__.py` + `--version` ใน `cli.py` (argparse `action="version"`), `pip install -e .` แล้ว ยืนยันด้วย `openpair --version` → `openpair 0.1.0 (registry snapshot: 2026-07-28)`, `pytest tests/test_cli.py` ผ่านครบ 8/8

**สถานะ registry.rs หลัง 2026-07-28 (ล้าสมัยแล้ว — ดู "สถานะปัจจุบัน" ด้านบน; llama ทั้ง 2 ตัวถูก Groq ปลดไปแล้ว 2026-08-28):**
- วัดจริงแล้ว: `llama-3.1-8b-instant`, `llama-3.3-70b-versatile`, `openai/gpt-oss-120b`, `gemini-3.1-flash-lite`, `gemini-3.6-flash` (5/10)
- ยังเป็นค่าประมาณ: `claude-haiku-4-5`, `gpt-5.4-nano`, `claude-sonnet-5`, `gpt-5.5`, `claude-opus-5` (ไม่มี API key OpenAI/Anthropic), `gemini-3.1-pro-preview` (free tier quota = 0 ต้องเปิด billing ก่อน)

---

## DONE — Prompt cache (2026-07-28)

- [x] **In-memory LRU cache สำหรับ prompt ซ้ำ** — เพิ่ม `_cache: OrderedDict` ใน `OpenPair.__init__` (`python/openpair/client.py`), key คือ `(prompt, preferred_provider, system, max_tokens)` ครบทุกตัวถึงจะนับว่าเหมือนกัน ค่า default `cache_size=128` ตั้งค่าได้ผ่าน `OpenPair(cache_size=...)`. `call()` มี param `use_cache: bool = True` (ปิดได้ต่อ call ด้วย `use_cache=False`)
- [x] เพิ่ม field `from_cache: bool` ใน `CallResult` (`caller.py`) — cache hit จะ `estimated_cost` เป็น 0.0 (ไม่ได้ยิง API จริง ไม่มีค่าใช้จ่าย)
- [x] เขียนเทส 4 ตัวใน `tests/test_client.py::TestCache` — cache hit ไม่เรียก API ซ้ำ, prompt ต่างกันไม่ hit, `use_cache=False` บังคับเรียกใหม่, cache เต็มแล้ว evict ตัวเก่าสุด (LRU) — ผ่านหมด, รวมทั้ง suite 81/81 ผ่าน (`pytest -m "not live"`), cargo test 21/21 ผ่าน
- **หมายเหตุ:** เป็น per-instance cache (อยู่ใน object `OpenPair` แต่ละตัว) ไม่ใช่ shared/global หรือ persist ข้าม process — ถ้าอยากได้ persistent cache (เช่น เขียนลง disk/redis) ต้องทำเพิ่ม ยังไม่ได้ทำตอนนี้

---

## ยังไม่ได้ทำ (blocked หรือ user บอกให้ข้ามไปก่อน — 2026-07-28, ยังเป็นจริง ณ 2026-10-02)

- [ ] **Ollama fallback กับของจริง** — เครื่องนี้ไม่มี Ollama ติดตั้งเลย (`ollama` command not found ทั้ง bash/PowerShell) เทสตอนนี้ผ่านแค่ mock (`tests/test_ollama_fallback.py` ใช้ `FakeOllama` fixture) ยังไม่เคยพิสูจน์กับ server จริง — user เลือก "ข้ามไปก่อน" (ไม่ให้ติดตั้ง Ollama อัตโนมัติ) ถ้าจะทำต่อ ต้องติดตั้ง Ollama เองก่อน (`ollama pull llama3.2` แล้วรัน `ollama serve`) แล้วค่อยรัน integration test จริง
- [ ] **`gemini-3.1-pro-preview` ยังไม่ได้วัดจริง** — ลองรันแล้วค้าง ~50 นาทีไม่จบ (rate limit ของ preview model) ยกเลิกไปแล้ว ตาม user บอกให้รันใหม่วันถัดไป — รันใหม่ 2026-09-28 แล้ว: free tier `limit: 0` ต้องเปิด billing ก่อน — **2026-10-02: user ไม่เปิด billing (เสียเงิน) พักไว้ก่อน**

---

## DONE — CI fix + Registry 2026 refresh + Classifier accuracy (2026-07-25)

> ตรวจโค้ดจริงแล้ว ตรงกับที่รายงานทั้ง 3 ข้อ — commit `8360447`, `9d58553`, `048ae65`, `d190394`, ทั้งหมด push แล้ว (`git status` clean)

- [x] **ซ่อม CI** — `maturin develop` พังบน CI เพราะต้องมี venv ที่ไม่มีใน CI → เปลี่ยนเป็น `pip install ".[dev]"` ใน `.github/workflows/ci.yml` — ยืนยันแล้วว่าไฟล์ workflow ใช้ `pip install ".[dev]"` จริง (rust-test + python-test)
- [x] **อัปเดต `src/registry.rs`** — โมเดล 2024 ตายหมด เปลี่ยนเป็นรุ่นปัจจุบัน (Haiku 4.5, Sonnet 5, Opus 5, GPT-5.4 Nano, GPT-5.5, Gemini 3.1 Flash-Lite/3.6 Flash/3.1 Pro, Groq เดิม) — ยืนยันแล้วว่าไม่มี id ปลอม `claude-3-5-sonnet-top` เหลืออยู่ในไฟล์
- [x] **แก้ `src/classifier.rs`** — ยืนยันแล้วว่ามีครบทั้ง 5 จุด: length buckets ละเอียดขึ้น (8 bucket แยก Thai char-count กับ English word-count), keyword ใช้ stem+tokenize+`starts_with`, น้ำหนัก complex keyword เพิ่มเป็น 0.8, ภาษาไทยข้าม avg-word-length และใช้ char count แทน, เพิ่ม test ครบ (10 test functions รวม `complex_13_word_sentence_scores_moderately_high`)

**หมายเหตุแก้ไขความเข้าใจผิด:** ที่คิดว่า `--version` flag "โค้ดเสร็จแล้วแค่ยังไม่ push" — ตรวจแล้วไม่จริง ไม่มี `__registry_snapshot__` ใน `__init__.py` และไม่มี `--version` ใน CLI เลย ไม่มี commit ไหนเคยเพิ่มด้วย ต้อง**เขียนใหม่ทั้งหมด** ไม่ใช่แค่ push

---

## ยังค้างอยู่ (ของ 2026-07-28 — ดู "สถานะปัจจุบัน" ด้านบนแทน)

- [x] ~~เพิ่ม `--version` flag ให้ CLI จริง~~ — ทำแล้ว 2026-07-28: เพิ่ม `__registry_snapshot__ = "2026-07-28"` ใน `python/openpair/__init__.py` + `--version` ใน `cli.py` (argparse `action="version"`), `pip install -e .` แล้ว, ยืนยันด้วย `openpair --version` → `openpair 0.1.0 (registry snapshot: 2026-07-28)`, `pytest tests/test_cli.py` ผ่านครบ 8/8 — ยังไม่ได้ commit/push
- [x] ~~อัปเดต README~~ — แก้แล้ว 2026-07-28 (ดู DONE ด้านล่าง)
- [x] ~~รัน benchmark~~ — รันแล้ว 4/10 model จริง 2026-07-28 (Groq ทั้ง 3 + gemini-3.1-flash-lite), อัปเดต `thai_score` ใน `registry.rs` แล้วด้วยผลจริง (ดู DONE ด้านล่าง)
- [x] ~~ตัดสินใจเรื่อง score ที่เหมาะสม~~ — **ไม่ต้องตัดสินใจแล้ว:** Groq ปลด `llama-3.3-70b-versatile` ไปเมื่อ 2026-08-28 (ลบออกจาก registry แล้ว) — ข้อความเดิม: "Design a distributed database..." ตอนนี้มีผลจริงแล้วว่า Llama 3.3 70B ได้ avg 8.44/10 แต่ทำ code_thai แย่สุด (6.0/10, `code_01` ได้ 3.0 kw=0%) → เป็นสัญญาณว่า Llama 3.3 70B ไม่ควรถูกดันขึ้น tier สำหรับงาน code — รอ human ตัดสินใจ ไม่เดาเอง
- [ ] **(พักไว้ — อนาคต) วัด `gemini-3.1-pro-preview`** — free tier ให้ quota = 0 (เช็ค 2026-09-28) ต้องเปิด billing (เสียเงิน ~$5–15 สำหรับชุด full) — user ตัดสินใจ 2026-10-02 ว่ายังไม่ทำ รอไว้ถ้ากลับมาทำเรื่องนี้ต่อในอนาคต, thai_score คงค่าประมาณ 7 ไว้
- **ตัดสินใจแล้ว (2026-10-02): ไม่วัด OpenAI/Anthropic** — benchmark แค่ Gemini + Groq ก็พอ, thai_score ของ `claude-*` / `gpt-*` ใน registry.rs คงเป็นค่าประมาณต่อไป
- [x] ~~Custom benchmark (ให้ user เพิ่ม test case เอง)~~ — ทำแล้ว: `load_custom_cases()` ใน `python/openpair/benchmark/dataset.py` (โหลด test case จาก JSON, มี validation + `custom_cases.example.json`) export ไว้ใน `benchmark/__init__.py` แล้ว (ตรวจโค้ดจริง 2026-07-28)

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

> ล้าสมัย — ค่าปัจจุบัน (2026-10-02): simple `gemini-3.1-flash-lite` / medium `claude-haiku-4-5` / complex `claude-sonnet-5`

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
- [x] ~~รัน benchmark ครบทุก model~~ — รันได้ 4/10 แล้ว (ดู DONE 2026-07-28 ด้านบน), เหลืออีก 6 model รอ API key/quota
- [x] ~~อัปเดต thai_score ใน registry.rs ด้วยผลจริง~~ — อัปเดตแล้วสำหรับ 4 model ที่วัดได้ (ดู DONE 2026-07-28 ด้านบน)
- [x] ~~Custom benchmark (ให้ user เพิ่ม test case เอง)~~ — ทำแล้ว: `load_custom_cases()` ใน `dataset.py`

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

- [x] Unit test: call_openrouter() mock response — `tests/test_client.py::TestOpenRouter` (2026-10-02)
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

> ~~Next session: เริ่มที่ OpenRouter ก่อน แล้วค่อยทำ Ollama fallback~~ — OpenRouter caller + Ollama fallback (mock) ทำแล้ว ดู "สถานะปัจจุบัน" ด้านบนสำหรับงานถัดไป
