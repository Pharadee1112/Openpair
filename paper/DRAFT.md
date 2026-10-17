# Where Free-Tier LLMs Break on Thai: A 600-Case Behavioural Study for Cost-Aware Routing

> DRAFT v0.1 — 2026-10-17. Thai version: `paper/DRAFT_TH.md` — keep both in sync. Numbers come from `paper/ANALYSIS.md` (regenerate with `python scripts/analyze_behavior.py`).
> Human-review numbers come from `paper/HUMAN_REVIEW.md` (`python scripts/analyze_human_review.py`).

## Abstract

Cost-aware LLM routers send each prompt to the cheapest model that can handle it, but the quality signal they route on is usually measured in English. We built OpenPair, a router restricted to free-tier Gemini and Groq models, and a 600-case Thai benchmark covering six task categories (QA, translation, summarisation, classification, code with Thai context, creative writing) with content drawn from September 2026 news, social-media slang, idioms, dialects, register and sarcasm. We evaluate Gemini 3.1 Flash-Lite, gpt-oss-120b and gpt-oss-20b on the 598 cases all three completed. Gemini scores 9.40 / 10 [95% CI 9.33–9.48], significantly above gpt-oss-120b (8.79) and gpt-oss-20b (8.71), while the two gpt-oss sizes are statistically indistinguishable (paired difference 0.09 [−0.01, 0.18]). The gap is largest on slang (8.88 vs 7.68 / 7.38) and idioms, where the gpt-oss models produce fluent, confident but wrong definitions. A blind review of 462 answers by a native speaker confirms the gap — 100%, 76% and 60% of decidable answers correct — and shows our keyword scorer agrees with the human only 84% of the time. We also report what our benchmark cannot measure: author-assigned difficulty labels do not predict scores (Spearman ρ between −0.10 and −0.03), 32% of cases are solved perfectly by every model, and our keyword scorer rewards verbose multi-option answers. We release the cases, scorer and analysis scripts and list concrete extensions for future work.

## 1. Introduction

- Problem: developers using several LLM providers either hard-code one expensive model or pay for a strong model on easy prompts. Routers (FrugalGPT, RouteLLM, AutoMix) address cost, but their routing signals are learned or validated on English benchmarks.
- For Thai, an "it can do Thai" flag is not enough: models that look fluent can misunderstand slang or sarcasm, and that failure is invisible to a router that only checks the output language.
- Constraint that shaped this work: only free-tier APIs (Gemini, Groq) and a 4 GB consumer GPU. This is realistic for students and small teams in Thailand, and it limits which models and how many runs we could afford.
- Contributions:
  1. A 600-case Thai benchmark (100 per category) with content-type annotations (slang, current news, idioms, dialect, register, sarcasm, scam detection).
  2. A behavioural comparison of three free-tier models with bootstrap CIs and paired tests, broken down by category, content type and difficulty.
  3. An honest account of the benchmark's own limits (ceiling effects, label validity, scorer bias) and of the models' weaknesses, written as guidance for researchers extending this work.
  4. OpenPair, an open-source router (Rust core, Python wrapper) whose Thai routing table is set from these measurements.
- Scope: this is a measurement study. The research question is where models fail on Thai, not how to make them better, so training models (e.g. fine-tuning) is deliberately outside this paper; Section 8 describes how the failures found here can serve as targets for that work.

## 2. Related Work

**Cost-aware routing and cascades.** FrugalGPT (Chen, Zaharia & Zou, 2023/TMLR 2024) frames LLM cost reduction as prompt adaptation, model approximation and cascades, and learns which combination of models to query per input, reporting up to 98% cost reduction at GPT-4-level accuracy. RouteLLM (Ong et al., ICLR 2025) trains routers between a strong and a weak model from human preference data and reports over 2× cost savings without quality loss, with routers that transfer to unseen model pairs. AutoMix (Aggarwal, Madaan et al., NeurIPS 2024) routes to a larger model based on a small model's few-shot self-verification, with a meta-verifier to correct noisy self-checks. All three learn or validate their routing signal on English tasks. OpenPair is far simpler — a rule-based complexity score plus a measured per-model Thai score — and our contribution is not the router but the evidence about what such a Thai signal should and should not capture.

