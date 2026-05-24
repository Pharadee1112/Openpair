/// OpenPair Core — PyO3 Module Entry Point
///
/// Exposes two functions to Python:
///   openpair_core.route(prompt, preferred_provider=None) → RoutingDecision
///   openpair_core.score_complexity(prompt) → int

use pyo3::prelude::*;

mod classifier;
mod registry;
mod router;

use router::{route_prompt, RoutingDecision};

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<RoutingDecision>()?;
    m.add_function(wrap_pyfunction!(py_route, m)?)?;
    m.add_function(wrap_pyfunction!(py_score_complexity, m)?)?;
    m.add_function(wrap_pyfunction!(py_is_thai, m)?)?;
    m.add_function(wrap_pyfunction!(py_thai_ratio, m)?)?;
    Ok(())
}

/// Route a prompt to the best AI model.
///
/// Args:
///     prompt (str): The user's prompt.
///     preferred_provider (str | None): "openai" | "anthropic" | "google"
///
/// Returns:
///     RoutingDecision: model_id, provider, tier, complexity_score, reason, cost_per_1k_input
#[pyfunction]
#[pyo3(name = "route", signature = (prompt, preferred_provider=None))]
fn py_route(prompt: &str, preferred_provider: Option<&str>) -> PyResult<RoutingDecision> {
    Ok(route_prompt(prompt, preferred_provider))
}

/// Score the complexity of a prompt (1–10).
///
/// Args:
///     prompt (str): The user's prompt.
///
/// Returns:
///     int: Complexity score 1 (simple) → 10 (expert-level)
#[pyfunction]
#[pyo3(name = "score_complexity")]
fn py_score_complexity(prompt: &str) -> PyResult<u8> {
    Ok(classifier::score_complexity(prompt))
}

/// Detect whether a prompt contains Thai characters.
///
/// Args:
///     text (str): Any text string.
///
/// Returns:
///     bool: True if the text contains Thai Unicode characters.
#[pyfunction]
#[pyo3(name = "is_thai")]
fn py_is_thai(text: &str) -> PyResult<bool> {
    Ok(classifier::is_thai(text))
}

/// Return the fraction of characters that are Thai (0.0–1.0).
///
/// Args:
///     text (str): Any text string.
///
/// Returns:
///     float: Ratio of Thai characters in [0.0, 1.0].
#[pyfunction]
#[pyo3(name = "thai_ratio")]
fn py_thai_ratio(text: &str) -> PyResult<f64> {
    Ok(classifier::thai_ratio(text))
}
