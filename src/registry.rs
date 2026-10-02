
/// Model Registry — in-memory store of AI model metadata
///
/// For MVP: hard-coded defaults across 4 providers (OpenAI, Anthropic, Google, Groq)
/// Future: hot-reload from YAML/JSON config
/// Prices per 1k tokens, current as of 2026-07-25.

#[derive(Debug, Clone, PartialEq)]
pub enum ModelTier {
    Small,  // Complexity 1–3 : fast, cheap (Haiku 4.5, Flash-Lite, GPT-5.4 Nano)
    Mid,    // Complexity 4–6 : balanced  (Sonnet 5, Gemini 3.6 Flash)
    Top,    // Complexity 7–9 : quality   (GPT-5.5, Opus 5)
    Expert, // Complexity 10  : best + long-context (Gemini 3.1 Pro)
}

impl ModelTier {
    pub fn as_str(&self) -> &'static str {
        match self {
            ModelTier::Small  => "small",
            ModelTier::Mid    => "mid",
            ModelTier::Top    => "top",
            ModelTier::Expert => "expert",
        }
    }

    pub fn from_score(score: u8) -> Self {
        match score {
            1..=3 => ModelTier::Small,
            4..=6 => ModelTier::Mid,
            7..=9 => ModelTier::Top,
            _     => ModelTier::Expert,
        }
    }
}

// context_window / cost_per_1k_output / thai_score are catalog data that the router
// doesn't read yet (scripts/update_registry_scores.py patches thai_score in this file).
#[allow(dead_code)]
#[derive(Debug, Clone)]
pub struct ModelMeta {
    pub id:                  &'static str,
    pub name:                &'static str,
    pub provider:            &'static str,  // "openai" | "anthropic" | "google" | "groq"
    pub tier:                ModelTier,
    pub context_window:      u32,
    pub cost_per_1k_input:   f64,   // USD
    pub cost_per_1k_output:  f64,   // USD
    /// Thai language capability score 1–10 (10 = best Thai support).
    /// Based on known benchmark data; updated when empirical results arrive.
    pub thai_score:          u8,
}

/// Thai routing priority — preferred model IDs for each complexity bucket.
/// Updated after running `openpair benchmark --lang th`.
pub const THAI_ROUTING_PRIORITY: ThaiRoutingPriority = ThaiRoutingPriority {
    simple_thai:  "gemini-3.1-flash-lite",  // cheap + acceptable Thai
    medium_thai:  "claude-haiku-4-5",       // balanced + good Thai
    complex_thai: "claude-sonnet-5",        // best Thai quality
};

pub struct ThaiRoutingPriority {
    pub simple_thai:  &'static str,
    pub medium_thai:  &'static str,
    pub complex_thai: &'static str,
}

pub struct ModelRegistry {
    models: Vec<ModelMeta>,
}