**Thai and Southeast Asian evaluation.** Typhoon (Pipatanakul et al., 2023) introduced ThaiExam, built from Thai national and professional exams (ONET, IC, later TGAT, TPAT-1, A-Level), now hosted as a HELM leaderboard. Typhoon 2 (Pipatanakul et al., 2024) and the Thai LLM Leaderboard (SCB 10X, VISTEC, SEACrowd) add a Thai MT-Bench judged by an LLM. SEA-HELM (Susanto et al., 2025) evaluates Thai among five SEA languages across NLP classics, LLM-specific skills, linguistics, culture and safety. Limkonchotiwat et al. (2025) assess Thai dialect performance with automatic benchmarks and human evaluation. These benchmarks focus on exam knowledge or general instruction following; ours targets the content that changes fastest and that routers are least likely to have seen — slang, social-media register and news from the evaluation month — and is designed to be cheap enough to rerun on free tiers.

**Automatic evaluation and its biases.** Zheng et al. (2023) show that strong LLM judges agree with humans about as often as humans agree with each other, but document position and verbosity bias. We deliberately avoided an LLM judge (cost, and the judge would itself be one of the models under study) and used keyword matching instead; Section 7 shows our scorer has its own verbosity bias.

**Hallucination.** Huang et al. (2023) separate factuality hallucination (conflict with world facts) from faithfulness hallucination (conflict with the input). The confident wrong slang definitions in Section 6 are factuality hallucinations about culture-specific knowledge.

## 3. System: OpenPair

- Rust core (`classifier.rs`, `router.rs`, `registry.rs`) scores prompt complexity 1–10, detects Thai, and picks the cheapest model in the required tier; Python layer (`client.py`, `caller.py`) calls the provider and falls back on 429/503, ending at a local Ollama model.
- Registry restricted to free-tier models (Gemini + Groq) since 2026-10-02.
- Thai routing table, set from the results in Section 5: before this study, Thai prompts went to `gemini-3.1-flash-lite` (simple), `gpt-oss-20b` (medium) and `gpt-oss-120b` (complex), on the assumption that larger models handle harder Thai better. Section 5 shows Gemini Flash-Lite beats both gpt-oss models at every difficulty level and that 120b is no better than 20b, so OpenPair now routes **all Thai prompts to `gemini-3.1-flash-lite`**; Groq's gpt-oss models remain as the rate-limit fallback. This is the study's direct practical outcome: a size-based routing intuition was wrong for Thai.

## 4. Benchmark and Method

### 4.1 Cases
- 600 cases, 100 per category; 20 "core" cases from the original suite plus 580 added in September 2026.
- Content types (from case notes, one group per case): slang/social media 112, current news (Sep 2026, article text included in the prompt) 140, idioms/proverbs 18, regional dialects 3, register/formality 15, sarcasm/mixed sentiment 6, scam detection 15, other 289 (counts over the 598 analysed cases).
- Each case has a prompt, expected keywords, a keyword threshold, a minimum Thai-character ratio, a minimum length and an author-assigned difficulty (easy 164 / medium 300 / hard 134).

### 4.2 Models and runs
- `gemini-3.1-flash-lite` (Google AI Studio free tier, run 2026-10-01), `openai/gpt-oss-120b` and `openai/gpt-oss-20b` (Groq free tier, run 2026-10-02; open-weight MoE models, OpenAI 2025).
- One run per model, provider default temperature, `max_tokens` 2048. gpt-oss-20b returned empty responses on 2 cases after retries; we analyse the 598 cases all models completed.
- Excluded: `gemini-3.6-flash` (free quota too small for 600 cases; core-20 only, 5.74), `gemini-3.1-pro-preview` (free-tier quota is 0). Local `qwen2.5:3b` via Ollama scored 8.10 on core-20 only and is reported as a fallback, not compared.

