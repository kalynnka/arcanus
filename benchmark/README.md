# arcanus benchmarks

This suite is an instrument for the two performance gaps the project tracks over
time — not a pass/fail test suite. Every comparison is a `@pytest.mark.benchmark`
**group** holding a reference and a candidate so a *gap* (ratio) can be computed.

## The two axes

- **Axis A — schema overhead** (`benchmark/noop/`): pure Pydantic
  (`test_pydantic_*`, the reference) vs a Transmuter under **NoOpMateria**
  (`test_transmuter_*`, the candidate). No backend is active, so this isolates
  exactly what the transmuter machinery adds over raw Pydantic. Group names are
  prefixed `noop-`.
- **Axis B — full ORM path** (`benchmark/sqlalchemy/`): the hand-written
  "validate with Pydantic, then build/realize ORM objects" pattern
  (`test_pydantic_sqlalchemy_*`, the reference) vs arcanus `SqlalchemyMateria`
  (`test_arcanus_*`, the candidate). Pure ORM (`test_sqlalchemy_*`) is shown for
  **context** only (the unavoidable-ORM floor) and is never gated.

**Gap = candidate / reference.** Because both run in the same process on the same
machine, the ratio cancels machine noise — which makes it a stable signal both on
the CodeSpeed dashboard and as a CI gate.

Coverage spans validation, construction, serialization (dict + JSON), every
relationship *shape* (scalar / collection / map / group-map / typed-map /
polymorphic), DB CRUD, relationship loading strategies (selectin / subquery /
joined, plus M-M and 1-M), bulk writes, bulk relationship mutations, association
proxies, and an async mini-suite.

## Run it locally (macOS-friendly, wall-clock)

CodeSpeed's instrumentation mode needs valgrind (Linux/CI only), so locally use
the wall-clock reporter:

```bash
uv run python scripts/bench.py report          # the gap report, both axes
uv run python scripts/bench.py report --axis a  # one axis
uv run python scripts/bench.py report -k nested # filter by test name
```

Raw pytest-benchmark also works: `uv run pytest benchmark/ --benchmark-enable`.

## Reading the gap report

Columns: group, reference µs, candidate µs (plus context µs for Axis B), and the
**gap** (the ratio). `1.00×` is parity; `2.00×` means arcanus is twice as slow as
the reference. Rows are sorted worst-gap first, with a per-axis median and max.
The gap is colored green (≤1.5×) / yellow (≤3×) / red (>3×) as a soft cue — it is
**not** a pass/fail; the report only measures.

## The gate: gap drift vs main (10%)

There are no absolute ceilings. The gate compares this branch against a
main-branch run and fails only when a group's gap regresses by more than 10%
(measured ratios cancel machine noise, so this is robust on CI runners):

```bash
# on main:
uv run pytest benchmark/ --benchmark-enable --benchmark-json=/tmp/main.json
# on your branch — see the drift, then enforce it:
uv run python scripts/bench.py compare /tmp/main.json --json /tmp/current.json
uv run python scripts/bench.py compare /tmp/main.json --json /tmp/current.json --gate
```

`--gate` exits non-zero on regression; `--max-regression 0.10` is the default
10% allowance. A group with no main baseline (e.g. a brand-new group) is shown as
`new` and never fails the gate.

## Drilling into a regression

```bash
uv run python scripts/bench.py profile transmuter_validate_scalar --top 30
```

`TARGET` is a pytest `-k` pattern matching the **test function name**, not the
benchmark `group=` label — e.g. the group `noop-mutation-collection` is profiled
with `profile mutate_collection` (or `transmuter_mutate_collection` for just the
candidate). This runs the matching benchmarks under cProfile (via
pytest-benchmark) and prints the top cumulative frames so you can see *where* the
gap comes from. (List names with `pytest benchmark/ --collect-only -q`.)

## How CodeSpeed fits

CI keeps a CodeSpeed instrumentation job for deterministic per-commit absolute
history of every benchmark (references included, since `uv.lock` pins the deps).
The separate `gap_gate` job runs the wall-clock comparison and fails a PR when a
group's gap regresses more than 10% vs main. The two are complementary: CodeSpeed
answers "what changed and by how much, precisely, over time"; the gap gate answers
"did this PR make the relative overhead meaningfully worse than main".
