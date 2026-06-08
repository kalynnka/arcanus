#!/usr/bin/env python
"""arcanus benchmark gap tool.

Measures the GAP (candidate / reference) for the two axes the project tracks and
reports it as rich tables. The ratio is taken within a single run so it cancels
machine noise — a robust "did we slow down too much" signal.

  Axis A  pure Pydantic (test_pydantic_*)            vs Transmuter@NoOp (test_transmuter_*)
  Axis B  Pydantic+SQLAlchemy (test_pydantic_sqlalchemy_*) vs materia (test_arcanus_*)
          (pure ORM test_sqlalchemy_* is shown as context)

Saved runs live under ./.bench (e.g. ./.bench/main.json, ./.bench/last.json).

Typical use:
  uv run python scripts/bench.py report                 # see the gaps now
  uv run python scripts/bench.py report --save main      # snapshot a baseline
  uv run python scripts/bench.py compare                 # drift vs ./.bench/main.json
  uv run python scripts/bench.py compare --gate          # …and fail on >10% regression
  uv run python scripts/bench.py profile mutate_collection   # drill into one gap
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import statistics
import subprocess
import sys
from enum import Enum
from typing import Optional

import typer
from rich.box import SIMPLE_HEAVY
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from typing_extensions import Annotated

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
BENCHMARK_DIR = REPO_ROOT / "benchmark"
BENCH_DIR = REPO_ROOT / ".bench"

# Most-specific prefix FIRST: test_pydantic_sqlalchemy_ must beat test_pydantic_.
REFERENCE_PREFIXES = ("test_pydantic_sqlalchemy_", "test_pydantic_")
CANDIDATE_PREFIXES = ("test_arcanus_", "test_transmuter_")
CONTEXT_PREFIXES = ("test_sqlalchemy_",)

AXIS_TITLES = {
    "A": "Axis A — pure Pydantic (ref) vs Transmuter@NoOp (cand)",
    "B": "Axis B — Pydantic+SQLAlchemy (ref) vs arcanus materia (cand)",
}

console = Console()
app = typer.Typer(
    help=__doc__,
    add_completion=False,
    rich_markup_mode="rich",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)


class Axis(str, Enum):
    a = "a"
    b = "b"
    both = "both"


@dataclasses.dataclass
class Record:
    axis: str  # "A" | "B"
    group: str
    size: str  # parametrize id like "n=10", or "" when unparametrized
    role: str  # "reference" | "candidate" | "context"
    seconds: float  # the min time — a stable noise floor


@dataclasses.dataclass
class GapRow:
    axis: str
    group: str
    size: str
    reference: float
    candidate: float
    context: float | None

    @property
    def key(self) -> str:
        return f"{self.group}[{self.size}]" if self.size else self.group

    @property
    def ratio(self) -> float:
        return self.candidate / self.reference if self.reference else float("nan")


# ── parsing & gap math ────────────────────────────────────────────────────────


def classify_role(name: str) -> str | None:
    base = name.split("[", 1)[0]
    for prefix in REFERENCE_PREFIXES:
        if base.startswith(prefix):
            return "reference"
    for prefix in CANDIDATE_PREFIXES:
        if base.startswith(prefix):
            return "candidate"
    for prefix in CONTEXT_PREFIXES:
        if base.startswith(prefix):
            return "context"
    return None


def size_label(params: dict | None) -> str:
    if not params:
        return ""
    return ",".join(f"{k}={v}" for k, v in sorted(params.items()))


def build_records(payload: dict) -> list[Record]:
    records: list[Record] = []
    for entry in payload.get("benchmarks", []):
        role = classify_role(entry["name"])
        if role is None:
            continue
        group = entry.get("group") or entry["name"]
        records.append(
            Record(
                axis="A" if group.startswith("noop-") else "B",
                group=group,
                size=size_label(entry.get("params")),
                role=role,
                seconds=entry["stats"]["min"],
            )
        )
    return records


def _best(records: list[Record], role: str) -> float | None:
    times = [r.seconds for r in records if r.role == role]
    return min(times) if times else None


def compute_gaps(payload: dict) -> list[GapRow]:
    buckets: dict[tuple[str, str, str], list[Record]] = {}
    for record in build_records(payload):
        buckets.setdefault((record.axis, record.group, record.size), []).append(record)
    rows: list[GapRow] = []
    for (axis, group, size), bucket in buckets.items():
        reference = _best(bucket, "reference")
        candidate = _best(bucket, "candidate")
        if reference is None or candidate is None:
            continue
        rows.append(
            GapRow(axis, group, size, reference, candidate, _best(bucket, "context"))
        )
    rows.sort(key=lambda r: r.ratio, reverse=True)
    return rows


# ── running pytest (output hidden behind a progress bar) ──────────────────────

# pytest -v ends each test's line with one of these outcomes.
_OUTCOMES = (" PASSED", " FAILED", " ERROR", " SKIPPED", " XFAIL", " XPASS")


def _count_benchmarks(k: Optional[str]) -> int:
    """Quick collect-only pass to size the progress bar."""
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(BENCHMARK_DIR),
        "--collect-only",
        "-q",
        "-p",
        "no:cacheprovider",
    ]
    if k:
        cmd += ["-k", k]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    return sum(1 for line in proc.stdout.splitlines() if "::" in line)


def _measure(
    k: Optional[str],
    rounds: Optional[int],
    warmup: int,
    max_time: Optional[float],
    out_path: pathlib.Path,
) -> dict:
    """Run the benchmark suite, writing JSON to out_path.

    pytest output is hidden — its ``-v`` stream is parsed only to drive a progress
    bar (one tick per completed benchmark). On failure the full log is dumped to
    ./.bench/pytest.log and we exit.
    """
    BENCH_DIR.mkdir(exist_ok=True)
    total = _count_benchmarks(k)
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(BENCHMARK_DIR),
        "-v",
        "--benchmark-enable",
        f"--benchmark-warmup-iterations={warmup}",
        f"--benchmark-json={out_path}",
        "-p",
        "no:cacheprovider",
    ]
    if rounds:
        cmd.append(f"--benchmark-min-rounds={rounds}")
    if max_time:
        cmd.append(f"--benchmark-max-time={max_time}")
    if k:
        cmd += ["-k", k]

    captured: list[str] = []
    columns = (
        TextColumn("[bold cyan]benchmarking[/bold cyan]"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
    )
    proc = subprocess.Popen(
        cmd,
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    with Progress(
        *columns, console=console, transient=True, disable=not console.is_terminal
    ) as progress:
        task = progress.add_task("bench", total=total or None)
        assert proc.stdout is not None
        for line in proc.stdout:
            captured.append(line)
            if "::" in line and any(token in line for token in _OUTCOMES):
                progress.advance(task)
    proc.wait()
    if proc.returncode != 0:
        log = BENCH_DIR / "pytest.log"
        log.write_text("".join(captured))
        console.print(
            f"[bold red]benchmark run failed[/bold red] (pytest exit {proc.returncode}). "
            f"Full output: [underline]{log}[/underline]"
        )
        raise typer.Exit(1)
    return json.loads(out_path.read_text())


def _load_saved(name: str) -> dict:
    path = name if name.endswith(".json") else f"{name}.json"
    candidate = pathlib.Path(path)
    if not candidate.is_absolute():
        candidate = BENCH_DIR / path
    if not candidate.exists():
        console.print(
            f"[yellow]no saved run at {candidate}[/yellow] — create one with: "
            f"[bold]bench report --save {name}[/bold]"
        )
        raise typer.Exit(2)
    return json.loads(candidate.read_text())


# ── rendering ─────────────────────────────────────────────────────────────────


def _us(seconds: float) -> str:
    return f"{seconds * 1e6:,.1f}"


def _ratio_markup(ratio: float) -> str:
    color = "green" if ratio <= 1.5 else "yellow" if ratio <= 3.0 else "red"
    return f"[{color}]{ratio:.2f}×[/{color}]"


def _render_report(rows: list[GapRow], axis: str) -> None:
    for ax in ("A", "B"):
        if axis not in ("both", ax.lower()):
            continue
        ax_rows = [r for r in rows if r.axis == ax]
        if not ax_rows:
            continue
        table = Table(title=AXIS_TITLES[ax], box=SIMPLE_HEAVY, header_style="bold")
        table.add_column("group", style="cyan", no_wrap=True)
        table.add_column("ref µs", justify="right")
        table.add_column("cand µs", justify="right")
        if ax == "B":
            table.add_column("ctx µs", justify="right", style="dim")
        table.add_column("gap", justify="right")
        for row in ax_rows:
            cells = [row.key, _us(row.reference), _us(row.candidate)]
            if ax == "B":
                cells.append(_us(row.context) if row.context is not None else "—")
            cells.append(_ratio_markup(row.ratio))
            table.add_row(*cells)
        console.print(table)
        ratios = [r.ratio for r in ax_rows]
        worst = max(ax_rows, key=lambda r: r.ratio)
        console.print(
            f"  [bold]median gap[/bold] {statistics.median(ratios):.2f}×   "
            f"[bold]max gap[/bold] {worst.ratio:.2f}× ({worst.key})\n"
        )


def _render_compare(
    rows: list[GapRow],
    baseline_rows: list[GapRow],
    axis: str,
    max_regression: float,
    gate: bool,
) -> int:
    baseline = {(r.axis, r.key): r.ratio for r in baseline_rows}
    regressions: list[str] = []
    for ax in ("A", "B"):
        if axis not in ("both", ax.lower()):
            continue
        ax_rows = [r for r in rows if r.axis == ax]
        if not ax_rows:
            continue
        table = Table(
            title=f"{AXIS_TITLES[ax]}  —  gap drift vs baseline",
            box=SIMPLE_HEAVY,
            header_style="bold",
        )
        table.add_column("group", style="cyan", no_wrap=True)
        table.add_column("base", justify="right")
        table.add_column("now", justify="right")
        table.add_column("Δ", justify="right")
        table.add_column("status")
        for row in ax_rows:
            before = baseline.get((row.axis, row.key))
            if before is None:
                table.add_row(
                    row.key, "—", f"{row.ratio:.2f}×", "—", "[blue]new[/blue]"
                )
                continue
            drift = row.ratio / before - 1 if before else 0.0
            if drift > max_regression:
                status = "[red]REGRESSED[/red]"
                regressions.append(f"{row.axis}/{row.key}: +{drift * 100:.1f}%")
            elif drift < -0.02:
                status = "[green]improved[/green]"
            else:
                status = "[dim]ok[/dim]"
            table.add_row(
                row.key,
                f"{before:.2f}×",
                f"{row.ratio:.2f}×",
                f"{drift * 100:+.1f}%",
                status,
            )
        console.print(table)

    if not baseline:
        console.print(
            "[yellow]baseline has no comparable groups — gate skipped.[/yellow]"
        )
        return 0
    if gate and regressions:
        console.print(
            f"[bold red]GATE FAIL[/bold red] — {len(regressions)} group(s) over "
            f"{max_regression * 100:.0f}%:"
        )
        for line in regressions:
            console.print(f"  [red]{line}[/red]")
        return 1
    if gate:
        console.print(
            f"[bold green]GATE PASS[/bold green] — nothing over {max_regression * 100:.0f}%."
        )
    return 0


# ── shared option annotations ─────────────────────────────────────────────────

AxisOpt = Annotated[Axis, typer.Option(help="Which axis to show (A=schema, B=ORM).")]
FilterOpt = Annotated[
    Optional[str],
    typer.Option(
        "--filter", "-k", help="pytest -k pattern to restrict which groups run."
    ),
]
RoundsOpt = Annotated[
    Optional[int],
    typer.Option(
        help="Min rounds per benchmark. Raise (e.g. 8) to steady the noisy DB groups."
    ),
]
WarmupOpt = Annotated[
    int, typer.Option(help="Warmup iterations discarded before timing.")
]
MaxTimeOpt = Annotated[
    Optional[float],
    typer.Option(
        "--max-time", help="Cap wall-time (s) per benchmark to bound total runtime."
    ),
]


# ── commands ──────────────────────────────────────────────────────────────────


@app.command()
def report(
    axis: AxisOpt = Axis.both,
    k: FilterOpt = None,
    save: Annotated[
        Optional[str],
        typer.Option(
            help="Persist this run as ./.bench/<name>.json (use 'main' to snapshot a baseline)."
        ),
    ] = None,
    rounds: RoundsOpt = None,
    warmup: WarmupOpt = 5,
    max_time: MaxTimeOpt = None,
):
    """Run the suite and print the gap (candidate/reference) per group, worst first.

    Always saved to ./.bench/last.json; pass --save main to also keep it as the
    comparison baseline.
    """
    out = BENCH_DIR / (f"{save}.json" if save else "last.json")
    payload = _measure(k, rounds, warmup, max_time, out)
    if save:
        console.print(f"[dim]saved baseline → {out}[/dim]")
    _render_report(compute_gaps(payload), axis.value)


@app.command()
def compare(
    base: Annotated[
        str,
        typer.Option(
            "--base",
            "-b",
            help="Baseline run name under ./.bench (or a path to a JSON).",
        ),
    ] = "main",
    gate: Annotated[
        bool,
        typer.Option(
            help="Exit non-zero if any group's gap regresses beyond --max-regression."
        ),
    ] = False,
    max_regression: Annotated[
        float, typer.Option(help="Allowed gap drift before --gate fails (0.10 = 10%).")
    ] = 0.10,
    use: Annotated[
        Optional[str],
        typer.Option(
            help="Compare a SAVED run as 'now' instead of measuring live (name or path)."
        ),
    ] = None,
    axis: AxisOpt = Axis.both,
    k: FilterOpt = None,
    rounds: RoundsOpt = None,
    warmup: WarmupOpt = 5,
    max_time: MaxTimeOpt = None,
):
    """Compare the current run's gaps against a saved baseline (default ./.bench/main.json).

    Measures the current branch live unless --use names a saved run. With --gate
    it becomes a regression check: a group only fails when its gap got more than
    --max-regression worse than the baseline. New groups (no baseline) never fail.
    """
    baseline_rows = compute_gaps(_load_saved(base))
    current = (
        _load_saved(use)
        if use
        else _measure(k, rounds, warmup, max_time, BENCH_DIR / "last.json")
    )
    code = _render_compare(
        compute_gaps(current), baseline_rows, axis.value, max_regression, gate
    )
    raise typer.Exit(code)


@app.command()
def profile(
    target: Annotated[
        str,
        typer.Argument(
            help="pytest -k pattern matching the TEST NAME (not the group label), "
            "e.g. 'mutate_collection' or 'transmuter_validate_scalar'."
        ),
    ],
    top: Annotated[
        int, typer.Option(help="Number of cumulative-time frames to show.")
    ] = 30,
):
    """cProfile the benchmarks matching TARGET and print the hottest frames.

    Use this to see *where* a gap comes from. TARGET is a test-name pattern: the
    group 'noop-mutation-collection' is profiled with 'mutate_collection'. (List
    names with: pytest benchmark/ --collect-only -q.)
    """
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(BENCHMARK_DIR),
        "-k",
        target,
        "--benchmark-enable",
        "--benchmark-cprofile=cumtime",
        f"--benchmark-cprofile-top={top}",
        "-q",
        "-p",
        "no:cacheprovider",
    ]
    with console.status("[bold cyan]profiling…[/bold cyan]", spinner="dots"):
        proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    out = proc.stdout or ""
    if (
        proc.returncode == 5
        or "no tests ran" in out
        or " deselected" in out
        and "passed" not in out
    ):
        console.print(
            f"[yellow]nothing matched -k '{target}'.[/yellow] TARGET is a test-name "
            "pattern, not a group label — e.g. use [bold]mutate_collection[/bold] "
            "for group 'noop-mutation-collection'."
        )
        raise typer.Exit(1)
    # Drop pytest's noisy benchmark table; print only the cProfile section.
    # Use plain print so rich doesn't re-flow the monospace frame table.
    marker = out.find("cProfile")
    print(out[marker:] if marker != -1 else out)
    raise typer.Exit(proc.returncode)


if __name__ == "__main__":
    app()