### 4.3 Scoring
- `final = 5 × keyword_fraction + min(10 × thai_ratio, 3) + 2 × length_ok` (0–10). A case passes if keyword fraction ≥ threshold, Thai ratio ≥ minimum and length is sufficient.
- No LLM judge. Human verification of slang/idiom/register/sarcasm cases: a native Thai speaker reviewed all 154 such cases (462 answers); answer keys checked and confirmed for the original 93 slang cases, and accepted for the remaining 61 on the strength of that check (not individually verified — see Limitations); each answer was marked correct (Y), wrong (N) or undecidable (?) blind — one answer per line, model names and machine scores hidden, answer order shuffled per question (`scripts/review_simple.py`).
- Statistics: bootstrap 95% CIs (5 000 resamples, seed 20261013); paired differences on the same cases; Spearman ρ for difficulty.

## 5. Results

### 5.1 Overall

| Model | Mean [95% CI] | Pass | Perfect 10 |
|---|---|---:|---:|
| Gemini 3.1 Flash-Lite | 9.40 [9.33, 9.48] | 592 | 370 |
| gpt-oss-120b | 8.79 [8.68, 8.91] | 545 | 265 |
| gpt-oss-20b | 8.71 [8.59, 8.83] | 526 | 257 |

Paired: Gemini − 120b = 0.61 [0.51, 0.71] (wins/ties/losses 231/309/58); Gemini − 20b = 0.70 [0.59, 0.80]; 120b − 20b = 0.09 [−0.01, 0.18]. **A 6× larger gpt-oss model buys no measurable Thai quality here** (117B vs 21B total parameters, 5.1B vs 3.6B active).

### 5.2 By category (Figure 1)
Gemini leads in every category. The gap is widest in QA (9.35 vs 8.12 / 8.00) and translation (9.22 vs 8.29 / 7.93), narrowest in classification (9.89 vs 9.65 / 9.55). The only reversal between gpt-oss sizes is code_thai, where 20b (9.15) beats 120b (8.84).

### 5.3 By content type (Figure 2)
Slang is the hardest content for all models (Gemini 8.88, 120b 7.68, 20b 7.38), followed by idioms (9.35 / 8.08 / 7.75). Current news, where the needed facts are in the prompt, is easy for all (9.69 / 9.15 / 8.98). Scam detection is solved perfectly by all three. Dialect (n = 3) and sarcasm (n = 6) are too small for conclusions.

**Interpretation.** Where the answer is in the context, the models are close; where the answer needs culture-specific knowledge the prompt does not supply, they diverge. This is the knowledge a router's "Thai score" should capture and a generic language-ID check cannot.

### 5.4 Where points are lost
Almost all lost points are keywords: Gemini loses 0.60 per case, 120b 1.20, 20b 1.28; the Thai-ratio and length components cost ≤ 0.01. So the scorer effectively measures content, not language.

### 5.5 Human verification (462 answers, blind)

Answers judged from the stored 80-character previews; `?` (cut off before the meaning) is excluded from rates.

| Model | Correct | Wrong | Undecidable | Correct rate |
|---|---:|---:|---:|---:|
| Gemini 3.1 Flash-Lite | 88 | 0 | 66 | 100% (88/88) |
| gpt-oss-120b | 92 | 29 | 33 | 76% (92/121) |
| gpt-oss-20b | 75 | 49 | 30 | 60% (75/124) |

By category, gpt-oss is close to Gemini on classification (91% each vs 100%) but far behind on slang QA (67% / 50%), translation (76% / 45%) and creative writing with slang (36% / 23%). Unlike the keyword scores, **human judgement separates the two gpt-oss sizes** (76% vs 60%).

**Keyword scorer vs human.** On the 333 decidable answers the scorer's pass/fail agrees with the human 84% of the time. In 31 cases it passed an answer the human marked wrong — up to a full 10.0 for literal translations of idioms (`tr_21` "Actions speak louder than words", `tr_24` "call it a day") and 9.0 for southern-dialect dialogue written in Isan (`cre_92`). Wrong answers still average 6.33 / 10 against 8.96 for correct ones, so the scorer ranks models in the right order but overstates how good the weaker ones are.

