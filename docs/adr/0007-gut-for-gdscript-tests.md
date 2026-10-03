# ADR-0007: GUT for GDScript tests

- Status: accepted
- Date: 2026-10-03

## Decision
Use **GUT 9.7** (pure GDScript addon) for unit and integration tests. It runs headless via
`tools/run_godot_tests.sh`. Unit tests live next to their module in a `tests/` folder.

## Alternatives
gdUnit4 (more features, C#-oriented tooling, heavier). GUT's simple headless CLI and JUnit output are enough.
