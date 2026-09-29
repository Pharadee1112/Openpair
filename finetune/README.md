# OpenPair — แผน Fine-tuning ภาษาไทย

> สถานะ: **เตรียมการ ยังไม่เทรน** (ตัดสินใจ 2026-09-29) — รอใช้ GPU ฟรีของมหาวิทยาลัย
> **ห้ามรัน fine-tuning บนเครื่อง dev** (RAM/GPU ไม่พอ) — เครื่องนี้ใช้แค่เตรียมข้อมูล + รัน benchmark ผ่าน API

ลำดับงาน:

1. Baseline benchmark (600 เคส) — `run_benchmark.py --suite full` → `benchmark_results_*_full.json`
2. ข้อมูล GPU มหาวิทยาลัย — ถามตาม [checklist ด้านล่าง](#2-คำถามที่ต้องถามมหาวิทยาลัย)
3. เลือก base model — ตาม [ตาราง VRAM](#3-เลือก-base-model)
4. Training dataset — [`data/train_seed.jsonl`](data/train_seed.jsonl) + ตรวจด้วย `python finetune/check_dataset.py`
5. Script เทรน (LoRA/QLoRA) — ทดสอบบน Colab ก่อน *(ยังไม่ทำ)*
6. วัดผลหลังเทรน — serve ผ่าน Ollama/vLLM แล้วรัน benchmark ชุดเดิม เทียบกับ baseline *(ยังไม่ทำ)*

-
## 2. คำถามที่ต้องถามมหาวิทยาลัย

ส่งคำถามเหล่านี้ให้ฝ่ายไอที/ผู้ดูแล cluster — คำตอบข้อ 1 ใช้เลือก base model ในข้อ 3

| # | คำถาม | ทำไมต้องรู้ |
|---|---|---|
| 1 | GPU รุ่นอะไร, **VRAM ต่อการ์ดกี่ GB**, ใช้ได้พร้อมกันกี่การ์ด | กำหนดขนาดโมเดลที่เทรนได้ (สำคัญที่สุด) |
| 2 | จำกัดเวลาใช้ต่อ job / ต่อสัปดาห์เท่าไหร่ | เทรน 1 รอบใช้หลายชั่วโมง — ต้องรู้ว่าต้อง checkpoint แบ่งช่วงไหม |
| 3 | ใช้ผ่านระบบคิวแบบไหน (SLURM, Jupyter, SSH ตรง) | ต้องเขียน job script ให้ตรงระบบ |
| 4 | เครื่องออกอินเทอร์เน็ตได้ไหม (Hugging Face, pip) | ถ้าไม่ได้ ต้องโหลดโมเดล/แพ็กเกจไปวางล่วงหน้า |
| 5 | พื้นที่ดิสก์ต่อ user กี่ GB | โมเดล 8B ≈ 16 GB, checkpoint ระหว่างเทรนกินเพิ่มอีกหลายเท่า |
| 6 | CUDA version / มี container (Docker, Apptainer/Singularity) ไหม | เลือกเวอร์ชัน PyTorch ให้ตรง |
| 7 | ติดตั้งแพ็กเกจเองได้ไหม (conda/venv ใน home) | transformers, peft, bitsandbytes, trl |
| 8 | มีข้อห้ามเรื่องการใช้ API ภายนอก / license โมเดลไหม | บางที่จำกัดการใช้งานเชิงพาณิชย์ |

---

## 3. เลือก base model

ต้องเป็นโมเดล **open-weights** (โหลดไฟล์โมเดลมาเทรนเองได้) — Gemini / Groq API เทรนแบบนี้ไม่ได้

ประมาณการ VRAM สำหรับ **QLoRA** (4-bit + LoRA, batch เล็ก, context ~2k token) — ตัวเลขคร่าวๆ ใช้วางแผน ไม่ใช่สเปกตายตัว:

| VRAM ที่มี | ขนาดโมเดลที่เหมาะ | ตัวเลือก (เช็ครุ่นล่าสุดบน Hugging Face ตอนจะเทรน) |
|---|---|---|
| 12–16 GB | 3–8B | Typhoon (โมเดลไทยของ SCB10X), Qwen ขนาดเล็ก, Llama 8B |
| 24 GB | 8–14B | Typhoon / OpenThaiGPT รุ่นกลาง, Qwen ~14B |
| 40–48 GB | 14–32B | Qwen ~32B, `gpt-oss-20b` |
| 80 GB+ | 32–70B | Llama 70B-class, Qwen รุ่นใหญ่ |

**แนะนำรอบแรก:** โมเดลที่ถูก pretrain ภาษาไทยมาแล้ว (Typhoon / OpenThaiGPT) ขนาด 7–8B — เทรนเร็ว, พอดี VRAM ส่วนใหญ่, เริ่มจากฐานภาษาไทยที่ดีอยู่แล้ว ถ้าผลดีค่อยขยับขนาด

ก่อนเลือกให้เช็ค: license (ใช้ต่อได้ไหม), รองรับ chat template, และรัน **baseline benchmark กับตัว base model เองก่อนเทรน** — เทียบกับ gpt-oss-120b / gemini-3.1-flash-lite ว่าห่างกันแค่ไหน

---

## 4. Training dataset

ไฟล์: `finetune/data/*.jsonl` — 1 บรรทัด = 1 ตัวอย่าง รูปแบบ chat (ใช้กับ `trl` SFTTrainer / chat template ได้ตรง):

```json
{"id": "train_qa_001", "category": "qa", "source": "handwritten", "messages": [
  {"role": "system", "content": "คุณเป็นผู้ช่วยที่ตอบเป็นภาษาไทยอย่างถูกต้องและกระชับ"},
  {"role": "user", "content": "..."},
  {"role": "assistant", "content": "..."}
]}
```

| field | บังคับ | คำอธิบาย |
|---|---|---|
| `id` | ✓ | ไม่ซ้ำกันทั้งชุด ขึ้นต้น `train_` |
| `category` | ✓ | หมวดเดียวกับ benchmark: qa / translation / summarization / classification / code_thai / creative |
| `source` | ✓ | ที่มาของข้อมูล เช่น `handwritten`, `wangchanx`, ชื่อ dataset — ไว้ตรวจ license ย้อนหลัง |
| `messages` | ✓ | ต้องจบด้วย `assistant` (คำตอบที่ต้องการให้โมเดลเรียนรู้) |

### กฎสำคัญ: ห้ามรั่วข้อสอบ

**ห้ามเอาเคสจาก `python/openpair/benchmark/data/` หรือ core suite ไปเทรน** — ไม่งั้นคะแนนหลังเทรนวัดความจำ ไม่ใช่ความสามารถ
`check_dataset.py` ตรวจให้อัตโนมัติ: prompt ที่ซ้ำหรือคล้ายเคส benchmark (character 5-gram overlap สูง) จะ fail

```
python finetune/check_dataset.py                       # ตรวจทุกไฟล์ใน finetune/data/
python finetune/check_dataset.py finetune/data/x.jsonl # ตรวจไฟล์เดียว
```

### ขนาดที่ต้องการ

`train_seed.jsonl` ตอนนี้เป็น **ตัวอย่างต้นแบบ** (กำหนดสไตล์คำตอบ) ยังน้อยเกินไปสำหรับเทรนจริง
เป้าหมายรอบแรก: **1,000–5,000 ตัวอย่าง** กระจายทุกหมวด — แหล่งที่เป็นไปได้:
- dataset ภาษาไทยเปิด (เช็ค license ก่อน ระบุใน `source`)
- เขียนเอง / ให้โมเดลใหญ่ช่วยร่างแล้วคนตรวจ (ตรวจ license ของ provider เรื่องการเอา output ไปเทรน)
