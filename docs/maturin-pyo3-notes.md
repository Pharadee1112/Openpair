# Maturin & PyO3 คืออะไร (สรุปไว้อ่านทีหลัง)

## สถานะ CLI ปัจจุบัน
โปรเจกต์นี้ **ยังไม่มี CLI จริง** — `pyproject.toml` ไม่มี `[project.scripts]` และไม่มีไฟล์ Python ไหนใช้ `argparse`/`click`/`typer` หรือมี `def main()` เลย
ดังนั้นตอนนี้ยังไม่สามารถทดสอบผ่านคำสั่ง `openpair ...` จาก terminal ได้ ต้อง import ผ่าน Python โดยตรง (`from openpair import ...`) หรือรัน Rust demo binary (`cargo run --bin openpair-demo`)

ถ้าจะเพิ่ม CLI ต้อง:
```toml
[project.scripts]
openpair = "openpair.cli:main"
```
แล้วสร้าง `python/openpair/cli.py` ที่มี `def main():`

---

## Maturin คืออะไร
**ไม่ใช่ framework** — เป็น **build tool / packaging tool** (คล้าย `pip`/`setuptools` แต่เฉพาะทางสำหรับ Rust)

หน้าที่:
1. เรียก `cargo build` compile Rust → native library (`.pyd` บน Windows / `.so` บน Linux / `.dylib` บน Mac)
2. ห่อ native library นั้นให้กลายเป็น Python wheel (`.whl`) ที่ `pip install` ได้
3. ใช้ **pyo3** เป็นสะพานเชื่อม Rust ↔ Python

คำสั่งที่ใช้บ่อย:
- `maturin develop` — build แล้ว install ลง virtualenv ทันที (สำหรับ dev)
- `maturin build` — build wheel สำหรับ distribute/publish

หลักฐานในโปรเจกต์ (`Cargo.toml`, `pyproject.toml`):
- `Cargo.toml`: lib ชื่อ `_core`, crate-type = `cdylib` → compile เป็น shared library ให้ Python import
- `pyproject.toml`:
  ```toml
  [tool.maturin]
  python-source = "python"
  module-name = "openpair._core"
  ```
  → Rust ที่ build เสร็จกลายเป็นโมดูล `openpair._core` ที่โค้ด Python (`python/openpair/client.py` ฯลฯ) import ไปใช้

ทางเลือกอื่นแทน maturin: `setuptools-rust` (เก่ากว่า, config ยุ่งยากกว่า)

---

## PyO3 คืออะไร
Core crate ที่ให้ macro/attribute แปลง Rust code ธรรมดาให้ Python เห็นเป็นของ Python ได้ (จัดการ type conversion, memory/GIL, error handling ผ่าน `PyResult`)

ตัวอย่างจริงใน [`src/lib.rs`](../src/lib.rs):
- `#[pymodule]` (บรรทัด 15) — จุด entry ตอน Python สั่ง `import _core`
- `#[pyfunction]` (บรรทัด 33, 48, ...) — แปลง Rust function → เรียกจาก Python ได้ตรง ๆ เช่น `_core.route(prompt)`
- `wrap_pyfunction!` (บรรทัด 18-21) — ห่อ function ไปลงทะเบียนใน module
- `m.add_class::<RoutingDecision>()` (บรรทัด 17) — แปลง Rust struct → Python class

## PyO3 Ecosystem (เครื่องมือรอบ ๆ pyo3)
pyo3 core ทำแค่เรื่อง binding เท่านั้น ส่วนงานอื่นมีเครื่องมือแยก:

| เครื่องมือ | หน้าที่ |
|---|---|
| **maturin** | build + package เป็น `.whl` |
| **rust-numpy** | เชื่อม Rust ↔ numpy array (ไม่ได้ใช้ในโปรเจกต์นี้) |
| **pyo3-asyncio** | เชื่อม Rust async (tokio) ↔ Python `asyncio` |
| **pyo3-log** | ส่ง log จาก Rust ไปออกที่ Python logging |
| **setuptools-rust** | ทางเลือกแทน maturin |

โปรเจกต์นี้ใช้แค่ pyo3 core + maturin เพราะงานของ `_core` (route, score_complexity, is_thai, thai_ratio) เป็นแค่ string-in → value-out ธรรมดา ไม่ต้องพึ่ง numpy/async
