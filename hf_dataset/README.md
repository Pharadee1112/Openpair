---
language:
  - th
  - en
license: unknown
pretty_name: OpenPair Thai Benchmark
size_categories:
  - n<1K
task_categories:
  - question-answering
  - translation
  - summarization
  - text-classification
  - text-generation
tags:
  - thai
  - slang
  - evaluation
  - llm-routing
  - human-evaluation
configs:
  - config_name: benchmark
    data_files: data/benchmark.jsonl
  - config_name: human_review
    data_files: data/human_review.jsonl
---

# OpenPair Thai Benchmark

A 600-case Thai benchmark for studying where large language models fail on Thai — especially content that depends on culture rather than on the text given (slang, idioms, register, sarcasm) — plus 462 blind human verdicts on model answers. It accompanies the paper draft *Where Free-Tier LLMs Break on Thai: A 600-Case Behavioural Study for Cost-Aware Routing* (`paper/DRAFT.md` in the [OpenPair repository](https://github.com/Pharadee1112/Openpair)).

**Prompts, answers and expected keywords are in Thai and are intentionally not translated** — they are what the benchmark measures. Field names, labels and this card are in English.

## Configurations

### `benchmark` — 600 cases

100 cases in each of six task categories: `qa`, `translation`, `summarization`, `classification`, `code_thai`, `creative`.

| Field | Type | Description |
|---|---|---|
| `id` | string | Case id, e.g. `qa_52` |
| `category` | string | Task category (one of the six above) |
| `difficulty` | string | `easy` / `medium` / `hard`, assigned by the author — **not predictive of scores** (see Limitations) |
| `content_type` | string | Derived from `notes`: `Slang / social media`, `Current news (Sep 2026)`, `Idioms / proverbs`, `Regional dialects`, `Register / formality`, `Sarcasm / mixed sentiment`, `Scam detection`, `Other` |
| `prompt` | string | Prompt sent to the model (Thai) |
| `expected_keywords` | list[string] | Words/phrases a correct answer should contain (Thai) |
| `keyword_threshold` | float | Fraction of keywords required to pass |
| `min_thai_ratio` | float | Minimum fraction of Thai characters in the answer |
| `min_length` | int | Minimum answer length in characters |
| `notes` | string | Author's note on the case (Thai, raw) |

Content types: other 290, current news 140, slang 113, idioms 18, register 15, scam detection 15, sarcasm 6, dialects 3. News cases include the article text in the prompt, so they test reading, not knowledge of recent events.

### `human_review` — 462 verdicts

One native Thai speaker judged every answer to the 154 culture-dependent cases (slang, idioms, dialect, register, sarcasm) from three models — `gemini-3.1-flash-lite`, `openai/gpt-oss-120b`, `openai/gpt-oss-20b` — **blind** (model names and machine scores hidden, answer order shuffled).

| Field | Type | Description |
|---|---|---|
| `case_id` | string | Matches `id` in `benchmark` |
| `category` | string | Task category |
| `model` | string | Model that produced the answer |
| `answer_preview` | string | First 80 characters of the answer — the text the reviewer judged (Thai) |
| `human_verdict` | string | `Y` correct, `N` wrong, `?` cut off before it could be judged |
| `reviewer_note_th` | string | Reviewer's note, raw (Thai) |
| `reviewer_note_en` | string | Short English translation of the note |
| `machine_score` | float | Automatic score 0–10 for the same answer |
| `machine_passed` | bool | Automatic pass/fail for the same answer |

## Scoring

`score = 5 × keyword_fraction + min(10 × thai_ratio, 3) + 2 × length_ok` (0–10). A case passes when the keyword fraction, Thai ratio and length all meet the case's thresholds. Implementation: `python/openpair/benchmark/scorer.py`.

## Headline results (from the paper)

| Model | Mean score, 598 cases [95% CI] | Human: correct / decidable |
|---|---|---|
| Gemini 3.1 Flash-Lite | 9.40 [9.33, 9.48] | 88 / 88 (100%) |
| gpt-oss-120b | 8.79 [8.68, 8.91] | 92 / 121 (76%) |
| gpt-oss-20b | 8.71 [8.59, 8.83] | 75 / 124 (60%) |

The keyword scorer agrees with the human on 84% of decidable answers and passed 31 answers the human marked wrong. A second run of the 154 cases moves model means by ≤ 0.11 but flips pass/fail on 12–13% of cases for gpt-oss vs 2% for Gemini.

## Limitations

- **Keyword scoring** misses synonyms and rewards verbose multi-option answers.
- **Ceiling**: 32% of cases are solved perfectly by every model tested.
- **Difficulty labels** do not predict scores (Spearman ρ −0.10 to −0.03).
- **Human review**: a single annotator; judged from 80-character previews, so 129 of 462 answers (28%) were undecidable, unevenly across models (Gemini answers often open with a preamble). Answer keys for 61 of the 154 reviewed cases were accepted without case-by-case checking.
- **Shelf life**: slang and news cases describe language as of September–October 2026 and age within months.
- Only free-tier models were evaluated, each with provider-default sampling.

## Reproducing

```bash
python run_benchmark.py --suite full --models <model ids>   # needs API keys
python scripts/analyze_behavior.py                          # paper/ANALYSIS.md
python scripts/analyze_human_review.py                      # paper/HUMAN_REVIEW.md
python scripts/analyze_stability.py                         # paper/STABILITY.md
python scripts/export_hf_dataset.py                         # regenerate these data files
```

## License

**Not yet chosen** (`license: unknown`). Some news-based prompts quote short passages of September 2026 Thai news coverage; check this before choosing a license and publishing.