**Caveat.** Gemini's answers are more often undecidable (66 vs 30–33) because they tend to open with a preamble ("choose a style that suits you…") that fills the 80-character preview; its 100% is measured on its more direct answers only.

## 6. Model Weaknesses (qualitative)

Examples are quoted from the stored 80-character previews — the same text the human reviewer judged (Section 5.5).
  
1. **Confident wrong slang definitions (gpt-oss).** e.g. `qa_50` "ทัวร์ลง" (online pile-on) explained by 120b as "taking action on something"; `qa_65` "CF" in live-selling (confirm an order) explained by 20b as "Cash Flow"; `qa_48` "ชิป" glossed by 20b as English "cheap". The answers are fluent, structured, and in Thai — nothing in their form signals the error. On the 39 slang/idiom QA cases the human marked 8 of 24 decidable 120b answers and 11 of 22 decidable 20b answers wrong; none of Gemini's 28.
2. **Invented or literal slang in translation (gpt-oss).** Human-marked wrong translations: 10 of 41 (120b) and 24 of 44 (20b). Typical failures are literal renderings (`tr_61` "slaps" → "ตบ", `tr_69` "flexing" → "แสดง"), non-words (`tr_77` "กรีกออกไป", `tr_80` "แซงซี่"), and wrong false friends (`tr_68` "MC", which means *emcee* in Thai).
3. **Missing sarcasm.** `cls_14`, `cls_23`, `cls_26`: gpt-oss labels sarcastic complaints as positive, taking praise words literally.
4. **Code tasks answered in English.** Thai ratio < 50% on code_thai: 19 (Gemini), 70 (120b), 79 (20b) of 99 — gpt-oss writes explanations around the code in English even when asked in Thai. The scorer barely penalises this (Thai credit saturates at 30%).
5. **Format drift.** gpt-oss often returns markdown tables for short QA/idiom answers (`qa_69`, `sum_96`); harmless to keyword scoring, relevant for chat UIs.
6. **Empty responses.** gpt-oss-20b returned empty output on 2/600 cases consistently.

## 7. Limitations of Our Method

1. **Keyword scoring.** Synonyms get no credit (`cls_50`: "พลังงาน" vs key "เทคโนโลยี", fixed after the run); answers listing several options collect more keywords — a verbosity bias like the one Zheng et al. found in LLM judges.
2. **Ceiling.** 193 cases (32%) are perfect for every model; 227 (38%) give identical scores to all three. A third of the benchmark does not separate these models. Classification is the most saturated (88 of 100 perfect for all).
3. **Difficulty labels are not valid.** Spearman ρ between author-assigned difficulty and score: −0.026, −0.058, −0.100. "Hard" was our guess, not a property the models experience.
4. **Truncated logs.** The analysed runs stored only the first 80 characters of each response, so human review sometimes cannot judge correctness and rescoring is impossible without rerunning. Fixed in the runner on 2026-10-13 (full text, tokens, latency).
5. **One run per model**, provider-default sampling: no estimate of run-to-run variance.
6. **Small and uneven subgroups** (dialect 3, sarcasm 6, idioms 18) and only three models, all reachable on free tiers.
7. **Single annotator** for human verification; no inter-annotator agreement. Answer keys for 61 of the 154 reviewed cases were accepted without case-by-case checking. Review was blind to model name, but answer style may still reveal it; and 129 of 462 answers (28%) were undecidable from the 80-character previews, unevenly across models (Section 5.5).
8. **Shelf life.** Slang and news cases age within months; results describe models as of October 2026.

## 8. Future Work (how to extend this)

