# OpenPair — Advanced Planning: Marketing & Future Strategy

> ไฟล์นี้เก็บแผนธุรกิจ, กลยุทธ์ Marketing, และข้อดีข้อเสียของ OpenPair  
> Last updated: 2026-05-22 (checkboxes verified against code 2026-07-28)

---

## 🎯 Target Market

### กลุ่มลูกค้าหลัก (SRD v1.1)

| User Type | Role | Pain Point | เป้าหมายที่ต้องการ |
|---|---|---|---|
| AI Engineer | สร้าง AI Pipeline / LLM Apps | Routing logic ซับซ้อน, ต้องเขียนเอง | Plug-in routing ที่ยืดหยุ่น |
| Software Developer | ใช้ AI ใน Application | ไม่รู้ว่าควรเรียก model ไหน, bill แพง | API ง่าย, cost-effective |
| Head of Product / CTO | ดูภาพรวมต้นทุน | ไม่เห็น breakdown ว่าเงินหายไปไหน | Dashboard + Analytics ลดค่าใช้จ่าย |

### ขนาดตลาด

```
Python developers ทั้งหมด     ~  15 ล้านคน (2024)
ใช้ AI APIs จริง              ~  2-3 ล้านคน
จ่าย OpenAI/Anthropic bill    ~  1+ ล้านคน
รู้สึกว่า bill แพงเกินไป     ← กลุ่มเป้าหมาย OpenPair
```

---

## 💰 Business Model (SRD Phase 4)

| Tier | ราคา | Features |
|---|---|---|
| **Open Source** | Free | CLI + Library, Community Support |
| **Starter** | $29/mo | Web Dashboard, 5M tokens/mo, 3 Users |
| **Pro** | $99/mo | Unlimited Routing, Analytics, 10 Users, SLA 99.9% |
| **Enterprise** | Custom | On-Premise, SSO, Dedicated Support, SLA 99.99% |

### Value Proposition หลัก
> "จ่ายให้ OpenPair $29/เดือน — ประหยัด OpenAI bill ได้สูงสุด 85%"

---

## ✅ ข้อดี (Strengths)

### Technical
- **Rust Core = < 5ms routing latency** — เร็วกว่า Python-only solution มาก
- **ไม่ lock-in provider** — ย้าย OpenAI → Claude → Gemini ได้ตลอด
- **pip install ง่าย** — ไม่ต้องเปลี่ยน codebase เดิม
- **Open Source core** — developer เชื่อถือได้, community-driven

### Business
- **Cost saving ชัดเจน วัดได้** — ลูกค้าเห็น ROI ทันที
- **Timing ดี** — ทุกบริษัทกำลังมองหาวิธีลด AI cost ปี 2025+
- **No vendor lock-in** เป็น selling point แรง — บริษัทกลัว dependency

---

## 🔥 Pain Points ที่ OpenPair แก้ — และหลักฐานที่รองรับ

### Pain Point 1: จ่ายเงินไม่คุ้ม ส่งงานง่ายไปหา model แพงทุกครั้ง

> คนส่วนใหญ่ default ไปที่ GPT-4 / Claude ทุก request โดยไม่คิด
> ทั้งที่งาน 70–80% เป็นแค่ summarize, classify, Q&A ง่าย ๆ

**หลักฐานจากงานวิจัย:**
| Paper | สำนัก | สิ่งที่พิสูจน์ |
|---|---|---|
| **FrugalGPT** (2023) | Stanford | routing ลดค่าใช้จ่ายได้ถึง 98% โดยคุณภาพไม่ตก |
| **RouteLLM** (2024) | LMSys / Berkeley | framework routing Strong↔Weak model ได้จริงใน production |
| **AutoMix** (2023) | CMU | model ตรวจตัวเองก่อน escalate — ลด unnecessary calls |