impl ModelRegistry {
    pub fn new() -> Self {
        ModelRegistry {
            models: vec![
                // Prices in USD per 1k tokens, current as of 2026-07-25 (per-1M ÷ 1000).
                // thai_score for the Groq models and gemini-3.1-flash-lite was measured
                // 2026-07-28 via run_benchmark.py (20 Thai test cases; see
                // benchmark_results_groq_2026.json / benchmark_results_gemini_2026.json).
                // 2026-10-01: re-checked on the 600-case --suite full (benchmark_results_groq_full.json /
                // benchmark_results_gemini_full.json): gpt-oss-120b 9, gemini-3.1-flash-lite 9 (unchanged),
                // gpt-oss-20b 8 -> 9 (547/600 cases, avg 8.71). gemini-3.6-flash was dropped from the full
                // suite (free quota too small) and keeps its 20-case score.
                // OpenAI and Anthropic are intentionally not benchmarked (decided 2026-10-02) —
                // their thai_score values are estimates.
                // gemini-3.1-pro-preview (id corrected from the non-existent "gemini-3.1-pro") has
                // zero free-tier quota, so it can't be benchmarked without paid billing — its
                // thai_score is still an estimate.

                // ── Small / Fast ──────────────────────────────────────────────────────────────────────
                //                                                                           thai_score ↓
                ModelMeta { id: "claude-haiku-4-5",           name: "Claude Haiku 4.5",  provider: "anthropic", tier: ModelTier::Small,  context_window: 1_000_000, cost_per_1k_input: 0.001,    cost_per_1k_output: 0.005,   thai_score: 7 },
                ModelMeta { id: "gpt-5.4-nano",               name: "GPT-5.4 Nano",      provider: "openai",    tier: ModelTier::Small,  context_window: 1_000_000, cost_per_1k_input: 0.0002,   cost_per_1k_output: 0.00125, thai_score: 6 },
                ModelMeta { id: "gemini-3.1-flash-lite",      name: "Gemini 3.1 Flash Lite", provider: "google", tier: ModelTier::Small,  context_window: 1_000_000, cost_per_1k_input: 0.00025,  cost_per_1k_output: 0.0015,  thai_score: 9 }, // measured

                // ── Mid / Balanced ────────────────────────────────────────────────────────────────────
                ModelMeta { id: "claude-sonnet-5",            name: "Claude Sonnet 5",   provider: "anthropic", tier: ModelTier::Mid,    context_window: 1_000_000, cost_per_1k_input: 0.003,    cost_per_1k_output: 0.01500, thai_score: 9 },
                ModelMeta { id: "gemini-3.6-flash",           name: "Gemini 3.6 Flash",  provider: "google",    tier: ModelTier::Mid,    context_window: 1_000_000, cost_per_1k_input: 0.0015,   cost_per_1k_output: 0.0075,  thai_score: 6 }, // measured

                // ── Top / Quality ─────────────────────────────────────────────────────────────────────
                ModelMeta { id: "gpt-5.5",                    name: "GPT-5.5",           provider: "openai",    tier: ModelTier::Top,    context_window: 1_000_000, cost_per_1k_input: 0.005,    cost_per_1k_output: 0.03000, thai_score: 8 },
                ModelMeta { id: "claude-opus-5",              name: "Claude Opus 5",     provider: "anthropic", tier: ModelTier::Top,    context_window: 1_000_000, cost_per_1k_input: 0.005,    cost_per_1k_output: 0.02500, thai_score: 9 },

                // ── Expert / Long-Context ─────────────────────────────────────────────────────────────
                ModelMeta { id: "gemini-3.1-pro-preview",     name: "Gemini 3.1 Pro",    provider: "google",    tier: ModelTier::Expert, context_window: 1_000_000, cost_per_1k_input: 0.002,    cost_per_1k_output: 0.01200, thai_score: 7 },

                // ── Groq (ultra-fast inference) ───────────────────────────────────────────────────────
                // 2026-08-28: llama-3.1-8b-instant / llama-3.3-70b-versatile decommissioned by Groq
                // (confirmed via GET /v1/models — both 404 now). No Mid-tier Groq model replaces
                // llama-3.3-70b-versatile at a comparable price today (qwen3.6/3.8-27b price above
                // gpt-oss-120b, groq/compound(-mini) pricing not published) — Mid tier drops its Groq
                // option until one appears; Small tier gets gpt-oss-20b (price confirmed via Groq docs,
                // thai_score measured 2026-10-01 on the 600-case full suite).
                ModelMeta { id: "openai/gpt-oss-20b",         name: "GPT-OSS 20B",       provider: "groq",      tier: ModelTier::Small,  context_window: 131_072,   cost_per_1k_input: 0.000075, cost_per_1k_output: 0.00030, thai_score: 9 }, // measured
                ModelMeta { id: "openai/gpt-oss-120b",        name: "GPT-OSS 120B",      provider: "groq",      tier: ModelTier::Top,    context_window: 131_072,   cost_per_1k_input: 0.00015,  cost_per_1k_output: 0.00060, thai_score: 9 }, // measured
            ],
        }
    }

    /// Pick the best model for a tier, preferring `preferred_provider` when possible.
    /// Falls back to cheapest in tier if provider not found.
    pub fn preferred_for_tier(
        &self,
        tier: &ModelTier,
        preferred_provider: Option<&str>,
    ) -> Option<&ModelMeta> {
        let candidates: Vec<&ModelMeta> = self.models
            .iter()
            .filter(|m| &m.tier == tier)
            .collect();

        if candidates.is_empty() {
            return None;
        }

        // Try preferred provider first
        if let Some(prov) = preferred_provider {
            if let Some(m) = candidates.iter().find(|m| m.provider == prov) {
                return Some(m);
            }
        }

        // Default: cheapest in tier
        candidates.into_iter()
            .min_by(|a, b| a.cost_per_1k_input.partial_cmp(&b.cost_per_1k_input).unwrap_or(std::cmp::Ordering::Equal))
    }

    pub fn get_by_id(&self, id: &str) -> Option<&ModelMeta> {
        self.models.iter().find(|m| m.id == id)
    }
}

// ─── Tests ─────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn registry_has_models_for_all_tiers() {
        let reg = ModelRegistry::new();
        for tier in &[ModelTier::Small, ModelTier::Mid, ModelTier::Top, ModelTier::Expert] {
            assert!(
                reg.preferred_for_tier(tier, None).is_some(),
                "No model found for tier {:?}", tier
            );
        }
    }

    #[test]
    fn preferred_provider_is_respected() {
        let reg = ModelRegistry::new();
        let m = reg.preferred_for_tier(&ModelTier::Small, Some("openai")).unwrap();
        assert_eq!(m.provider, "openai");
    }

    #[test]
    fn falls_back_when_provider_unavailable() {
        let reg = ModelRegistry::new();
        // "mistral" doesn't exist yet — should still return something
        let m = reg.preferred_for_tier(&ModelTier::Small, Some("mistral"));
        assert!(m.is_some(), "Should fall back to cheapest model");
    }

    #[test]
    fn tier_from_score_mapping() {
        assert_eq!(ModelTier::from_score(1), ModelTier::Small);
        assert_eq!(ModelTier::from_score(3), ModelTier::Small);
        assert_eq!(ModelTier::from_score(4), ModelTier::Mid);
        assert_eq!(ModelTier::from_score(6), ModelTier::Mid);
        assert_eq!(ModelTier::from_score(7), ModelTier::Top);
        assert_eq!(ModelTier::from_score(9), ModelTier::Top);
        assert_eq!(ModelTier::from_score(10), ModelTier::Expert);
    }
}