1. **Rerun with full logging** (already supported) and add per-case latency/tokens to put cost on the routing axis.
2. **Replace or complement keywords** with a rubric-based LLM judge plus human calibration on the 154-case review set; report judge–human agreement.
3. **Drop or harden saturated cases**; derive difficulty empirically (e.g. from the share of models that fail) instead of author labels.
4. **Grow the culture-dependent subsets** — dialects, sarcasm, idioms — with several annotators.
5. **Fine-tuning (out of scope by design).** This paper measures where models fail rather than trying to fix them, so no model was trained. The failure sets identified here — slang definitions, idiom translation, slang-heavy writing — are natural targets for a follow-up that fine-tunes a small open model and re-runs this benchmark and review sheet to measure the change. A format specification, a leakage checker and 24 seed examples are in `finetune/`.
6. **More models**: paid tiers (`gemini-3.1-pro-preview`), Thai-specific models (Typhoon, OpenThaiGPT), local models beyond `qwen2.5:3b`.
7. **Learned routing**: use the per-case scores here as training signal for a RouteLLM-style router conditioned on content type.
8. **Refresh schedule**: re-collect news and slang every 6–12 months.

## 9. Conclusion

We asked whether free-tier LLMs can be trusted with Thai prompts whose answers depend on culture rather than on the context given. On 598 cases, Gemini 3.1 Flash-Lite outperformed both gpt-oss models in every category and at every difficulty, and a blind native-speaker review of 462 answers widened the gap: all of Gemini's decidable answers were correct, against 76% for gpt-oss-120b and 60% for gpt-oss-20b. The failures concentrate in slang, idiom translation and slang-heavy writing, and they are fluent and confident, so neither a language check nor our keyword scorer — which agreed with the human 84% of the time and passed 31 wrong answers — reliably catches them.

In practice, the evidence reversed our routing intuition: OpenPair now sends all Thai prompts to the smallest Gemini model rather than escalating harder ones to larger models. Methodologically, a third of our benchmark is saturated and our difficulty labels do not predict scores. We release the cases, the review sheet and the analysis scripts so that future work can replace keyword scoring and harden the saturated cases, and so that work on improving models — which this study deliberately leaves aside — starts from a measured map of where Thai failures occur.

## References

- Chen, L., Zaharia, M., & Zou, J. (2024). FrugalGPT: How to Use Large Language Models While Reducing Cost and Improving Performance. Transactions on Machine Learning Research. arXiv:2305.05176.
- Ong, I., et al. (2025). RouteLLM: Learning to Route LLMs from Preference Data. ICLR 2025. arXiv:2406.18665.
- Aggarwal, P., Madaan, A., Anand, A., et al. (2024). AutoMix: Automatically Mixing Language Models. NeurIPS 2024. arXiv:2310.12963.
- Pipatanakul, K., Jirabovonvisut, P., Manakul, P., Sripaisarnmongkol, S., Patomwong, R., Chokchainant, P., & Tharnpipitchai, K. (2023). Typhoon: Thai Large Language Models. arXiv:2312.13951.
- Pipatanakul, K., Manakul, P., Nitarach, N., et al. (2024). Typhoon 2: A Family of Open Text and Multimodal Thai Large Language Models. arXiv:2412.13702.
- Stanford CRFM (2024). ThaiExam Leaderboard in HELM. https://crfm.stanford.edu/2024/09/04/thaiexam.html
- Susanto, Y., et al. (2025). SEA-HELM: Southeast Asian Holistic Evaluation of Language Models. Findings of ACL 2025. arXiv:2502.14301.
- Limkonchotiwat, P., Masuk, K., Nonesung, S., Mai-On, C., Nutanong, S., Ponwitayarat, W., & Manakul, P. (2025). Assessing Thai Dialect Performance in LLMs with Automatic Benchmarks and Human Evaluation. arXiv:2504.05898.
- Zheng, L., et al. (2023). Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena. arXiv:2306.05685. NeurIPS 2023.
- Huang, L., et al. (2023). A Survey on Hallucination in Large Language Models: Principles, Taxonomy, Challenges, and Open Questions. arXiv:2311.05232. ACM TOIS.
- OpenAI (2025). gpt-oss-120b & gpt-oss-20b Model Card. arXiv:2508.10925.
