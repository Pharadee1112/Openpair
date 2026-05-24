"""
benchmark.dataset — Thai test cases
=====================================
ชุดข้อสอบภาษาไทยมาตรฐานสำหรับวัดความสามารถของ model แต่ละตัว

6 หมวดหมู่:
  qa           — ถาม-ตอบความรู้ทั่วไป
  translation  — แปลภาษา (EN→TH)
  summarization— สรุปเนื้อหา
  classification— จัดหมวดหมู่ข้อความ
  code_thai    — อธิบาย code เป็นภาษาไทย
  creative     — เขียนสร้างสรรค์ภาษาไทย
"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class ThaiTestCase:
    id:                 str
    category:           str          # qa / translation / summarization / classification / code_thai / creative
    difficulty:         str          # easy / medium / hard
    prompt:             str          # prompt ที่ส่งเข้า model
    expected_keywords:  list[str]    # คำ/วลีที่ควรอยู่ในคำตอบ
    keyword_threshold:  float = 0.4  # ต้องได้ keyword อย่างน้อยกี่ fraction (0.0–1.0)
    min_thai_ratio:     float = 0.2  # response ต้องมีอักษรไทยอย่างน้อยกี่ fraction
    notes:              str = ""     # หมายเหตุ


THAI_TEST_CASES: list[ThaiTestCase] = [

    # ══════════════════════════════════════════════════════════
    #  หมวด 1: Q&A — ถาม-ตอบ
    # ══════════════════════════════════════════════════════════

    ThaiTestCase(
        id="qa_01",
        category="qa",
        difficulty="easy",
        prompt="เมืองหลวงของประเทศไทยคืออะไร? ตอบสั้นๆ เป็นภาษาไทย",
        expected_keywords=["กรุงเทพ", "กรุงเทพมหานคร"],
        keyword_threshold=0.5,
        notes="ความรู้พื้นฐาน ต้องตอบถูกต้อง",
    ),
    ThaiTestCase(
        id="qa_02",
        category="qa",
        difficulty="easy",
        prompt="น้ำประกอบด้วยธาตุอะไรบ้าง? อธิบายเป็นภาษาไทย",
        expected_keywords=["ไฮโดรเจน", "ออกซิเจน"],
        keyword_threshold=0.5,
    ),
    ThaiTestCase(
        id="qa_03",
        category="qa",
        difficulty="medium",
        prompt="อธิบายความแตกต่างระหว่าง AI กับ Machine Learning เป็นภาษาไทยอย่างเข้าใจง่าย",
        expected_keywords=["ปัญญาประดิษฐ์", "เรียนรู้", "ข้อมูล", "โมเดล"],
        keyword_threshold=0.4,
    ),
    ThaiTestCase(
        id="qa_04",
        category="qa",
        difficulty="medium",
        prompt="ภาวะโลกร้อนคืออะไร และส่งผลกระทบอย่างไรต่อประเทศไทย? ตอบเป็นภาษาไทย",
        expected_keywords=["อุณหภูมิ", "คาร์บอน", "น้ำท่วม", "ภัยแล้ง", "สิ่งแวดล้อม"],
        keyword_threshold=0.3,
    ),
    ThaiTestCase(
        id="qa_05",
        category="qa",
        difficulty="hard",
        prompt=(
            "เปรียบเทียบระบบเศรษฐกิจแบบทุนนิยมและสังคมนิยม "
            "พร้อมยกตัวอย่างประเทศที่ใช้ระบบนั้น อธิบายเป็นภาษาไทย"
        ),
        expected_keywords=["ทุนนิยม", "สังคมนิยม", "รัฐ", "ตลาด", "เอกชน"],
        keyword_threshold=0.4,
    ),

    # ══════════════════════════════════════════════════════════
    #  หมวด 2: Translation — แปลภาษา
    # ══════════════════════════════════════════════════════════

    ThaiTestCase(
        id="tr_01",
        category="translation",
        difficulty="easy",
        prompt="แปลประโยคนี้เป็นภาษาไทย: 'The sun rises in the east.'",
        expected_keywords=["พระอาทิตย์", "ทิศตะวันออก", "ขึ้น"],
        keyword_threshold=0.5,
        min_thai_ratio=0.3,
    ),
    ThaiTestCase(
        id="tr_02",
        category="translation",
        difficulty="easy",
        prompt="แปลประโยคนี้เป็นภาษาไทย: 'Artificial intelligence is changing the world.'",
        expected_keywords=["ปัญญาประดิษฐ์", "เปลี่ยน", "โลก"],
        keyword_threshold=0.5,
        min_thai_ratio=0.3,
    ),
    ThaiTestCase(
        id="tr_03",
        category="translation",
        difficulty="medium",
        prompt=(
            "แปลข้อความต่อไปนี้เป็นภาษาไทยให้เป็นธรรมชาติ: "
            "'Machine learning models require large amounts of training data "
            "to achieve high accuracy on complex tasks.'"
        ),
        expected_keywords=["machine learning", "ข้อมูล", "ความแม่นยำ", "การฝึก"],
        keyword_threshold=0.3,
        min_thai_ratio=0.3,
    ),
    ThaiTestCase(
        id="tr_04",
        category="translation",
        difficulty="hard",
        prompt=(
            "แปลย่อหน้านี้เป็นภาษาไทยให้เป็นธรรมชาติและถูกต้อง: "
            "'Quantum computing leverages quantum mechanical phenomena such as superposition "
            "and entanglement to process information in ways that classical computers cannot. "
            "This enables solving certain problems exponentially faster.'"
        ),
        expected_keywords=["ควอนตัม", "ซ้อนทับ", "การพัน", "คอมพิวเตอร์", "ปัญหา"],
        keyword_threshold=0.3,
        min_thai_ratio=0.3,
    ),

    # ══════════════════════════════════════════════════════════
    #  หมวด 3: Summarization — สรุปเนื้อหา
    # ══════════════════════════════════════════════════════════

    ThaiTestCase(
        id="sum_01",
        category="summarization",
        difficulty="easy",
        prompt=(
            "สรุปข้อความต่อไปนี้เป็นภาษาไทย 2-3 ประโยค:\n\n"
            "ประเทศไทยเป็นประเทศในเอเชียตะวันออกเฉียงใต้ มีประชากรประมาณ 70 ล้านคน "
            "เมืองหลวงคือกรุงเทพมหานคร ซึ่งเป็นศูนย์กลางทางเศรษฐกิจและวัฒนธรรม "
            "ประเทศไทยมีชื่อเสียงด้านการท่องเที่ยว อาหาร และวัฒนธรรมที่หลากหลาย "
            "ภาษาทางการคือภาษาไทย และสกุลเงินคือบาท"
        ),
        expected_keywords=["ไทย", "กรุงเทพ", "ท่องเที่ยว", "ประชากร"],
        keyword_threshold=0.4,
        min_thai_ratio=0.4,
    ),
    ThaiTestCase(
        id="sum_02",
        category="summarization",
        difficulty="medium",
        prompt=(
            "สรุปประเด็นสำคัญจากข้อความนี้เป็น bullet points ภาษาไทย:\n\n"
            "การพัฒนาปัญญาประดิษฐ์ในปัจจุบันได้รับแรงขับเคลื่อนหลักจากสามปัจจัย "
            "ได้แก่ ข้อมูลขนาดใหญ่ที่เพิ่มขึ้นอย่างต่อเนื่อง พลังการประมวลผลที่แข็งแกร่งขึ้น "
            "และอัลกอริทึมที่ซับซ้อนมากขึ้น โดยเฉพาะ deep learning "
            "ในภาคธุรกิจ AI ถูกนำมาใช้ในการวิเคราะห์ข้อมูลลูกค้า ระบบแนะนำสินค้า "
            "และการตรวจจับการฉ้อโกง ขณะที่ในภาคสาธารณสุข AI ช่วยในการวินิจฉัยโรค "
            "และการค้นพบยาใหม่"
        ),
        expected_keywords=["ข้อมูล", "ปัญญาประดิษฐ์", "deep learning", "ธุรกิจ", "สาธารณสุข"],
        keyword_threshold=0.4,
        min_thai_ratio=0.3,
    ),

    # ══════════════════════════════════════════════════════════
    #  หมวด 4: Classification — จัดหมวดหมู่
    # ══════════════════════════════════════════════════════════

    ThaiTestCase(
        id="cls_01",
        category="classification",
        difficulty="easy",
        prompt=(
            "จัดหมวดหมู่ข้อความต่อไปนี้ว่าเป็น 'บวก' 'ลบ' หรือ 'กลาง' "
            "ตอบเป็นภาษาไทย พร้อมเหตุผลสั้นๆ:\n\n"
            "'อาหารที่ร้านนี้อร่อยมาก บริการดี และราคาไม่แพง ประทับใจมากครับ'"
        ),
        expected_keywords=["บวก", "positive", "ดี", "ประทับใจ"],
        keyword_threshold=0.3,
        min_thai_ratio=0.3,
    ),
    ThaiTestCase(
        id="cls_02",
        category="classification",
        difficulty="easy",
        prompt=(
            "จัดหมวดหมู่ข้อความนี้ว่าเกี่ยวกับหัวข้ออะไร (เทคโนโลยี / สุขภาพ / การเงิน / กีฬา / อื่นๆ) "
            "ตอบเป็นภาษาไทย:\n\n"
            "'บริษัท Apple เปิดตัว iPhone รุ่นใหม่ พร้อมชิปประมวลผลที่เร็วกว่าเดิม 30%'"
        ),
        expected_keywords=["เทคโนโลยี", "Apple", "iPhone"],
        keyword_threshold=0.3,
    ),
    ThaiTestCase(
        id="cls_03",
        category="classification",
        difficulty="medium",
        prompt=(
            "อ่านรีวิวนี้และบอกว่าลูกค้าพอใจหรือไม่พอใจ พร้อมให้คะแนน 1-5 "
            "อธิบายเหตุผลเป็นภาษาไทย:\n\n"
            "'โรงแรมทำเลดีมาก ห้องสะอาด แต่อาหารเช้าน้อยมากและแพง "
            "พนักงานบางคนไม่ค่อยยิ้มแย้ม โดยรวมก็ใช้ได้'"
        ),
        expected_keywords=["คะแนน", "พอใจ", "ดี", "แต่"],
        keyword_threshold=0.3,
    ),

    # ══════════════════════════════════════════════════════════
    #  หมวด 5: Code + Thai — อธิบาย code เป็นภาษาไทย
    # ══════════════════════════════════════════════════════════

    ThaiTestCase(
        id="code_01",
        category="code_thai",
        difficulty="easy",
        prompt=(
            "อธิบาย code Python ต่อไปนี้เป็นภาษาไทยให้เข้าใจง่าย:\n\n"
            "```python\n"
            "def greet(name):\n"
            "    return f'Hello, {name}!'\n"
            "\n"
            "result = greet('World')\n"
            "print(result)\n"
            "```"
        ),
        expected_keywords=["ฟังก์ชัน", "พารามิเตอร์", "คืนค่า", "ชื่อ", "พิมพ์"],
        keyword_threshold=0.3,
        min_thai_ratio=0.2,
    ),
    ThaiTestCase(
        id="code_02",
        category="code_thai",
        difficulty="medium",
        prompt=(
            "อธิบาย code นี้เป็นภาษาไทย บอกว่าทำอะไร และ Big O complexity คืออะไร:\n\n"
            "```python\n"
            "def binary_search(arr, target):\n"
            "    left, right = 0, len(arr) - 1\n"
            "    while left <= right:\n"
            "        mid = (left + right) // 2\n"
            "        if arr[mid] == target:\n"
            "            return mid\n"
            "        elif arr[mid] < target:\n"
            "            left = mid + 1\n"
            "        else:\n"
            "            right = mid - 1\n"
            "    return -1\n"
            "```"
        ),
        expected_keywords=["ค้นหา", "binary", "อาร์เรย์", "ครึ่ง", "O(log"],
        keyword_threshold=0.3,
        min_thai_ratio=0.2,
    ),
    ThaiTestCase(
        id="code_03",
        category="code_thai",
        difficulty="hard",
        prompt=(
            "อธิบาย design pattern นี้เป็นภาษาไทย พร้อมบอกว่าควรใช้เมื่อไหร่:\n\n"
            "```python\n"
            "class Singleton:\n"
            "    _instance = None\n"
            "\n"
            "    def __new__(cls):\n"
            "        if cls._instance is None:\n"
            "            cls._instance = super().__new__(cls)\n"
            "        return cls._instance\n"
            "```"
        ),
        expected_keywords=["Singleton", "instance", "object", "เดียว", "pattern"],
        keyword_threshold=0.3,
        min_thai_ratio=0.2,
    ),

    # ══════════════════════════════════════════════════════════
    #  หมวด 6: Creative — เขียนสร้างสรรค์ภาษาไทย
    # ══════════════════════════════════════════════════════════

    ThaiTestCase(
        id="cre_01",
        category="creative",
        difficulty="easy",
        prompt="เขียนบทกวีสั้น 4 บรรทัด เกี่ยวกับดอกบัว เป็นภาษาไทย",
        expected_keywords=["บัว", "น้ำ", "ดอก"],
        keyword_threshold=0.4,
        min_thai_ratio=0.5,
        notes="วัด Thai ratio เป็นหลัก — ต้องเขียนเป็นภาษาไทยจริงๆ",
    ),
    ThaiTestCase(
        id="cre_02",
        category="creative",
        difficulty="medium",
        prompt=(
            "เขียนเรื่องสั้นภาษาไทย 3-4 ประโยค เกี่ยวกับหุ่นยนต์ที่เรียนรู้ "
            "ความหมายของมิตรภาพ"
        ),
        expected_keywords=["หุ่นยนต์", "เพื่อน", "เรียนรู้", "ความรู้สึก"],
        keyword_threshold=0.3,
        min_thai_ratio=0.5,
    ),
    ThaiTestCase(
        id="cre_03",
        category="creative",
        difficulty="hard",
        prompt=(
            "เขียนสโลแกนภาษาไทยสำหรับแอปพลิเคชัน AI ที่ช่วยเลือก model "
            "ที่เหมาะสมที่สุดอัตโนมัติ ให้น่าจดจำและกระชับ 3 ตัวเลือก"
        ),
        expected_keywords=["AI", "อัตโนมัติ", "เลือก", "ฉลาด"],
        keyword_threshold=0.2,
        min_thai_ratio=0.4,
    ),
]


def get_cases_by_category(category: str) -> list[ThaiTestCase]:
    return [c for c in THAI_TEST_CASES if c.category == category]


def get_cases_by_difficulty(difficulty: str) -> list[ThaiTestCase]:
    return [c for c in THAI_TEST_CASES if c.difficulty == difficulty]


CATEGORIES = ["qa", "translation", "summarization", "classification", "code_thai", "creative"]
