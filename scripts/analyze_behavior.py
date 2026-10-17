"""
analyze_behavior.py — model behaviour analysis of the full Thai benchmark run (for the paper)
==============================================================================================
Reads existing result files (no API calls) and writes:

  paper/ANALYSIS.md            all tables + bootstrap 95% CIs + benchmark limitations
  paper/figures/*.png, *.pdf   figures for the paper
  paper/slang_review.csv       answer-key review form for native Thai speakers (opens in Excel)

Usage:
    python scripts/analyze_behavior.py

Requires matplotlib (pip install -e ".[paper]")
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

# models with a complete full-suite run — this order also fixes each model's colour
MODELS = [
    ("gemini-3.1-flash-lite", "benchmark_results_gemini_full.json", "Gemini 3.1 Flash-Lite"),
    ("openai/gpt-oss-120b",   "benchmark_results_groq_full.json",   "gpt-oss-120b"),
    ("openai/gpt-oss-20b",    "benchmark_results_groq_full.json",   "gpt-oss-20b"),
]
COLORS = ["#2a78d6", "#eb6834", "#1baf7a"]  # categorical slots 1–3 (all-pairs CVD check passed)
INK, INK_2, GRID = "#0b0b0b", "#52514e", "#e4e3df"

CATEGORIES = ["qa", "translation", "summarization", "classification", "code_thai", "creative"]
DIFFICULTIES = ["easy", "medium", "hard"]

# content groups, matched against each case's (Thai) notes field — first match wins
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


# ── loading ─────────────────────────────────────────────────────────

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
    """Points lost per scorer component (keyword 5 / thai 3 / length 2)."""
    kw = row["keyword_score"] * 5.0
    th = min(row["thai_ratio"] * 10, 3.0)
    length_ok = row.get("length_ok")
    if length_ok is None:  # older result files lack length_ok — recover it from final_score
        length_ok = (row["final_score"] - kw - th) > 1.0
    return 5.0 - kw, 3.0 - th, 0.0 if length_ok else 2.0


# ── statistics ──────────────────────────────────────────────────────

_rng = np.random.default_rng(RNG_SEED)


def mean_ci(xs) -> tuple[float, float, float]:
    xs = np.asarray(xs, dtype=float)
    if len(xs) == 0:
        return float("nan"), float("nan"), float("nan")
    boots = _rng.choice(xs, size=(N_BOOT, len(xs)), replace=True).mean(axis=1)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return float(xs.mean()), float(lo), float(hi)


def rankdata(xs) -> np.ndarray:
    """Average ranks for ties (same as scipy.stats.rankdata)."""
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


# ── figures ─────────────────────────────────────────────────────────

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
    """Cleveland dot plot: row = group, dot = model, bar = 95% CI."""
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

    w("# Thai benchmark — model behaviour analysis (full suite)\n")
    w("> Generated by `python scripts/analyze_behavior.py` — do not edit by hand; rerun when results change.")
    w(f"> Only cases every model answered: **{len(ids)} cases** "
      f"(`gpt-oss-20b` returned empty output on 2 of 600). CI = bootstrap, {N_BOOT} resamples, seed {RNG_SEED}.")
    w("> Score 0–10 = keyword 5 + Thai-character ratio 3 + sufficient length 2 (`scorer.py`) — automatic, not human-judged.\n")

    # 1. overall
    w("## 1. Overall scores\n")
    w("| Model | Mean [95% CI] | Passed | Perfect 10 | Missing keywords | Thai < 50% |")
    w("|---|---|---:|---:|---:|---:|")
    for m in mids:
        fs = [res[m][i]["final_score"] for i in ids]
        w(f"| {label[m]} | {fmt_ci(*mean_ci(fs))} "
          f"| {sum(res[m][i]['passed'] for i in ids)} "
          f"| {sum(f >= 9.995 for f in fs)} "
          f"| {sum(res[m][i]['keyword_score'] < 1 for i in ids)} "
          f"| {sum(res[m][i]['thai_ratio'] < 0.5 for i in ids)} |")
    w("")

    w("**Paired differences (same cases)** — a CI that excludes 0 means a real difference\n")
    w("| Comparison | Mean difference [95% CI] | Wins / ties / losses |")
    w("|---|---|---|")
    for a, b in [(mids[0], mids[1]), (mids[0], mids[2]), (mids[1], mids[2])]:
        d = [res[a][i]["final_score"] - res[b][i]["final_score"] for i in ids]
        win = sum(x > 0.005 for x in d)
        loss = sum(x < -0.005 for x in d)
        w(f"| {label[a]} − {label[b]} | {fmt_ci(*mean_ci(d))} | {win} / {len(d) - win - loss} / {loss} |")
    w("")

    # 2. task category
    w("## 2. By task category\n")
    w("| Category | n | " + " | ".join(label[m] for m in mids) + " |")
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

    # 3. content type
    w("## 3. By content type (derived from case notes)\n")
    group_names = [g for g, _ in GROUPS] + [OTHER_GROUP]
    group_names = [g for g in group_names if any(grp[i] == g for i in ids)]
    w("| Content type | n | " + " | ".join(label[m] for m in mids) + " |")
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
    w("Small groups (dialects, sarcasm) have very wide CIs — read them as trends only.\n")
    dot_plot(group_names, grp_stats, "Score by content type", FIG_DIR / "fig2_content_type",
             xlim=(4, 10.2), row_labels=[f"{g} (n={sum(grp[i] == g for i in ids)})" for g in group_names])
    w("![](figures/fig2_content_type.png)\n")

    # 4. difficulty
    w("## 4. Do the difficulty labels (easy/medium/hard) predict scores?\n")
    w("| Difficulty | n | " + " | ".join(label[m] for m in mids) + " |")
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
    w(f"Spearman ρ (difficulty vs score): {rhos} — values near 0 mean the author-assigned labels do not track actual scores.\n")
    dot_plot(DIFFICULTIES, dif_stats, "Score by human-assigned difficulty label",
             FIG_DIR / "fig3_difficulty", xlim=(7, 10.2))
    w("![](figures/fig3_difficulty.png)\n")

    # 5. where points are lost
    w("## 5. Where points are lost (mean points lost per case)\n")
    w("| Model | Keyword (of 5) | Thai ratio (of 3) | Length (of 2) | Total lost |")
    w("|---|---:|---:|---:|---:|")
    for m in mids:
        lost = np.array([points_lost(res[m][i]) for i in ids])
        k, t, l = lost.mean(axis=0)
        w(f"| {label[m]} | {k:.2f} | {t:.2f} | {l:.2f} | {k + t + l:.2f} |")
    w("")
    w("**Answers with Thai-character ratio < 50%, by category**\n")
    w("| Model | " + " | ".join(CATEGORIES) + " |")
    w("|---|" + "---:|" * len(CATEGORIES))
    for m in mids:
        c = Counter(cases[i].category for i in ids if res[m][i]["thai_ratio"] < 0.5)
        w(f"| {label[m]} | " + " | ".join(str(c.get(cat, 0)) for cat in CATEGORIES) + " |")
    w("")
    w("Note: code characters count as non-Thai, so code_thai is disadvantaged for every model; the difference "
      "between models is explanation text written in English. The Thai component is already full at a 30% ratio "
      "(`min(ratio × 10, 3)`), so it almost never costs points: nearly all differences between models come from keywords.\n")

    # 6. discriminative power
    w("## 6. How well does the benchmark separate models?\n")
    all_perfect = [i for i in ids if all(res[m][i]["final_score"] >= 9.995 for m in mids)]
    identical = [i for i in ids if len({round(res[m][i]["final_score"], 2) for m in mids}) == 1]
    all_fail = [i for i in ids if all(not res[m][i]["passed"] for m in mids)]
    w(f"- Every model scores a perfect 10: **{len(all_perfect)} cases** ({len(all_perfect) / len(ids):.0%})")
    w(f"- Every model gets the same score: **{len(identical)} cases** ({len(identical) / len(ids):.0%}) — these do not separate models")
    per_cat = Counter(cases[i].category for i in all_perfect)
    w("- All-perfect cases by category: " + ", ".join(f"{c} {per_cat.get(c, 0)}" for c in CATEGORIES))
    w(f"- Every model fails: **{len(all_fail)} cases** — " + ", ".join(f"`{i}`" for i in all_fail))
    w("")

    # 7. largest disagreements
    w("## 7. Cases where models differ most (source of examples for the paper)\n")
    w("| Case | Content type | " + " | ".join(label[m] for m in mids) + " | Lowest-scoring answer (first 80 chars) |")
    w("|---|---|" + "---:|" * len(mids) + "---|")
    spread = sorted(ids, key=lambda i: -(max(res[m][i]["final_score"] for m in mids)
                                         - min(res[m][i]["final_score"] for m in mids)))
    for i in spread[:25]:
        worst = min(mids, key=lambda m: res[m][i]["final_score"])
        prev = res[worst][i]["preview"].replace("|", "\\|")
        w(f"| `{i}` | {grp[i]} | " + " | ".join(f"{res[m][i]['final_score']:.1f}" for m in mids)
          + f" | {label[worst]}: {prev} |")
    w("")

    # 8. limitations
    w("## 8. Limitations of this data\n")
    w("- This run stored only the first 80 characters of each answer, so full answers cannot be rescored or reviewed "
      "without rerunning (the runner stores full text, tokens and latency since 2026-10-13).")
    w("- The full suite was run once per model, without per-case tokens/latency; run-to-run variance is measured on the 154 rerun cases — see `paper/STABILITY.md`.")
    w("- Keyword scoring: synonyms earn nothing, multi-option answers collect more keywords, some keys are ambiguous (`cls_50`).")
    w("- Human verification of answer keys and answers: see `paper/HUMAN_REVIEW.md`.")
    w("")

    (OUT_DIR / "ANALYSIS.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    # review form for native speakers — every case that needs real Thai cultural knowledge
    # (slang, idioms, dialect, register, sarcasm); news/scam/other keys come from the prompt text itself
    review_groups = ("Slang / social media", "Idioms / proverbs", "Regional dialects",
                     "Register / formality", "Sarcasm / mixed sentiment")
    review_ids = [i for i in ids if grp[i] in review_groups]
    review_path = OUT_DIR / "slang_review.csv"
    review_cols = ["เฉลยถูกไหม (Y/N)", "ความหมายที่ถูก (ถ้าเฉลยผิด)",
                   *[f"{label[m]} ถูกไหม (Y/N/?)" for m in mids], "หมายเหตุ"]
    # keep what reviewers already filled in — a rerun must not overwrite it
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
