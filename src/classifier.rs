/// Rule-based Complexity Scorer (MVP Phase 1)
///
/// Returns a score 1–10 based on:
/// 1. Prompt length (word count)
/// 2. Vocabulary complexity (average word length)
/// 3. Complex/analytical keywords
/// 4. Code/technical keywords
/// 5. Multi-part question indicators

const COMPLEX_KEYWORDS: &[&str] = &[
    "analyze", "analyse", "evaluate", "compare", "design",
    "architecture", "implement", "algorithm", "optimize",
    "comprehensive", "reasoning", "multi-step", "trade-off",
    "in-depth", "explain in detail", "step by step",
];

const CODE_KEYWORDS: &[&str] = &[
    "function", "class", "code", "debug", "refactor",
    "api", "database", "sql", "deploy", "microservice",
    "system", "framework", "library", "async", "concurrency",
];

pub fn score_complexity(prompt: &str) -> u8 {
    if prompt.trim().is_empty() {
        return 1;
    }

    let lower = prompt.to_lowercase();
    let words: Vec<&str> = prompt.split_whitespace().collect();
    let word_count = words.len();

    let mut score: f64 = 0.0;

    // ── 1. Length component (0–3 pts) ──────────────────────────────
    score += match word_count {
        0..=15  => 0.5,
        16..=50 => 1.0,
        51..=150 => 1.8,
        151..=400 => 2.5,
        _ => 3.0,
    };

    // ── 2. Vocabulary complexity via avg word length (0–2 pts) ──────
    let avg_len = words.iter().map(|w| w.len()).sum::<usize>() as f64 / word_count as f64;
    score += match avg_len as u8 {
        0..=4 => 0.0,
        5..=6 => 0.7,
        7..=8 => 1.3,
        _ => 2.0,
    };

    // ── 3. Complex/analytical keywords (0–2 pts) ────────────────────
    let complex_hits = COMPLEX_KEYWORDS.iter().filter(|k| lower.contains(**k)).count();
    score += (complex_hits as f64 * 0.5).min(2.0);

    // ── 4. Code/technical keywords (0–2 pts) ────────────────────────
    let code_hits = CODE_KEYWORDS.iter().filter(|k| lower.contains(**k)).count();
    score += (code_hits as f64 * 0.4).min(2.0);

    // ── 5. Multi-part question bonus (0–1 pt) ────────────────────────
    let multi_q = prompt.matches('?').count() > 1;
    let has_numbered = lower.contains("1.") || lower.contains("1)") || lower.contains("step 1");
    if multi_q || has_numbered {
        score += 0.5;
    }

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
    fn code_keywords_raise_score() {
        let base = score_complexity("Write something.");
        let code = score_complexity("Write a Python class that implements a database connection pool.");
        assert!(code >= base, "code prompt should score >= base");
    }
}