> 🔍 อ่านเพิ่ม: [arxiv.org](https://arxiv.org) ค้น `LLM routing`, `LLM cost optimization`, `model selection`

---

### Pain Point 2: ไม่รู้ว่า model ไหนเก่งเรื่องอะไร

> Developer ส่วนใหญ่รู้แค่ "GPT-4 แพงแต่เก่ง" "Haiku ถูกแต่โง่"
> ไม่มีเครื่องมือบอกว่า task นี้ควรใช้ model ไหน เพราะอะไร

**หลักฐานจาก Industry:**
| แหล่ง | Report | ข้อมูลที่ได้ |
|---|---|---|
| **a16z** | "Who Owns the Generative AI Stack?" | cost หายไปที่ model layer มากที่สุด, margin บาง |
| **Sequoia Capital** | "Generative AI: A Creative New World" | $600B revenue gap — ROI ยังไม่คุ้มสำหรับหลายบริษัท |
| **McKinsey** | "The State of AI" (ออกทุกปี) | % บริษัทที่ใช้ AI จริง vs แค่ทดลอง, barrier คือ cost |

> 🔍 อ่านเพิ่ม: เว็บโดยตรง `a16z.com`, `sequoiacap.com`, `mckinsey.com/ai` — ดาวน์โหลดฟรี

---

### Pain Point 3: Developer ไม่รู้ตัวว่าตัวเองเปลืองเงินอยู่

> ไม่มี visibility ว่า request ไหนแพง request ไหนถูก
> จนกว่าจะได้รับ bill ปลายเดือน

**หลักฐานจาก Developer Community:**
| แหล่ง | วิธีหาข้อมูล |
|---|---|
| **Stack Overflow Developer Survey** | `survey.stackoverflow.co` — อายุ, tools, AI adoption, pain points |
| **JetBrains State of Developer Ecosystem** | `jetbrains.com/lp/devecosystem` — workflow จริงของ developer |
| **GitHub Octoverse** | `octoverse.github.com` — พฤติกรรมการใช้ AI tools |
| **Reddit** r/MachineLearning, r/LocalLLaMA | ค้น "API cost", "too expensive", "which model should I use" |
| **Hacker News** | `news.ycombinator.com` ค้น "LLM cost", "GPT-4 expensive" |

---

### Pain Point 4: Vendor Lock-in กลัวย้าย provider ไม่ได้

> เขียน code ผูกกับ OpenAI SDK → ถ้าอยากลอง Claude ต้อง refactor ใหม่ทั้งหมด

**หลักฐานจาก UX Research:**
| แหล่ง | ประเภท | ข้อมูลที่ได้ |
|---|---|---|
| **Nielsen Norman Group** | UX research firm | cognitive load ของ developer เวลาเปลี่ยน tool |
| **KPMG AI Quarterly Pulse** | Survey รายไตรมาส | adoption barrier, ROI perception, switching cost |
| **Pew Research Center** | Social research | demographics ของคนใช้ AI จริงในชีวิตประจำวัน |

---

## ❌ ข้อเสีย / ความเสี่ยง (Weaknesses & Risks)

### Technical Risks
- **Rule-based classifier แม่นยำจำกัด** — Phase 1 ใช้แค่ keyword matching, ยังไม่มี BERT/semantic (ตรวจโค้ดจริง 2026-07-28: ปรับปรุงเป็น stem+tokenize+bucket แล้ว แต่ยังเป็น rule-based ไม่ใช่ semantic)
- ~~ยังไม่ได้ call AI API จริง~~ — **แก้แล้ว** call จริงได้ทั้ง 5 provider (OpenAI, Anthropic, Google, Groq, Ollama) ใน `python/openpair/caller.py` (ตรวจโค้ดจริง 2026-07-28)
- **Hardcoded registry** — ถ้า OpenAI ขึ้นราคา ต้องแก้ code ใหม่ทุกครั้ง (ยังไม่แก้ — ตัดสินใจแล้วว่ายังไม่ทำ YAML config ดู `list_to_add.md`)

### Business Risks
- **pip-only = เข้าถึงแค่ Python developer** (แก้ได้ใน Phase 4 ด้วย REST API)
- **Competition จาก OpenAI เอง** — ถ้า OpenAI ทำ auto-routing built-in, value prop หายทันที
- **ต้อง maintain model pricing** — ราคา model เปลี่ยนบ่อย ต้องอัปเดตตาม

### Market Risks
- **ถ้า AI model ถูกลงทั่วทั้งตลาด** — pain point เรื่อง cost จะเบาลง
- **Developer ไม่อยากเพิ่ม dependency** — ต้องพิสูจน์ว่า value > friction ของการติดตั้ง

---

## 🗺️ แผนอนาคต (Beyond SRD)

### สิ่งที่ต้องทำก่อน (Phase 2 Priority)
- [x] ~~Call AI API จริงได้ (OpenAI, Anthropic, Google)~~ — ทำแล้ว ครบ 5 provider รวม Groq + Ollama (ตรวจโค้ดจริง 2026-07-28)
- [x] ~~Python library (`pip install openpair`) ใช้ได้จริง~~ — ทำแล้ว, entry point `openpair = "openpair.cli:main"` ใน `pyproject.toml`
- [x] ~~API key management~~ — ทำแล้ว, `ApiKeys` class ใน `python/openpair/config.py`
- [ ] YAML config สำหรับ registry (ไม่ต้อง hardcode) — ตัดสินใจแล้วว่ายังไม่ทำ (ดู `list_to_add.md`)

### Growth Path
```
Phase 1-2:  Python Library (AI Engineers)
                ↓
Phase 3:    Semantic Routing + BERT (accuracy ดีขึ้น)
                ↓
Phase 4:    REST API (ทุกภาษาใช้ได้) + Web Dashboard (CTO)
                ↓
Future:     Enterprise On-Premise + Custom Model Support (Ollama)
```

### Competitive Landscape

| Competitor | ข้อดีของเขา | ที่ OpenPair ทำได้ดีกว่า |
|---|---|---|
| RouteLLM (open source) | Academic research, proof-of-concept | Production-ready, pip install ง่าย |
| LiteLLM | Unified API หลาย provider | Intelligent routing (ไม่ใช่แค่ proxy) |
| OpenRouter | Web-based, marketplace | Embeddable library, no external dependency |
| AWS Bedrock | Enterprise, managed | Provider-agnostic, ไม่ lock-in AWS |

---

## 📌 คำถามเชิงกลยุทธ์ที่ต้องตอบ

- [ ] จะ monetize open source อย่างไร? (Cloud vs On-Premise vs SaaS)
- [ ] GTM strategy: Developer-led growth หรือ Sales-led?
- [ ] เมื่อไหรจะ launch public beta?
- [ ] Pricing สำหรับ token count vs flat fee ดีกว่ากัน?
