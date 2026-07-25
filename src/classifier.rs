/// Rule-based Complexity Scorer (MVP Phase 1)
///
/// Returns a score 1–10 based on:
/// 1. Prompt length (word count)
/// 2. Vocabulary complexity (average word length)
/// 3. Complex/analytical keywords
/// 4. Code/technical keywords
/// 5. Multi-part question indicators
/// 6. Thai language detection (boosts score slightly — Thai needs stronger models)

/// Word-start stems for complex/analytical keywords, so that inflected
/// forms (analysis, analyzing, evaluation, comparing, ...) match without
/// needing every surface form spelled out. Matched against whole tokens
/// via `starts_with`, not raw substring search, to avoid false hits.
const COMPLEX_KEYWORD_STEMS: &[&str] = &[
    "analy",        // analyze, analysis, analyzing, analytical
    "evaluat",       // evaluate, evaluation, evaluating
    "compar",        // compare, comparison, comparing
    "design",        // design, designing, designed
    "architect",     // architecture, architectural
    "implement",      // implement, implementation, implementing
    "algorithm",      // algorithm, algorithmic
    "optimi",         // optimize/optimise, optimization, optimizing
    "comprehensiv",   // comprehensive, comprehensively
    "reason",         // reasoning, reason, reasoned
];

/// Multi-word / hyphenated complex-keyword phrases, matched as substrings
/// since they span token boundaries.
const COMPLEX_KEYWORD_PHRASES: &[&str] = &[
    "multi-step", "trade-off", "in-depth", "explain in detail", "step by step",
];

const CODE_KEYWORDS: &[&str] = &[
    "function", "class", "code", "debug", "refactor",
    "api", "database", "sql", "deploy", "microservice",
    "system", "framework", "library", "async", "concurrency",
];

/// Thai analytical/complex keywords (written in Thai script)
const THAI_COMPLEX_KEYWORDS: &[&str] = &[
    "วิเคราะห์",     // analyze
    "เปรียบเทียบ",  // compare
    "ออกแบบ",       // design
    "อธิบาย",       // explain
    "สรุป",         // summarize
    "ประเมิน",      // evaluate
    "พัฒนา",        // develop
    "แนะนำ",        // recommend
    "ขั้นตอน",      // step-by-step
    "กลยุทธ์",      // strategy
];

/// Detect whether the prompt contains Thai characters (Unicode U+0E00–U+0E7F).
pub fn is_thai(text: &str) -> bool {
    text.chars().any(|c| ('\u{0E00}'..='\u{0E7F}').contains(&c))
}

/// Return the fraction of characters that are Thai (0.0–1.0).
pub fn thai_ratio(text: &str) -> f64 {
    let chars: Vec<char> = text.chars().collect();
    if chars.is_empty() {
        return 0.0;
    }
    let thai_count = chars.iter().filter(|&&c| ('\u{0E00}'..='\u{0E7F}').contains(&c)).count();
    thai_count as f64 / chars.len() as f64
}

pub fn score_complexity(prompt: &str) -> u8 {
    if prompt.trim().is_empty() {
        return 1;
    }

    let lower = prompt.to_lowercase();
    let words: Vec<&str> = prompt.split_whitespace().collect();
    let word_count = words.len();

    // Thai script doesn't reliably delimit words with spaces the way
    // English does — a whole Thai clause can arrive as a single
    // whitespace-split "word". Decide up front so length and vocabulary
    // scoring can use a script-appropriate signal instead of collapsing
    // every Thai prompt onto the same bucket.
    let ratio = thai_ratio(prompt);
    let is_thai_text = ratio > 0.3;

    let mut score: f64 = 0.0;

    // ── 1. Length component (0–3 pts) ──────────────────────────────
    if is_thai_text {
        // Use character count instead of whitespace word count — it
        // actually scales with sentence length for space-sparse Thai text.
        let char_count = prompt.chars().filter(|c| !c.is_whitespace()).count();
        score += match char_count {
            0..=6 => 0.2,
            7..=15 => 0.5,
            16..=30 => 0.9,
            31..=50 => 1.3,
            51..=80 => 1.6,
            81..=150 => 2.0,
            151..=400 => 2.5,
            401..=1000 => 2.8,
            _ => 3.0,
        };
    } else {
        score += match word_count {
            0..=2 => 0.2,
            3..=5 => 0.5,
            6..=10 => 0.9,
            11..=15 => 1.3,
            16..=25 => 1.6,
            26..=50 => 2.0,
            51..=150 => 2.5,
            151..=400 => 2.8,
            _ => 3.0,
        };
    }

    // ── 2. Vocabulary complexity via avg word length (0–2 pts) ──────
    // Skipped for Thai: whitespace-based average word length is not a
    // meaningful signal when words aren't space-delimited (it maxes out
    // for both a short greeting and a long sentence alike).
    if !is_thai_text {
        let avg_len = words.iter().map(|w| w.len()).sum::<usize>() as f64 / word_count as f64;
        score += match avg_len as u8 {
            0..=4 => 0.0,
            5..=6 => 0.7,
            7..=8 => 1.3,
            _ => 2.0,
        };
    }

    // ── 3. Complex/analytical keywords (0–3.5 pts) ──────────────────
    // Tokenize (splitting on anything but letters/digits/hyphen) so stems
    // are matched against whole words, not arbitrary substrings.
    let tokens: Vec<&str> = lower
        .split(|c: char| !c.is_alphanumeric() && c != '-')
        .filter(|s| !s.is_empty())
        .collect();
    let stem_hits = tokens
        .iter()
        .filter(|t| COMPLEX_KEYWORD_STEMS.iter().any(|stem| t.starts_with(stem)))
        .count();
    let phrase_hits = COMPLEX_KEYWORD_PHRASES.iter().filter(|p| lower.contains(**p)).count();
    let complex_hits = stem_hits + phrase_hits;
    score += (complex_hits as f64 * 0.8).min(3.5);

    // ── 4. Code/technical keywords (0–2 pts) ────────────────────────
    let code_hits = CODE_KEYWORDS.iter().filter(|k| lower.contains(**k)).count();
    score += (code_hits as f64 * 0.4).min(2.0);

    // ── 5. Multi-part question bonus (0–1 pt) ────────────────────────
    let multi_q = prompt.matches('?').count() > 1;
    let has_numbered = lower.contains("1.") || lower.contains("1)") || lower.contains("step 1");
    if multi_q || has_numbered {
        score += 0.5;
    }

    // ── 6. Thai language boost (0–1.5 pts) ───────────────────────────
    // Thai prompts are harder for most models → bump the score so routing
    // picks a more capable model even for "simple-looking" Thai text.
    if ratio > 0.3 {
        score += 0.5 + ratio; // up to +1.5 for fully-Thai prompt
    }

    // ── 7. Thai complex-keyword hits (0–1 pt) ────────────────────────
    let thai_hits = THAI_COMPLEX_KEYWORDS.iter().filter(|k| prompt.contains(**k)).count();
    score += (thai_hits as f64 * 0.25).min(1.0);

    (score.round() as u8).clamp(1, 10)
}

