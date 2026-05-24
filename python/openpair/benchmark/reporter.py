"""
benchmark.reporter — แสดงผล benchmark เป็นตารางสวยงาม
=======================================================
พิมพ์ตารางเปรียบเทียบ model และแนะนำค่า thai_score ที่ควรอัปเดตใน registry
"""

from __future__ import annotations
from .scorer import ModelBenchmarkResult
from .dataset import CATEGORIES


def print_summary(results: list[ModelBenchmarkResult]) -> None:
    """พิมพ์ตารางสรุปผลทุก model"""
    if not results:
        print("ไม่มีผลลัพธ์")
        return

    print(f"\n{'═'*80}")
    print("  📊 Thai Benchmark — ผลการทดสอบ")
    print(f"{'═'*80}\n")

    # ── ตารางหลัก ────────────────────────────────────────────────
    col_model  = 24
    col_score  = 9
    col_kw     = 9
    col_thai   = 9
    col_pass   = 9
    col_thai_s = 10

    header = (
        f"{'Model':<{col_model}} "
        f"{'Avg Score':>{col_score}} "
        f"{'Keyword':>{col_kw}} "
        f"{'Thai Ratio':>{col_thai}} "
        f"{'Pass Rate':>{col_pass}} "
        f"{'thai_score':>{col_thai_s}}"
    )
    print(header)
    print("─" * 80)

    for r in results:
        bar = _score_bar(r.avg_final_score)
        print(
            f"{r.model_name:<{col_model}} "
            f"{r.avg_final_score:>{col_score}.2f}/10 "
            f"{r.avg_keyword_score:>{col_kw}.0%} "
            f"{r.avg_thai_ratio:>{col_thai}.0%} "
            f"{r.pass_rate:>{col_pass}.0%} "
            f"{r.suggested_thai_score:>{col_thai_s}}   {bar}"
        )

    print()

    # ── ตารางแยกตาม Category ─────────────────────────────────────
    print("  📂 แยกตามหมวดหมู่\n")

    cat_header = f"{'Model':<24} " + " ".join(f"{c[:8]:>9}" for c in CATEGORIES)
    print(cat_header)
    print("─" * 80)

    for r in results:
        row = f"{r.model_name:<24} "
        for cat in CATEGORIES:
            avg = r.category_avg(cat)
            row += f"{avg:>9.1f}"
        print(row)

    print()

    # ── แนะนำค่า thai_score ──────────────────────────────────────
    print_registry_suggestion(results)


def print_registry_suggestion(results: list[ModelBenchmarkResult]) -> None:
    """แนะนำค่า thai_score ที่ควรอัปเดตใน registry.rs"""
    print(f"{'═'*80}")
    print("  🦀 แนะนำ: อัปเดตค่าต่อไปนี้ใน src/registry.rs\n")
    for r in results:
        print(f"  {r.model_id:<40} thai_score: {r.suggested_thai_score}")
    print(f"\n{'═'*80}\n")


def print_detail(result: ModelBenchmarkResult) -> None:
    """พิมพ์ผลแบบละเอียดของ model เดียว"""
    print(f"\n{'─'*70}")
    print(f"  📋 รายละเอียด: {result.model_name}")
    print(f"{'─'*70}")
    print(f"  {'ID':<12} {'Category':<16} {'Diff':<8} {'Score':>6} {'KW':>6} {'Thai':>6} {'✓'}")
    print(f"  {'─'*65}")
    for s in result.scores:
        check = "✅" if s.passed else "❌"
        print(
            f"  {s.test_case_id:<12} {s.category:<16} {s.difficulty:<8} "
            f"{s.final_score:>6.1f} {s.keyword_score:>6.0%} {s.thai_ratio:>6.0%} {check}"
        )
        print(f"     ↳ {s.response_preview[:70]}")


def _score_bar(score: float, width: int = 10) -> str:
    """แสดง score เป็น bar เช่น ████░░░░░░"""
    filled = round(score / 10 * width)
    return "█" * filled + "░" * (width - filled)
