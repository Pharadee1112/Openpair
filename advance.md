# OpenPair — Advanced Planning: Marketing & Future Strategy

> ไฟล์นี้เก็บแผนธุรกิจ, กลยุทธ์ Marketing, และข้อดีข้อเสียของ OpenPair  
> Last updated: 2026-05-22

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

## ❌ ข้อเสีย / ความเสี่ยง (Weaknesses & Risks)

### Technical Risks
- **Rule-based classifier แม่นยำจำกัด** — Phase 1 ใช้แค่ keyword matching, ยังไม่มี BERT/semantic
- **ยังไม่ได้ call AI API จริง** — MVP ยังแค่ "routing decision" ไม่ใช่ "routing จริง"
- **Hardcoded registry** — ถ้า OpenAI ขึ้นราคา ต้องแก้ code ใหม่ทุกครั้ง

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
- [ ] Call AI API จริงได้ (OpenAI, Anthropic, Google)
- [ ] Python library (`pip install openpair`) ใช้ได้จริง
- [ ] API key management
- [ ] YAML config สำหรับ registry (ไม่ต้อง hardcode)

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
