# Baseline: build and test status (November 2026)

Recorded for issue #4. This is the state of `master` (commit `605c0b7`) before any
Phase 0 follow-up work, built from a clean virtual environment on a local machine.

## Environment

| Item | Value |
| --- | --- |
| OS | Windows 11 Home (10.0.26200) |
| Python | 3.12.10 (inside `.venv`) |
| Rust / Cargo | rustc 1.100.0 (2026-11-09) / cargo 1.100.0 (2026-11-05) |
| maturin | 1.16.0 |
| pytest / pytest-asyncio | 9.2.0 / 1.5.0 |
| PyO3 | 0.22.6 (from `Cargo.lock`) |

Resolved runtime dependencies (unpinned floors in `pyproject.toml`, so these are
simply the latest versions at the time of the run):

| Package | Version |
| --- | --- |
| openai | 3.57.0 |
| anthropic | 2.12.0 |
| google-genai | 3.6.1 |
| python-dotenv | 1.2.4 |

## Commands (run from the repository root, PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version                  # Python 3.12.10
pip install maturin
maturin develop --release
pip install -e ".[dev]"
cargo test
pytest -m "not live"
```

## Results

| Step | Result |
| --- | --- |
| `maturin develop --release` | Success. Built a `cp312-cp312-win_amd64` wheel and installed it as editable (`openpair-0.1.0`). |
| `pip install -e ".[dev]"` | Success. |
| `cargo test` | **26 passed, 0 failed, 0 ignored** in each of two targets (see below), plus a doc-test target with 0 tests. |
| `pytest -m "not live"` | **126 passed, 0 failed, 3 deselected** (the 3 deselected tests are the `live` tests that need real API keys), in about 36 s. |

### `cargo test` targets

| Target | Tests run | Result |
| --- | --- | --- |
| unittests `src/lib.rs` (`_core`) | 26 | ok, 26 passed |
| unittests `src/main.rs` (`openpair_demo`) | 26 | ok, 26 passed |
| Doc-tests `_core` | 0 | ok |

Both `src/lib.rs` and `src/main.rs` declare `mod classifier; mod registry; mod router;`,
so the same 26 unit tests are compiled and run once per target. That is 26 distinct
tests, reported twice (52 test executions in total). The test names were not compared
one by one; the equal counts and identical `mod` declarations are the evidence.

## Notes

- `pytest` prints a `PytestDeprecationWarning` because
  `asyncio_default_fixture_loop_scope` is unset for pytest-asyncio. It does not
  affect results; it is a candidate for a later cleanup.
- Live API tests (`-m live`) were not run: no API keys were used for this baseline.
- `pip` printed a "new release of pip is available" notice. It is informational only.
