/// OpenPair Demo Binary
/// Run: cargo run --bin openpair-demo -- "your prompt here"

mod classifier;
mod registry;
mod router;

use router::route_prompt;
use std::env;

fn main() {
    let args: Vec<String> = env::args().collect();
    let prompt = if args.len() > 1 {
        args[1..].join(" ")
    } else {
        "Hello, can you help me?".to_string()
    };

    println!("──────────────────────────────────────────");
    println!("  OpenPair Routing Engine (Rust Demo)");
    println!("──────────────────────────────────────────");
    println!("  Prompt : {}", &prompt[..prompt.len().min(80)]);

    let decision = route_prompt(&prompt, None);

    println!("  Score  : {}/10", decision.complexity_score);
    println!("  Tier   : {}", decision.tier);
    println!("  Model  : {} ({})", decision.model_name, decision.provider);
    println!("  Cost   : ${:.5}/1K input tokens", decision.cost_per_1k_input);
    println!("  Reason : {}", decision.reason);
    println!("──────────────────────────────────────────");
}
