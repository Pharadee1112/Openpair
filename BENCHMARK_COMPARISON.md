# Thai Benchmark — เทียบ model แยกตามหมวดงาน

> สร้างโดย `python scripts/compare_results.py` — อย่าแก้มือ รันสคริปต์ใหม่เมื่อมีผล benchmark ใหม่
> คะแนน 0–10 ต่อเคส (keyword 50% + สัดส่วนภาษาไทย 30% + ความยาว 20%) — ตัวหนา = ดีที่สุดในคอลัมน์นั้น

## 1. ชุด core — 20 เคสเดียวกันทุก model (เทียบได้ยุติธรรมที่สุด)

| Model | เคส | qa | translation | summarization | classification | code_thai | creative | รวม |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `openai/gpt-oss-20b` | 20 | 9.20 | 8.29 | **10.00** | **8.47** | **9.33** | **9.17** | **9.00** |
| `gemini-3.1-flash-lite` | 20 | **9.80** | **9.33** | 8.88 | 8.06 | 8.67 | 8.33 | 8.96 |
| `nvidia/nemotron-3-super-120b-a12b:free` | 20 | 8.80 | 8.96 | 9.50 | **8.47** | **9.33** | 8.75 | 8.93 |
| `openai/gpt-oss-120b` | 20 | 9.60 | 8.71 | **10.00** | **8.47** | 8.33 | 8.19 | 8.89 |
| `gemini-3.6-flash` | 20 | 5.00 | 7.95 | 5.62 | 6.81 | 2.96 | 5.83 | 5.74 |

ดีที่สุดในแต่ละหมวด:
- **qa**: `gemini-3.1-flash-lite` (9.80)
- **translation**: `gemini-3.1-flash-lite` (9.33)
- **summarization**: `openai/gpt-oss-20b`, `openai/gpt-oss-120b` (10.00)
- **classification**: `openai/gpt-oss-20b`, `openai/gpt-oss-120b`, `nvidia/nemotron-3-super-120b-a12b:free` (8.47)
- **code_thai**: `openai/gpt-oss-20b`, `nvidia/nemotron-3-super-120b-a12b:free` (9.33)
- **creative**: `openai/gpt-oss-20b` (9.17)

หมายเหตุ: 20 เคสคือ 3–4 เคสต่อหมวด ต่างกันไม่กี่ทศนิยมยังถือว่าสูสี ใช้ดูแนวโน้ม ไม่ใช่ตัดสินเด็ดขาด
`gemini-3.6-flash` วัดเมื่อ 2026-07-28 ด้วย runner รุ่นเก่า (ก่อนแก้ปัญหาคำตอบว่าง) คะแนนอาจต่ำกว่าความจริงเล็กน้อย

## 2. ชุด full — 600 เคส (100 ต่อหมวด) เฉพาะ model ที่รันครบ

| Model | เคส | qa | translation | summarization | classification | code_thai | creative | รวม |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `gemini-3.1-flash-lite` | 600 | **9.36** | **9.22** | **9.52** | **9.89** | **9.39** | **9.05** | **9.41** |
| `openai/gpt-oss-120b` | 600 | 8.10 | 8.29 | 9.22 | 9.65 | 8.84 | 8.63 | 8.79 |
| `openai/gpt-oss-20b` | 598 | 8.00 | 7.93 | 9.03 | 9.55 | 9.15 | 8.58 | 8.71 |

ดีที่สุดในแต่ละหมวด:
- **qa**: `gemini-3.1-flash-lite` (9.36)
- **translation**: `gemini-3.1-flash-lite` (9.22)
- **summarization**: `gemini-3.1-flash-lite` (9.52)
- **classification**: `gemini-3.1-flash-lite` (9.89)
- **code_thai**: `gemini-3.1-flash-lite` (9.39)
- **creative**: `gemini-3.1-flash-lite` (9.05)

## ที่มาของผล

- `gemini-3.1-flash-lite` — Gemini, จาก `benchmark_results_gemini_full.json`
- `gemini-3.6-flash` — Gemini, จาก `benchmark_results_gemini_2026_part2.json`
- `openai/gpt-oss-20b` — Groq, จาก `benchmark_results_groq_full.json`
- `openai/gpt-oss-120b` — Groq, จาก `benchmark_results_groq_full.json`
- `nvidia/nemotron-3-super-120b-a12b:free` — OpenRouter (ไม่อยู่ใน registry), จาก `benchmark_results_openrouter_core.json`
