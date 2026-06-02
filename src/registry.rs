
/// Model Registry — in-memory store of AI model metadata
///
/// For MVP: hard-coded defaults across 3 providers (OpenAI, Anthropic, Google)
/// Future: hot-reload from YAML/JSON config

#[derive(Debug, Clone, PartialEq)]
pub enum ModelTier {
    Small,  // Complexity 1–3 : fast, cheap (Haiku, Flash, GPT-4o-mini)
    Mid,    // Complexity 4–6 : balanced  (Gemini 1.5 Pro, Claude 3.5 Sonnet)
    Top,    // Complexity 7–9 : quality   (GPT-4o, Claude 3.5 Sonnet)
    Expert, // Complexity 10  : best + long-context
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
    simple_thai:  "gemini-2.5-flash-lite",        // cheap + acceptable Thai
    medium_thai:  "claude-3-haiku-20240307",    // balanced + good Thai
    complex_thai: "claude-3-5-sonnet-20241022", // best Thai quality
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
                // ── Small / Fast ──────────────────────────────────────────────────────────────────────
                //                                                                           thai_score ↓
                ModelMeta { id: "claude-3-haiku-20240307",    name: "Claude 3 Haiku",    provider: "anthropic", tier: ModelTier::Small,  context_window: 200_000,   cost_per_1k_input: 0.00025,  cost_per_1k_output: 0.00125, thai_score: 7 },
                ModelMeta { id: "gpt-4o-mini",                name: "GPT-4o Mini",       provider: "openai",    tier: ModelTier::Small,  context_window: 128_000,   cost_per_1k_input: 0.00015,  cost_per_1k_output: 0.00060, thai_score: 6 },
                ModelMeta { id: "gemini-2.5-flash-lite",      name: "Gemini 2.5 Flash Lite", provider: "google", tier: ModelTier::Small,  context_window: 1_000_000, cost_per_1k_input: 0.000075, cost_per_1k_output: 0.00030, thai_score: 9 },

                // ── Mid / Balanced ────────────────────────────────────────────────────────────────────
                ModelMeta { id: "claude-3-5-sonnet-20241022", name: "Claude 3.5 Sonnet", provider: "anthropic", tier: ModelTier::Mid,    context_window: 200_000,   cost_per_1k_input: 0.003,    cost_per_1k_output: 0.01500, thai_score: 9 },
                ModelMeta { id: "gemini-2.5-flash",           name: "Gemini 2.5 Flash",  provider: "google",    tier: ModelTier::Mid,    context_window: 1_000_000, cost_per_1k_input: 0.00125,  cost_per_1k_output: 0.00500, thai_score: 4 },

                // ── Top / Quality ─────────────────────────────────────────────────────────────────────
                ModelMeta { id: "gpt-4o",                     name: "GPT-4o",            provider: "openai",    tier: ModelTier::Top,    context_window: 128_000,   cost_per_1k_input: 0.005,    cost_per_1k_output: 0.01500, thai_score: 8 },
                ModelMeta { id: "claude-3-5-sonnet-top",      name: "Claude 3.5 Sonnet", provider: "anthropic", tier: ModelTier::Top,    context_window: 200_000,   cost_per_1k_input: 0.003,    cost_per_1k_output: 0.01500, thai_score: 9 },

                // ── Expert / Long-Context ─────────────────────────────────────────────────────────────
                ModelMeta { id: "gemini-2.5-pro",             name: "Gemini 2.5 Pro",    provider: "google",    tier: ModelTier::Expert, context_window: 1_000_000, cost_per_1k_input: 0.00125,  cost_per_1k_output: 0.00500, thai_score: 7 },

                // ── Groq (ultra-fast inference) ───────────────────────────────────────────────────────
                ModelMeta { id: "llama-3.1-8b-instant",       name: "Llama 3.1 8B",      provider: "groq",      tier: ModelTier::Small,  context_window: 128_000,   cost_per_1k_input: 0.00005,  cost_per_1k_output: 0.00008, thai_score: 5 },
                ModelMeta { id: "llama-3.3-70b-versatile",    name: "Llama 3.3 70B",     provider: "groq",      tier: ModelTier::Mid,    context_window: 128_000,   cost_per_1k_input: 0.00059,  cost_per_1k_output: 0.00079, thai_score: 6 },
                ModelMeta { id: "moonshotai/kimi-k2-instruct", name: "Kimi K2",           provider: "groq",      tier: ModelTier::Top,    context_window: 131_072,   cost_per_1k_input: 0.00100,  cost_per_1k_output: 0.00300, thai_score: 6 },
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

    pub fn all(&self) -> &[ModelMeta] {
        &self.models
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