// ─── Tests ─────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_prompt_returns_one() {
        assert_eq!(score_complexity(""), 1);
        assert_eq!(score_complexity("   "), 1);
    }

    #[test]
    fn simple_prompts_score_low() {
        assert!(score_complexity("Hi!") <= 3);
        assert!(score_complexity("What is 2 + 2?") <= 3);
        assert!(score_complexity("Hello, how are you?") <= 3);
    }

    #[test]
    fn medium_prompts_score_mid() {
        let s = score_complexity(
            "Please summarize the key points of this article about renewable energy.",
        );
        assert!((2..=6).contains(&s), "expected 2–6, got {s}");
    }

    #[test]
    fn complex_prompts_score_high() {
        let s = score_complexity(
            "Design a comprehensive microservices architecture for an e-commerce platform. \
             Include authentication, product catalog, order management, and payment processing. \
             Analyze trade-offs between synchronous and asynchronous communication patterns, \
             and implement circuit breakers for resilience.",
        );
        assert!(s >= 6, "expected ≥ 6, got {s}");
    }

    #[test]
    fn score_is_always_1_to_10() {
        let prompts = [
            "",
            "hi",
            "What time is it?",
            &"word ".repeat(600),
        ];
        for p in &prompts {
            let s = score_complexity(p);
            assert!((1..=10).contains(&s), "score {s} out of range for: {p:.30}...");
        }
    }

    #[test]
    fn suffix_variants_are_recognized() {
        // "analysis"/"comparison" should now count as keyword hits, not just
        // the bare "analyze"/"compare" forms.
        let base = score_complexity("Please write a short summary of the weekly team meeting notes");
        let analysis = score_complexity("Please write a short analysis of the weekly team meeting notes");
        let comparison = score_complexity("Please write a short comparison of the weekly team meeting notes");
        assert!(analysis > base, "analysis should score above a keyword-free baseline");
        assert!(comparison > base, "comparison should score above a keyword-free baseline");
    }

    #[test]
    fn length_buckets_are_granular() {
        // A one-word prompt and a moderately long keyword-free prompt should
        // no longer collapse onto the same length-component score.
        let one_word = score_complexity("Hi");
        let longer = score_complexity(
            "This is a fairly ordinary sentence with quite a few plain, everyday words \
             strung together one after another just to pad out the total word count here",
        );
        assert!(longer > one_word, "longer prompt should score above a one-word prompt");
    }

    #[test]
    fn complex_13_word_sentence_scores_moderately_high() {
        let s = score_complexity(
            "Analyze the trade-offs between microservices architecture and monolithic design patterns in software systems",
        );
        assert!((6..=7).contains(&s), "expected 6-7, got {s}");
    }

    #[test]
    fn code_keywords_raise_score() {
        let base = score_complexity("Write something.");
        let code = score_complexity("Write a Python class that implements a database connection pool.");
        assert!(code >= base, "code prompt should score >= base");
    }

    #[test]
    fn thai_complex_scores_above_thai_simple() {
        // A short Thai greeting has no space-delimited "words" to speak of,
        // so the (now Thai-skipped) whitespace word-length heuristic used to
        // max out for both prompts alike and collapse them onto the same
        // score. Character-count length + Thai keyword hits should now
        // separate them.
        let simple = score_complexity("สวัสดีครับ วันนี้อากาศเป็นอย่างไร");
        let complex = score_complexity(
            "ช่วยวิเคราะห์เปรียบเทียบข้อดีข้อเสียของระบบฐานข้อมูลแบบกระจายและออกแบบสถาปัตยกรรมที่เหมาะสม",
        );
        assert!(
            complex > simple,
            "expected complex Thai prompt to score above simple Thai greeting, got complex={complex} simple={simple}"
        );
    }

    #[test]
    fn thai_simple_greeting_scores_low() {
        let s = score_complexity("สวัสดีครับ วันนี้อากาศเป็นอย่างไร");
        assert!(s <= 4, "expected a short Thai greeting to score low, got {s}");
    }
}
