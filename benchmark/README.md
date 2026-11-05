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

**Gap = candidate / reference.** Measuring both in the same process reduces some
environmental variation, but does not eliminate it. Ratios describe relative
overhead; CodSpeed gates the absolute performance of Arcanus workloads.

Coverage spans validation, construction, serialization (dict + JSON), every
relationship *shape* (scalar / collection / map / group-map / typed-map /
polymorphic), DB CRUD, relationship loading strategies (selectin / subquery /
joined, plus M-M and 1-M), bulk writes, bulk relationship mutations, association
proxies, and an async mini-suite.

## Run it locally (macOS-friendly, wall-clock)

CodSpeed's CPU simulation mode needs Valgrind, so locally use the wall-clock
reporter:

```bash
uv run python scripts/benchmark.py report           # the gap report, both axes
uv run python scripts/benchmark.py report --axis a   # one axis
uv run python scripts/benchmark.py report -k nested  # filter by test name
uv run python scripts/benchmark.py --help            # full command/option help
```

`scripts/benchmark.py` is a Typer CLI (`report`, `compare`, `profile`); every command
and flag has `--help`. pytest's own output is hidden — runs are saved under
`./.bench/` (`last.json`, plus `main.json` when you `--save main`). Raw
pytest-benchmark also works: `uv run pytest benchmark/ --benchmark-enable`.

## Reading the gap report

Columns: group, reference µs, candidate µs (plus context µs for Axis B), **Δ µs**
(candidate − reference, the absolute cost arcanus adds), and the **gap** (the
ratio). `1.00×` is parity; `2.00×` means arcanus is twice as slow as the
reference. Rows are sorted worst-gap first, with a per-axis median/max gap plus
a **max Δ** — the worst *absolute* overhead, which is a different group than the
worst gap whenever the reference is tiny. That gap/Δ split is the point: a
near-zero-reference group (e.g. `noop-mutation-groupmap`) shows a huge ratio but
a trivial Δ, while a DB-path group shows a small ratio but a large Δ. The gap is
colored green (≤1.5×) / yellow (≤3×) / red (>3×) as a soft cue; Δ µs is left
uncolored on purpose (an absolute-µs threshold would itself be misleading across
the two axes' scales). The report only measures — neither column is a pass/fail.

## Compare relative overhead

Compare this branch against a saved baseline to see how the gap changes. This
report is informational: if Pydantic gets faster, the ratio can widen even when
Arcanus also gets faster. A slower reference can make the ratio narrow without
improving Arcanus performance.

```bash
# snapshot a baseline (e.g. while on main) → ./.bench/main.json
uv run python scripts/benchmark.py report --save main
# on your branch — see the drift:
uv run python scripts/benchmark.py compare            # vs ./.bench/main.json
```

`--base NAME` picks a different baseline (name under `./.bench`, or a JSON path);
`--use NAME` compares a saved run as "now" instead of measuring live.
`--max-regression 0.10` highlights ratio increases above 10%; it does not fail the
command. A group with no baseline is shown as `new`. The former `--gate` option
has been removed. Missing input files and failed benchmark execution still fail
the command. Use repeated measurements when interpreting noisy DB-bound groups.

## Drilling into a regression

```bash
uv run python scripts/benchmark.py profile transmuter_validate_scalar --top 30
```

`TARGET` is a pytest `-k` pattern matching the **test function name**, not the
benchmark `group=` label — e.g. the group `noop-mutation-collection` is profiled
with `profile mutate_collection` (or `transmuter_mutate_collection` for just the
candidate). This runs the matching benchmarks under cProfile (via
pytest-benchmark) and prints the top cumulative frames so you can see *where* the
gap comes from. (List names with `pytest benchmark/ --collect-only -q`.)

## CodSpeed merge policy

The merge gate evaluates changes in the absolute performance of `test_transmuter_*`
and `test_arcanus_*` against main. Pure Pydantic, Pydantic+SQLAlchemy and pure ORM
cases remain visible as reference measurements, but do not decide whether to merge.

The workflow selects candidates with `-m "not baseline"` for CodSpeed. Cases
decorated with `@pytest.mark.baseline` (`test_pydantic_*` and `test_sqlalchemy_*`)
run separately with pytest-benchmark and are saved in the downloadable
`benchmark-references` JSON artifact. It contains wall-clock measurements, retained
for 30 days. It does not contain CodSpeed profiles and must not be compared
numerically with simulated candidate timings. Use the local gap report
to measure candidates and references together with the same instrument.

This selection lives in version control and applies to new baseline-marked cases
without per-benchmark dashboard changes. Reference test failures still fail CI;
reference timing changes do not.

- Keep candidate cases active and the performance check blocking. Review a real
  regression individually. For an accepted dependency tradeoff, record the
  affected operation and measured Arcanus impact, then use **Acknowledge regression**
  on that result. Do not raise the global threshold to accept one known change.
- Keep thresholds unchanged until repeated runs of an unchanged commit establish
  the variability of each workload. Configure per-benchmark thresholds from those
  measurements, retaining stricter limits for stable CPU workloads.

See CodSpeed's [acknowledgement workflow](https://codspeed.io/docs/features/performance-checks),
and [threshold configuration](https://codspeed.io/docs/features/customization).

## CI environments and instruments

CI currently uses CPU simulation on `ubuntu-24.04` for Arcanus candidates in both
directories. Database simulation results do not establish end-to-end I/O latency;
walltime on a stable dedicated runner is needed to include system calls and async
scheduling reliably. The current personal CodSpeed account cannot use Macro
Runners: its billing settings limit that feature to organization accounts.

Before migrating `benchmark/sqlalchemy/` to walltime, provision an eligible stable
runner and verify its allowance and spending controls. CodSpeed documents 600 free
Macro Runner minutes per month, with additional usage billed unless covered by an
open-source sponsorship. Keep that suite serial; do not enable pytest-xdist.
See [Macro Runners](https://codspeed.io/docs/features/macro-runners).

The job pins Python 3.12.15, uv 0.13.7, CodSpeed runner 4.19.1 and action commit
SHAs. `uv sync --frozen` installs the committed dependency set, and `uv run --no-sync`
prevents resolution during measurement. The cache key includes `uv.lock`, and
`PYTHONHASHSEED=0` keeps hash randomization consistent. Update these pins deliberately
and compare base/head on matching environments when investigating regressions.
An Ubuntu release label does not pin the GitHub runner image or physical CPU.

Switching the SQLAlchemy suite from CPU simulation to dedicated walltime creates a
new baseline; its numbers are not comparable to the old simulated timings. Record
a successful main-branch run on the same macro runner before enforcing walltime
regressions. Review dropped results caused by the instrument migration and by
moving reference measurements out of CodSpeed.
