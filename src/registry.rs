
/// Model Registry — in-memory store of AI model metadata
///
/// Hard-coded defaults for the two providers usable on a free tier: Google (Gemini) and Groq.
/// OpenAI / Anthropic / OpenRouter models were removed 2026-10-02 (no keys / not benchmarked);
/// their caller code in python/openpair/caller.py is kept but nothing routes to it.
/// Future: hot-reload from YAML/JSON config
/// Prices per 1k tokens, current as of 2026-07-25.

#[derive(Debug, Clone, PartialEq)]
pub enum ModelTier {
    Small,  // Complexity 1–3 : fast, cheap (Gemini 3.1 Flash-Lite, GPT-OSS 20B)
    Mid,    // Complexity 4–6 : balanced  (Gemini 3.6 Flash)
    Top,    // Complexity 7–9 : quality   (GPT-OSS 120B)
    Expert, // Complexity 10  : no free model of its own — falls back to Top
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

    /// The next tier down, used when a tier has no models of its own.
    pub fn lower(&self) -> Option<Self> {
        match self {
            ModelTier::Small  => None,
            ModelTier::Mid    => Some(ModelTier::Small),
            ModelTier::Top    => Some(ModelTier::Mid),
            ModelTier::Expert => Some(ModelTier::Top),
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
    pub provider:            &'static str,  // "google" | "groq"
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
    // All buckets → flash-lite: on the 598-case full suite it beats both gpt-oss models at every
    // difficulty (9.40 vs 8.79 / 8.71, paired CIs exclude 0) and 120b ≈ 20b (paper/ANALYSIS.md, 2026-10-17).
    // If Gemini is rate-limited, client.call() falls back to Groq as usual.
    simple_thai:  "gemini-3.1-flash-lite",
    medium_thai:  "gemini-3.1-flash-lite",
    complex_thai: "gemini-3.1-flash-lite",
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
                // 2026-10-02: removed OpenAI/Anthropic models (not used) and gemini-3.1-pro-preview
                // (zero free-tier quota) — every model left has a measured thai_score.

                // ── Small / Fast ──────────────────────────────────────────────────────────────────────
                //                                                                           thai_score ↓
                ModelMeta { id: "gemini-3.1-flash-lite",      name: "Gemini 3.1 Flash Lite", provider: "google", tier: ModelTier::Small,  context_window: 1_000_000, cost_per_1k_input: 0.00025,  cost_per_1k_output: 0.0015,  thai_score: 9 }, // measured

                // ── Mid / Balanced ────────────────────────────────────────────────────────────────────
                ModelMeta { id: "gemini-3.6-flash",           name: "Gemini 3.6 Flash",  provider: "google",    tier: ModelTier::Mid,    context_window: 1_000_000, cost_per_1k_input: 0.0015,   cost_per_1k_output: 0.0075,  thai_score: 6 }, // measured

                // Top tier: openai/gpt-oss-120b (Groq, below). Expert has no model — see ModelTier::lower.

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
            return tier.lower().and_then(|t| self.preferred_for_tier(&t, preferred_provider));
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
        let m = reg.preferred_for_tier(&ModelTier::Small, Some("google")).unwrap();
        assert_eq!(m.provider, "google");
    }

    #[test]
    fn expert_falls_back_to_top_tier_model() {
        let reg = ModelRegistry::new();
        let m = reg.preferred_for_tier(&ModelTier::Expert, None).unwrap();
        assert_eq!(m.tier, ModelTier::Top);
    }

    #[test]
    fn only_free_tier_providers_remain() {
        let reg = ModelRegistry::new();
        for tier in &[ModelTier::Small, ModelTier::Mid, ModelTier::Top] {
            let m = reg.preferred_for_tier(tier, None).unwrap();
            assert!(m.provider == "google" || m.provider == "groq", "{} is {}", m.id, m.provider);
        }
    }

    #[test]
    fn thai_routing_priority_ids_exist() {
        let reg = ModelRegistry::new();
        for id in [THAI_ROUTING_PRIORITY.simple_thai, THAI_ROUTING_PRIORITY.medium_thai, THAI_ROUTING_PRIORITY.complex_thai] {
            assert!(reg.get_by_id(id).is_some(), "{id} missing from registry");
        }
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
