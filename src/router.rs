/// Decision Engine — combines classifier + registry → RoutingDecision
///
/// This is the struct exposed to Python via PyO3.

use pyo3::prelude::*;
use crate::classifier::{score_complexity, is_thai};
use crate::registry::{ModelRegistry, ModelTier, THAI_ROUTING_PRIORITY};

#[pyclass]
#[derive(Debug, Clone)]
pub struct RoutingDecision {
    #[pyo3(get)]
    pub model_id:          String,
    #[pyo3(get)]
    pub model_name:        String,
    #[pyo3(get)]
    pub provider:          String,
    #[pyo3(get)]
    pub tier:              String,
    #[pyo3(get)]
    pub complexity_score:  u8,
    #[pyo3(get)]
    pub reason:            String,
    #[pyo3(get)]
    pub cost_per_1k_input: f64,
}

#[pymethods]
impl RoutingDecision {
    fn __repr__(&self) -> String {
        format!(
            "RoutingDecision(model='{}', tier='{}', score={}, cost=${:.5}/1K)",
            self.model_name, self.tier, self.complexity_score, self.cost_per_1k_input
        )
    }
}

/// Core routing function — pure Rust, called from Python via PyO3.
///
/// If the prompt is Thai and no `preferred_provider` is specified,
/// Thai Routing Priority overrides the normal cheapest-in-tier logic.
pub fn route_prompt(prompt: &str, preferred_provider: Option<&str>) -> RoutingDecision {
    let registry = ModelRegistry::new();
    let score = score_complexity(prompt);
    let tier = ModelTier::from_score(score);
    let thai = is_thai(prompt);

    // Thai routing override (only when caller did not pin a provider)
    let model = if thai && preferred_provider.is_none() {
        let preferred_id = match score {
            1..=3 => THAI_ROUTING_PRIORITY.simple_thai,
            4..=6 => THAI_ROUTING_PRIORITY.medium_thai,
            _     => THAI_ROUTING_PRIORITY.complex_thai,
        };
        registry.get_by_id(preferred_id)
            .or_else(|| registry.preferred_for_tier(&tier, None))
            .expect("Registry must have at least one model per tier")
    } else {
        registry
            .preferred_for_tier(&tier, preferred_provider)
            .expect("Registry must have at least one model per tier")
    };

    let reason = build_reason(score, &tier, model.name, preferred_provider, thai);

    RoutingDecision {
        model_id:          model.id.to_string(),
        model_name:        model.name.to_string(),
        provider:          model.provider.to_string(),
        tier:              tier.as_str().to_string(),
        complexity_score:  score,
        reason,
        cost_per_1k_input: model.cost_per_1k_input,
    }
}

fn build_reason(score: u8, tier: &ModelTier, model_name: &str, preferred: Option<&str>, thai: bool) -> String {
    let tier_desc = match tier {
        ModelTier::Small  => "Low complexity — using a fast, cost-efficient model",
        ModelTier::Mid    => "Medium complexity — using a balanced quality/cost model",
        ModelTier::Top    => "High complexity — using a top-tier reasoning model",
        ModelTier::Expert => "Critical complexity — using the best available model",
    };

    let provider_note = if let Some(p) = preferred {
        format!(" (preferred provider: {p})")
    } else if thai {
        " (Thai routing priority)".to_string()
    } else {
        " (cheapest in tier)".to_string()
    };

    let lang_tag = if thai { " [Thai]" } else { "" };

    format!(
        "{tier_desc}{lang_tag}. Score: {score}/10 → {model_name}{provider_note}."
    )
}

// ─── Tests ─────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn simple_prompt_routes_to_small_tier() {
        let d = route_prompt("Hello!", None);
        assert_eq!(d.tier, "small");
        assert!(d.complexity_score <= 3);
    }

    #[test]
    fn complex_prompt_routes_to_top_tier() {
        let d = route_prompt(
            "Design a comprehensive microservices architecture for an e-commerce platform. \
             Analyze trade-offs between synchronous and asynchronous communication patterns, \
             implement circuit breakers, and explain database sharding strategies.",
            None,
        );
        assert!(d.complexity_score >= 6);
    }

    #[test]
    fn preferred_provider_openai() {
        let d = route_prompt("What is the capital of France?", Some("openai"));
        assert_eq!(d.provider, "openai");
    }

    #[test]
    fn preferred_provider_anthropic() {
        let d = route_prompt("What is the capital of France?", Some("anthropic"));
        assert_eq!(d.provider, "anthropic");
    }

    #[test]
    fn preferred_provider_google() {
        let d = route_prompt("What is the capital of France?", Some("google"));
        assert_eq!(d.provider, "google");
    }

    #[test]
    fn decision_has_all_fields() {
        let d = route_prompt("Write a poem about the ocean.", None);
        assert!(!d.model_id.is_empty());
        assert!(!d.model_name.is_empty());
        assert!(!d.provider.is_empty());
        assert!(!d.tier.is_empty());
        assert!(!d.reason.is_empty());
        assert!(d.cost_per_1k_input > 0.0);
    }
}
