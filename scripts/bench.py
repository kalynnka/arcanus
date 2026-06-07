#!/usr/bin/env python
"""Local benchmark gap reporter & regression gate for arcanus.

Runs the wall-clock benchmark suite, pairs each ``@pytest.mark.benchmark`` group
into a reference vs candidate, and reports the GAP (candidate / reference) for
the two axes the project cares about:

  Axis A  pure Pydantic (test_pydantic_*)            vs Transmuter@NoOp (test_transmuter_*)
  Axis B  Pydantic+SQLAlchemy (test_pydantic_sqlalchemy_*) vs materia (test_arcanus_*)
          (pure ORM test_sqlalchemy_* is shown as context)

The ratio is measured within a single run, so it cancels machine noise. The gate
does NOT use absolute ceilings — it compares this branch against a main-branch
run and fails only if a group's gap regresses by more than 10%.

Commands:
  report                 run the suite and print the gap report (default)
  compare BASELINE.json  diff this run's gaps against a saved main run;
                         add --gate to fail when a gap regresses > --max-regression
  profile TARGET         cProfile the benchmarks matching ``-k TARGET`` (drill a gap)
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import statistics
import subprocess
import sys
import tempfile

from rich.box import SIMPLE_HEAVY
from rich.console import Console
from rich.table import Table

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
BENCHMARK_DIR = REPO_ROOT / "benchmark"

# Most-specific prefix FIRST: test_pydantic_sqlalchemy_ must beat test_pydantic_.
REFERENCE_PREFIXES = ("test_pydantic_sqlalchemy_", "test_pydantic_")
CANDIDATE_PREFIXES = ("test_arcanus_", "test_transmuter_")
CONTEXT_PREFIXES = ("test_sqlalchemy_",)

AXIS_TITLES = {
    "A": "Axis A — pure Pydantic (ref) vs Transmuter@NoOp (cand)",
    "B": "Axis B — Pydantic+SQLAlchemy (ref) vs arcanus materia (cand)",
}

console = Console()


@dataclasses.dataclass
class Record:
    axis: str  # "A" or "B"
    group: str
    size: str  # parametrize id like "n=10", or "" when unparametrized
    role: str  # "reference" | "candidate" | "context"
    seconds: float  # the min time (stable noise floor)


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


def run_suite(args, json_path: pathlib.Path) -> None:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(BENCHMARK_DIR),
        "--benchmark-enable",
        f"--benchmark-warmup-iterations={args.warmup_iters}",
        f"--benchmark-json={json_path}",
        "-q",
        "-p",
        "no:cacheprovider",
    ]
    if args.rounds:
        cmd.append(f"--benchmark-min-rounds={args.rounds}")
    if args.max_time:
        cmd.append(f"--benchmark-max-time={args.max_time}")
    if args.k:
        cmd += ["-k", args.k]
    # Results are read from the JSON file, so pytest-benchmark's own (ugly) console
    # table is captured and discarded — only surfaced if the run fails.
    with console.status("[bold]running benchmarks…[/bold]", spinner="dots"):
        completed = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    if completed.returncode != 0:
        console.print(completed.stdout)
        console.print(completed.stderr)
        raise SystemExit(f"pytest exited with code {completed.returncode}")


def load_payload(args) -> dict:
    if args.json:
        return json.loads(pathlib.Path(args.json).read_text())
    with tempfile.TemporaryDirectory() as tmp:
        json_path = pathlib.Path(tmp) / "bench.json"
        run_suite(args, json_path)
        return json.loads(json_path.read_text())


def build_records(payload: dict) -> list[Record]:
    records: list[Record] = []
    for entry in payload.get("benchmarks", []):
        role = classify_role(entry["name"])
        if role is None:
            continue
        group = entry.get("group") or entry["name"]
        axis = "A" if group.startswith("noop-") else "B"
        records.append(
            Record(
                axis=axis,
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


def compute_gaps(records: list[Record]) -> list[GapRow]:
    buckets: dict[tuple[str, str, str], list[Record]] = {}
    for record in records:
        buckets.setdefault((record.axis, record.group, record.size), []).append(record)

    rows: list[GapRow] = []
    for (axis, group, size), bucket in buckets.items():
        reference = _best(bucket, "reference")
        candidate = _best(bucket, "candidate")
        if reference is None or candidate is None:
            continue
        rows.append(
            GapRow(
                axis=axis,
                group=group,
                size=size,
                reference=reference,
                candidate=candidate,
                context=_best(bucket, "context"),
            )
        )
    rows.sort(key=lambda r: r.ratio, reverse=True)
    return rows


def _us(seconds: float) -> str:
    return f"{seconds * 1e6:,.1f}"


def _ratio_markup(ratio: float) -> str:
    color = "green" if ratio <= 1.5 else "yellow" if ratio <= 3.0 else "red"
    return f"[{color}]{ratio:.2f}×[/{color}]"


def render_report(rows: list[GapRow], axis_filter: str) -> None:
    for axis in ("A", "B"):
        if axis_filter not in ("both", axis.lower()):
            continue
        axis_rows = [r for r in rows if r.axis == axis]
        if not axis_rows:
            continue
        table = Table(title=AXIS_TITLES[axis], box=SIMPLE_HEAVY, header_style="bold")
        table.add_column("group", style="cyan", no_wrap=True)
        table.add_column("ref µs", justify="right")
        table.add_column("cand µs", justify="right")
        if axis == "B":
            table.add_column("ctx µs", justify="right", style="dim")
        table.add_column("gap", justify="right")
        for row in axis_rows:
            cells = [row.key, _us(row.reference), _us(row.candidate)]
            if axis == "B":
                cells.append(_us(row.context) if row.context is not None else "—")
            cells.append(_ratio_markup(row.ratio))
            table.add_row(*cells)
        console.print(table)
        ratios = [r.ratio for r in axis_rows]
        worst = max(axis_rows, key=lambda r: r.ratio)
        console.print(
            f"  [bold]median gap[/bold] {statistics.median(ratios):.2f}×   "
            f"[bold]max gap[/bold] {worst.ratio:.2f}× ({worst.key})\n"
        )


def render_compare(
    rows: list[GapRow], baseline_rows: list[GapRow], max_regression: float, gate: bool
) -> int:
    baseline = {(r.axis, r.key): r.ratio for r in baseline_rows}
    regressions: list[str] = []
    for axis in ("A", "B"):
        axis_rows = [r for r in rows if r.axis == axis]
        if not axis_rows:
            continue
        table = Table(
            title=f"{AXIS_TITLES[axis]}  —  vs main (gap drift)",
            box=SIMPLE_HEAVY,
            header_style="bold",
        )
        table.add_column("group", style="cyan", no_wrap=True)
        table.add_column("main gap", justify="right")
        table.add_column("now gap", justify="right")
        table.add_column("Δ", justify="right")
        table.add_column("status")
        for row in axis_rows:
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
            "[yellow]no baseline groups found — gate skipped "
            "(main has no benchmark run yet).[/yellow]"
        )
        return 0
    if gate and regressions:
        console.print(
            f"[bold red]GATE FAIL[/bold red] — {len(regressions)} group(s) regressed "
            f"more than {max_regression * 100:.0f}% vs main:"
        )
        for line in regressions:
            console.print(f"  [red]{line}[/red]")
        return 1
    if gate:
        console.print(
            f"[bold green]GATE PASS[/bold green] — no gap regressed more than "
            f"{max_regression * 100:.0f}% vs main."
        )
    return 0


def run_profile(args) -> int:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(BENCHMARK_DIR),
        "-k",
        args.target,
        "--benchmark-enable",
        "--benchmark-cprofile=cumtime",
        f"--benchmark-cprofile-top={args.top}",
        "-q",
        "-p",
        "no:cacheprovider",
    ]
    console.print(f"[dim]profiling: {' '.join(cmd)}[/dim]")
    return subprocess.run(cmd, cwd=REPO_ROOT).returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command")

    def add_run_flags(p: argparse.ArgumentParser) -> None:
        p.add_argument("--axis", choices=("a", "b", "both"), default="both")
        p.add_argument("-k", default=None, help="pytest -k pattern filter")
        p.add_argument("--warmup-iters", type=int, default=5)
        p.add_argument(
            "--rounds", type=int, default=None, help="--benchmark-min-rounds"
        )
        p.add_argument(
            "--max-time",
            type=float,
            default=None,
            help="--benchmark-max-time (seconds) to bound each benchmark",
        )
        p.add_argument(
            "--json",
            default=None,
            help="reuse an existing benchmark JSON for THIS run instead of running",
        )

    report = sub.add_parser("report", help="print the gap report (default)")
    add_run_flags(report)

    compare_p = sub.add_parser(
        "compare", help="diff gaps vs a saved main run; --gate to enforce"
    )
    add_run_flags(compare_p)
    compare_p.add_argument("baseline", help="path to a main-branch benchmark JSON")
    compare_p.add_argument(
        "--gate",
        action="store_true",
        help="exit 1 if any gap regresses more than --max-regression",
    )
    compare_p.add_argument(
        "--max-regression",
        type=float,
        default=0.10,
        help="allowed gap drift vs main before failing (default 0.10 = 10%%)",
    )

    profile_p = sub.add_parser("profile", help="cProfile benchmarks matching -k TARGET")
    profile_p.add_argument(
        "target", help="pytest -k pattern (e.g. transmuter_validate_scalar)"
    )
    profile_p.add_argument("--top", type=int, default=30)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    command = args.command or "report"

    if command == "profile":
        return run_profile(args)

    rows = compute_gaps(build_records(load_payload(args)))
    if not rows:
        console.print("[red]no paired benchmark groups found.[/red]")
        return 1

    if command == "report":
        render_report(rows, args.axis)
        return 0
    if command == "compare":
        baseline_path = pathlib.Path(args.baseline)
        baseline_text = baseline_path.read_text() if baseline_path.exists() else ""
        baseline_rows = (
            compute_gaps(build_records(json.loads(baseline_text)))
            if baseline_text.strip()
            else []
        )
        return render_compare(rows, baseline_rows, args.max_regression, args.gate)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
