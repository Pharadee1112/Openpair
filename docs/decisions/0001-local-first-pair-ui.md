# 0001: Local-first, CLI-launched browser UI (Pair)

Status: Accepted
Date: 2026-11-22
Related: issue #7, README sections 1 and 6

## Context

OpenPair today is a one-shot CLI and Python API: it scores a prompt, routes it to a cloud model
(Gemini or Groq), and uses Ollama only as a last-resort fallback. We want a tool developers can work inside,
using models they already run on their own machines.

## Decision

1. Local-first. In the new UI, local models (Ollama, LM Studio, or a configurable OpenAI-compatible local endpoint)
   are the default. The UI runs in LOCAL_ONLY mode unless the developer explicitly opts into a remote endpoint.
2. The UI never silently sends a request to a cloud provider. If a local model fails, it shows an error or asks
   for explicit permission.
3. The UI is a local web page launched from the terminal (planned command: `openpair ui`), served on 127.0.0.1.
   It is not a native terminal drawing engine.
4. Pair is an interface companion (an original pixel-art avatar). It shows real system state and is not another
   model or an autonomous agent. No file edits or command execution in the initial scope.
5. Build on what exists: keep the Rust routing core, the Python client and the one-shot `openpair "prompt"`
   behaviour and API. Do not rewrite.
6. Priority: this is the main direction for now. The Thai benchmark and paper continue at lower priority, and
   their artifacts (benchmark results, paper/, hf_dataset/) are kept, not deleted.

## Consequences

- Order of work: issue #1 (`openpair chat`) comes first. Its session layer (multi-turn history, streaming) is
  designed so the Pair UI can reuse it. The one-line installer (#9) comes later.
- Needs a local-only execution policy and a local model adapter before the UI is connected to real prompts.
  The current `OpenPair.call()` tries cloud models first and must not be exposed unchanged behind a "local only" label.
- Existing risks to resolve on the way: the OLLAMA_BASE_URL inconsistency, `.env` being loaded from the current
  directory, and error messages for a missing model or an unreachable Ollama server.

## Not decided yet

- License for hf_dataset/ and paper/ (MIT currently covers the whole repository by default).
- Whether a v0.1.0 tag and GitHub Release are created, and whether to publish to PyPI.
- Python 3.14 support (needs a newer PyO3).
