"""
analyze_behavior.py — วิเคราะห์พฤติกรรม model จากผล Thai benchmark ชุด full (สำหรับเขียน paper)
=================================================================================================
อ่านผลที่มีอยู่แล้ว (ไม่เรียก API) แล้วสร้าง:

  paper/ANALYSIS.md            ตารางทั้งหมด + bootstrap 95% CI + ข้อจำกัดของ benchmark
  paper/figures/*.png, *.pdf   กราฟสำหรับใส่ใน paper (label ภาษาอังกฤษ)
  paper/slang_review.csv       แบบฟอร์มให้คนไทยตรวจความหมายสแลง (เปิดใน Excel ได้)

Usage:
    python scripts/analyze_behavior.py

ต้องมี matplotlib (pip install -e ".[paper]")
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from openpair.benchmark.dataset import get_suite  # noqa: E402

OUT_DIR = ROOT / "paper"
FIG_DIR = OUT_DIR / "figures"

# model ที่รันชุด full ครบ — ลำดับนี้คือลำดับสีด้วย (สีตาม model เสมอ ไม่ตามอันดับ)
MODELS = [
    ("gemini-3.1-flash-lite", "benchmark_results_gemini_full.json", "Gemini 3.1 Flash-Lite"),
    ("openai/gpt-oss-120b",   "benchmark_results_groq_full.json",   "gpt-oss-120b"),
    ("openai/gpt-oss-20b",    "benchmark_results_groq_full.json",   "gpt-oss-20b"),
]
COLORS = ["#2a78d6", "#eb6834", "#1baf7a"]  # categorical slot 1–3 (ผ่าน CVD check แบบ all-pairs)
INK, INK_2, GRID = "#0b0b0b", "#52514e", "#e4e3df"

CATEGORIES = ["qa", "translation", "summarization", "classification", "code_thai", "creative"]
DIFFICULTIES = ["easy", "medium", "hard"]

# กลุ่มเนื้อหา จาก field notes ของแต่ละเคส — เคสหนึ่งอยู่ได้กลุ่มเดียว (เช็คตามลำดับ)
GROUPS = [
    ("Slang / social media", ("สแลง", "วัยรุ่น", "ภาษาโซเชียล", "มีม")),
    ("Current news (Sep 2026)", ("ข่าวปัจจุบัน",)),
    ("Idioms / proverbs", ("สำนวน", "สุภาษิต")),
    ("Regional dialects", ("ภาษาถิ่น",)),
    ("Register / formality", ("ระดับภาษา", "ทางการ")),
    ("Sarcasm / mixed sentiment", ("ประชด", "ความรู้สึกผสม")),
    ("Scam detection", ("หลอกลวง",)),
]
OTHER_GROUP = "Other"

N_BOOT = 5000
RNG_SEED = 20261013


# ── โหลดข้อมูล ──────────────────────────────────────────────────────

def load_scores() -> dict[str, dict[str, dict]]:
    """model_id -> case_id -> score row"""
    out: dict[str, dict[str, dict]] = {}
    for model_id, fname, _ in MODELS:
        data = json.loads((ROOT / fname).read_text(encoding="utf-8"))
        entry = next(m for m in data["models"] if m["model_id"] == model_id)
        out[model_id] = {s["id"]: s for s in entry["scores"]}
    return out


def group_of(notes: str) -> str:
    for name, keys in GROUPS:
        if any(k in notes for k in keys):
            return name
    return OTHER_GROUP


def points_lost(row: dict) -> tuple[float, float, float]:
    """แยกคะแนนที่เสียตามองค์ประกอบของ scorer (keyword 5 / thai 3 / length 2)"""
    kw = row["keyword_score"] * 5.0
    th = min(row["thai_ratio"] * 10, 3.0)
    length_ok = row.get("length_ok")
    if length_ok is None:  # ไฟล์ผลเก่าไม่มี length_ok — คำนวณกลับจาก final_score
        length_ok = (row["final_score"] - kw - th) > 1.0
    return 5.0 - kw, 3.0 - th, 0.0 if length_ok else 2.0


# ── สถิติ ───────────────────────────────────────────────────────────

_rng = np.random.default_rng(RNG_SEED)


def mean_ci(xs) -> tuple[float, float, float]:
    xs = np.asarray(xs, dtype=float)
    if len(xs) == 0:
        return float("nan"), float("nan"), float("nan")
    boots = _rng.choice(xs, size=(N_BOOT, len(xs)), replace=True).mean(axis=1)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return float(xs.mean()), float(lo), float(hi)


def rankdata(xs) -> np.ndarray:
    """rank แบบเฉลี่ยเมื่อค่าเท่ากัน (เหมือน scipy.stats.rankdata)"""
    xs = np.asarray(xs, dtype=float)
    order = np.argsort(xs, kind="mergesort")
    ranks = np.empty(len(xs))
    sorted_x = xs[order]
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and sorted_x[j + 1] == sorted_x[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(a, b) -> float:
    ra, rb = rankdata(a), rankdata(b)
    return float(np.corrcoef(ra, rb)[0, 1])


def fmt_ci(m: float, lo: float, hi: float) -> str:
    return f"{m:.2f} [{lo:.2f}, {hi:.2f}]"


# ── กราฟ ────────────────────────────────────────────────────────────

def _style(ax, xlabel: str) -> None:
    ax.set_xlabel(xlabel, color=INK_2, fontsize=9)
    ax.tick_params(colors=INK_2, labelsize=9, length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)


def dot_plot(rows: list[str], stats: dict[str, list[tuple]], title: str, path: Path,
             xlim=(5, 10.2), row_labels: list[str] | None = None) -> None:
    """Cleveland dot plot: แถว = หมวด, จุด = model, เส้น = 95% CI"""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6.4, 0.42 * len(rows) + 1.3), dpi=300)
    offsets = np.linspace(-0.22, 0.22, len(MODELS))
    for k, (model_id, _, label) in enumerate(MODELS):
        ys = np.arange(len(rows)) + offsets[k]
        m = np.array([stats[model_id][i][0] for i in range(len(rows))])
        lo = np.array([stats[model_id][i][1] for i in range(len(rows))])
        hi = np.array([stats[model_id][i][2] for i in range(len(rows))])
        ax.hlines(ys, lo, hi, color=COLORS[k], linewidth=2, zorder=2)
        ax.scatter(m, ys, s=36, color=COLORS[k], edgecolor="white", linewidth=1.5, zorder=3, label=label)
    ax.set_yticks(np.arange(len(rows)))
    ax.set_yticklabels(row_labels or rows)
    ax.invert_yaxis()
    ax.set_xlim(*xlim)
    _style(ax, "Mean score (0–10), bars = bootstrap 95% CI")
    ax.set_title(title, loc="left", fontsize=10.5, color=INK, pad=24)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=len(MODELS), frameon=False,
              fontsize=8.5, handletextpad=0.3, columnspacing=1.2, labelcolor=INK_2)
    fig.tight_layout()
    fig.savefig(path.with_suffix(".png"))
    fig.savefig(path.with_suffix(".pdf"))
    plt.close(fig)


# ── main ────────────────────────────────────────────────────────────

def main() -> None:
    import matplotlib
    matplotlib.use("Agg")

    cases = {c.id: c for c in get_suite("full")}
    res = load_scores()
    ids = sorted(set(cases).intersection(*[set(v) for v in res.values()]))
    mids = [m for m, _, _ in MODELS]
    label = {m: lab for m, _, lab in MODELS}
    grp = {i: group_of(cases[i].notes or "") for i in ids}

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    md: list[str] = []
    w = md.append

    w("# Thai benchmark — วิเคราะห์พฤติกรรม model (ชุด full)\n")
    w("> สร้างโดย `python scripts/analyze_behavior.py` — อย่าแก้มือ รันใหม่เมื่อผลเปลี่ยน")
    w(f"> ใช้เฉพาะเคสที่ทุก model ตอบครบ: **{len(ids)} เคส** "
      f"(`gpt-oss-20b` ได้คำตอบว่าง 2 เคส จาก 600) — CI = bootstrap {N_BOOT} รอบ, seed {RNG_SEED}")
    w("> คะแนน 0–10 = keyword 5 + สัดส่วนภาษาไทย 3 + ความยาวพอ 2 (`scorer.py`) — ไม่ใช่การตรวจโดยคน\n")

    # 1. ภาพรวม
    w("## 1. คะแนนรวม\n")
    w("| Model | Mean [95% CI] | ผ่านเกณฑ์ | ได้ 10 เต็ม | keyword ไม่ครบ | ภาษาไทย < 50% |")
    w("|---|---|---:|---:|---:|---:|")
    for m in mids:
        fs = [res[m][i]["final_score"] for i in ids]
        w(f"| {label[m]} | {fmt_ci(*mean_ci(fs))} "
          f"| {sum(res[m][i]['passed'] for i in ids)} "
          f"| {sum(f >= 9.995 for f in fs)} "
          f"| {sum(res[m][i]['keyword_score'] < 1 for i in ids)} "
          f"| {sum(res[m][i]['thai_ratio'] < 0.5 for i in ids)} |")
    w("")

    w("**ผลต่างแบบจับคู่ (paired, เคสเดียวกัน)** — CI ไม่คร่อม 0 = ต่างกันจริง\n")
    w("| เทียบ | ผลต่างเฉลี่ย [95% CI] | ชนะ / เสมอ / แพ้ |")
    w("|---|---|---|")
    for a, b in [(mids[0], mids[1]), (mids[0], mids[2]), (mids[1], mids[2])]:
        d = [res[a][i]["final_score"] - res[b][i]["final_score"] for i in ids]
        win = sum(x > 0.005 for x in d)
        loss = sum(x < -0.005 for x in d)
        w(f"| {label[a]} − {label[b]} | {fmt_ci(*mean_ci(d))} | {win} / {len(d) - win - loss} / {loss} |")
    w("")

    # 2. หมวดงาน
    w("## 2. แยกตามหมวดงาน\n")
    w("| หมวด | n | " + " | ".join(label[m] for m in mids) + " |")
    w("|---|---:|" + "---|" * len(mids))
    cat_stats: dict[str, list[tuple]] = {m: [] for m in mids}
    for cat in CATEGORIES:
        sel = [i for i in ids if cases[i].category == cat]
        cells = []
        for m in mids:
            s = mean_ci([res[m][i]["final_score"] for i in sel])
            cat_stats[m].append(s)
            cells.append(fmt_ci(*s))
        w(f"| {cat} | {len(sel)} | " + " | ".join(cells) + " |")
    w("")
    dot_plot(CATEGORIES, cat_stats, "Thai benchmark score by task category (n = %d)" % len(ids),
             FIG_DIR / "fig1_category")
    w("![](figures/fig1_category.png)\n")

    # 3. กลุ่มเนื้อหา
    w("## 3. แยกตามประเภทเนื้อหา (จาก notes ของเคส)\n")
    group_names = [g for g, _ in GROUPS] + [OTHER_GROUP]
    group_names = [g for g in group_names if any(grp[i] == g for i in ids)]
    w("| ประเภท | n | " + " | ".join(label[m] for m in mids) + " |")
    w("|---|---:|" + "---|" * len(mids))
    grp_stats: dict[str, list[tuple]] = {m: [] for m in mids}
    for g in group_names:
        sel = [i for i in ids if grp[i] == g]
        cells = []
        for m in mids:
            s = mean_ci([res[m][i]["final_score"] for i in sel])
            grp_stats[m].append(s)
            cells.append(fmt_ci(*s))
        w(f"| {g} | {len(sel)} | " + " | ".join(cells) + " |")
    w("")
    w("กลุ่มที่ n น้อย (ภาษาถิ่น, ประชด) CI กว้างมาก — ใช้ดูแนวโน้มเท่านั้น\n")
    dot_plot(group_names, grp_stats, "Score by content type", FIG_DIR / "fig2_content_type",
             xlim=(4, 10.2), row_labels=[f"{g} (n={sum(grp[i] == g for i in ids)})" for g in group_names])
    w("![](figures/fig2_content_type.png)\n")

    # 4. ความยาก
    w("## 4. ป้ายความยาก (easy/medium/hard) ทำนายคะแนนได้ไหม\n")
    w("| ความยาก | n | " + " | ".join(label[m] for m in mids) + " |")
    w("|---|---:|" + "---|" * len(mids))
    dif_stats: dict[str, list[tuple]] = {m: [] for m in mids}
    for dif in DIFFICULTIES:
        sel = [i for i in ids if cases[i].difficulty == dif]
        cells = []
        for m in mids:
            s = mean_ci([res[m][i]["final_score"] for i in sel])
            dif_stats[m].append(s)
            cells.append(fmt_ci(*s))
        w(f"| {dif} | {len(sel)} | " + " | ".join(cells) + " |")
    w("")
    dnum = [DIFFICULTIES.index(cases[i].difficulty) for i in ids]
    rhos = ", ".join(f"{label[m]} {spearman(dnum, [res[m][i]['final_score'] for i in ids]):+.3f}" for m in mids)
    w(f"Spearman ρ (ความยาก vs คะแนน): {rhos} — ค่าใกล้ 0 = ป้ายความยากที่คนตั้งไม่สัมพันธ์กับคะแนนจริง\n")
    dot_plot(DIFFICULTIES, dif_stats, "Score by human-assigned difficulty label",
             FIG_DIR / "fig3_difficulty", xlim=(7, 10.2))
    w("![](figures/fig3_difficulty.png)\n")

    # 5. เสียคะแนนตรงไหน
    w("## 5. เสียคะแนนจากองค์ประกอบไหน (คะแนนที่เสียเฉลี่ยต่อเคส)\n")
    w("| Model | keyword (เต็ม 5) | ภาษาไทย (เต็ม 3) | ความยาว (เต็ม 2) | รวมที่เสีย |")
    w("|---|---:|---:|---:|---:|")
    for m in mids:
        lost = np.array([points_lost(res[m][i]) for i in ids])
        k, t, l = lost.mean(axis=0)
        w(f"| {label[m]} | {k:.2f} | {t:.2f} | {l:.2f} | {k + t + l:.2f} |")
    w("")
    w("**คำตอบที่สัดส่วนภาษาไทย < 50% แยกตามหมวด**\n")
    w("| Model | " + " | ".join(CATEGORIES) + " |")
    w("|---|" + "---:|" * len(CATEGORIES))
    for m in mids:
        c = Counter(cases[i].category for i in ids if res[m][i]["thai_ratio"] < 0.5)
        w(f"| {label[m]} | " + " | ".join(str(c.get(cat, 0)) for cat in CATEGORIES) + " |")
    w("")
    w("หมายเหตุ: สัดส่วนภาษาไทยนับตัวอักษรในโค้ดเป็น \"ไม่ใช่ไทย\" ด้วย — code_thai จึงเสียเปรียบทุก model "
      "ส่วนต่างระหว่าง model คือคำอธิบายรอบโค้ดเป็นภาษาอังกฤษ — แต่คะแนนส่วนภาษาไทยเต็มตั้งแต่สัดส่วน 30% "
      "(`min(ratio × 10, 3)`) จึงแทบไม่เคยหักคะแนนจริง: ผลต่างระหว่าง model เกือบทั้งหมดมาจาก keyword\n")

    # 6. ความสามารถในการแยก model
    w("## 6. Benchmark แยก model ออกจากกันได้แค่ไหน\n")
    all_perfect = [i for i in ids if all(res[m][i]["final_score"] >= 9.995 for m in mids)]
    identical = [i for i in ids if len({round(res[m][i]["final_score"], 2) for m in mids}) == 1]
    all_fail = [i for i in ids if all(not res[m][i]["passed"] for m in mids)]
    w(f"- ทุก model ได้ 10 เต็ม: **{len(all_perfect)} เคส** ({len(all_perfect) / len(ids):.0%})")
    w(f"- ทุก model ได้คะแนนเท่ากัน: **{len(identical)} เคส** ({len(identical) / len(ids):.0%}) — เคสพวกนี้ไม่ช่วยแยก model")
    per_cat = Counter(cases[i].category for i in all_perfect)
    w("- เคสที่ทุก model ได้เต็ม แยกหมวด: " + ", ".join(f"{c} {per_cat.get(c, 0)}" for c in CATEGORIES))
    w(f"- ทุก model ไม่ผ่านเกณฑ์: **{len(all_fail)} เคส** — " + ", ".join(f"`{i}`" for i in all_fail))
    w("")

    # 7. เคสที่ model แตกต่างกันมากที่สุด
    w("## 7. เคสที่ model ห่างกันมากที่สุด (ใช้เลือกตัวอย่างใส่ paper)\n")
    w("| เคส | ประเภท | " + " | ".join(label[m] for m in mids) + " | คำตอบ (80 ตัวอักษรแรก) ของ model ที่ต่ำสุด |")
    w("|---|---|" + "---:|" * len(mids) + "---|")
    spread = sorted(ids, key=lambda i: -(max(res[m][i]["final_score"] for m in mids)
                                         - min(res[m][i]["final_score"] for m in mids)))
    for i in spread[:25]:
        worst = min(mids, key=lambda m: res[m][i]["final_score"])
        prev = res[worst][i]["preview"].replace("|", "\\|")
        w(f"| `{i}` | {grp[i]} | " + " | ".join(f"{res[m][i]['final_score']:.1f}" for m in mids)
          + f" | {label[worst]}: {prev} |")
    w("")

    # 8. ข้อจำกัด
    w("## 8. ข้อจำกัดของข้อมูลชุดนี้\n")
    w("- ผลชุดนี้เก็บคำตอบแค่ 80 ตัวอักษรแรก — ให้คะแนนใหม่ / ให้คนตรวจทั้งคำตอบไม่ได้ ต้องรันใหม่ "
      "(runner เก็บคำตอบเต็ม + token + latency แล้วตั้งแต่ 2026-10-13)")
    w("- ชุด full รันรอบเดียวต่อ model และไม่มี token/latency รายเคส — ความแปรปรวนระหว่างรอบวัดได้บน 154 เคสที่รันซ้ำ ดู `paper/STABILITY.md`")
    w("- keyword scoring: คำพ้องความหมายไม่ได้คะแนน, คำตอบที่ให้หลายตัวเลือกได้ keyword มากกว่า, เฉลยบางข้อกำกวม (`cls_50`)")
    w("- ความหมายสแลงในเฉลยยังไม่มีคนตรวจยืนยัน — ดู `paper/slang_review.csv`")
    w("")

    (OUT_DIR / "ANALYSIS.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    # แบบฟอร์มให้คนไทยตรวจ — ทุกเคสที่ต้องใช้ความรู้ภาษาไทยจริง (สแลง, สำนวน, ภาษาถิ่น, ระดับภาษา, ประชด)
    # ข่าว/หลอกลวง/อื่นๆ ไม่อยู่ในนี้ เพราะเฉลยมาจากเนื้อข่าวในโจทย์ ไม่ต้องอาศัยคนไทยตัดสิน
    review_groups = ("Slang / social media", "Idioms / proverbs", "Regional dialects",
                     "Register / formality", "Sarcasm / mixed sentiment")
    review_ids = [i for i in ids if grp[i] in review_groups]
    review_path = OUT_DIR / "slang_review.csv"
    review_cols = ["เฉลยถูกไหม (Y/N)", "ความหมายที่ถูก (ถ้าเฉลยผิด)",
                   *[f"{label[m]} ถูกไหม (Y/N/?)" for m in mids], "หมายเหตุ"]
    # เก็บสิ่งที่คนตรวจกรอกไว้แล้ว — รันสคริปต์ใหม่ต้องไม่ทับ
    filled: dict[str, dict[str, str]] = {}
    if review_path.exists():
        with open(review_path, encoding="utf-8-sig", newline="") as f:
            filled = {row["case_id"]: row for row in csv.DictReader(f)}
    with open(review_path, "w", encoding="utf-8-sig", newline="") as f:
        cw = csv.writer(f)
        cw.writerow(["case_id", "category", "ประเภทเนื้อหา", "prompt", "expected_keywords",
                     *[f"{label[m]} (score / คำตอบ 80 ตัวแรก)" for m in mids], *review_cols])
        for i in review_ids:
            c = cases[i]
            old = filled.get(i, {})
            cw.writerow([i, c.category, grp[i], c.prompt, ", ".join(c.expected_keywords),
                         *[f"{res[m][i]['final_score']:.1f} | {res[m][i]['preview']}" for m in mids],
                         *[old.get(col, "") for col in review_cols]])

    print(f"wrote {OUT_DIR / 'ANALYSIS.md'}")
    print(f"wrote {len(list(FIG_DIR.glob('*.png')))} figures to {FIG_DIR}")
    print(f"wrote {review_path} ({len(review_ids)} cases, {sum(1 for i in review_ids if i in filled)} kept from previous file)")


if __name__ == "__main__":
    main()
