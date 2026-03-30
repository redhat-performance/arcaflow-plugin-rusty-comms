#!/usr/bin/env python3
"""Run the comprehensive Arcaflow IPC benchmark suite multiple times
and produce a CSV with averaged results.

Executes the Arcaflow engine N times (default 5) using the
comprehensive test YAML, saves each run's output to run/out/,
then parses all outputs and averages the throughput and latency
fields across runs for each unique test configuration.

Usage:
    python run_comprehensive.py
    python run_comprehensive.py --iterations 3
    python run_comprehensive.py --skip-runs  # parse existing outputs only
"""

import argparse
import csv
import logging
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))
from parse_arcaflow_output import (  # noqa: E402
    CSV_COLUMNS,
    build_rows,
    extract_yaml_from_output,
    sort_rows,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).resolve().parent
UTILS_DIR = SCRIPT_DIR.parent
PLUGIN_DIR = UTILS_DIR.parent
ARCAFLOW_BIN = PLUGIN_DIR / "arcaflow"
CONFIG_FILE = PLUGIN_DIR / "config.yaml"
INPUT_FILE = (
    PLUGIN_DIR / "comprehensive-rusty-comms-arcaflow-testing.yaml"
)
OUT_DIR = UTILS_DIR / "out"

NUMERIC_FIELDS = [
    "total_messages_sent",
    "average_throughput_mb_s",
    "ow_min_ns",
    "ow_max_ns",
    "ow_mean_ns",
    "ow_p99_ns",
    "rt_min_ns",
    "rt_max_ns",
    "rt_mean_ns",
    "rt_p99_ns",
]

IDENTITY_FIELDS = [
    "test_type",
    "communication_method",
    "mechanism",
    "message_size",
    "command",
]


def run_arcaflow(iteration: int, total: int) -> Path:
    """Execute one Arcaflow benchmark run.

    Args:
        iteration: 1-based iteration number.
        total: Total number of planned iterations.

    Returns:
        Path to the output file.

    Raises:
        RuntimeError: If the arcaflow process fails.
    """
    out_file = OUT_DIR / f"run{iteration}.out"
    logger.info(
        "Starting iteration %d/%d -> %s",
        iteration,
        total,
        out_file,
    )

    start = time.time()
    with open(out_file, "w", encoding="utf-8") as fh:
        result = subprocess.run(
            [
                str(ARCAFLOW_BIN),
                "-input", str(INPUT_FILE),
                "-config", str(CONFIG_FILE),
            ],
            stdout=fh,
            stderr=subprocess.STDOUT,
            cwd=str(PLUGIN_DIR),
        )
    elapsed = time.time() - start

    if result.returncode != 0:
        logger.error(
            "Iteration %d failed (exit %d) after %.1fs."
            " Check %s for details.",
            iteration,
            result.returncode,
            elapsed,
            out_file,
        )
        raise RuntimeError(
            f"Arcaflow iteration {iteration} exited with"
            f" code {result.returncode}"
        )

    logger.info(
        "Iteration %d completed in %.1fs", iteration, elapsed
    )
    return out_file


def parse_output(out_file: Path) -> List[Dict[str, Any]]:
    """Parse a single Arcaflow output file into rows.

    Args:
        out_file: Path to an Arcaflow output file.

    Returns:
        List of row dicts matching CSV_COLUMNS.
    """
    data = extract_yaml_from_output(out_file)
    rows = build_rows(data, "arcaflow", out_file.name)
    return rows


def make_key(row: Dict[str, Any]) -> tuple:
    """Build a unique identity key for a test result row.

    Args:
        row: A single CSV row dict.

    Returns:
        Tuple of identity field values.
    """
    return tuple(str(row.get(f, "")) for f in IDENTITY_FIELDS)


def to_float(value: Any) -> Optional[float]:
    """Safely convert a value to float.

    Args:
        value: The value to convert.

    Returns:
        Float value, or None if conversion fails.
    """
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def average_rows(
    all_runs: List[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Average numeric fields across multiple runs.

    Groups rows by identity key, then computes the mean of
    each numeric field across all runs where that field has
    a value.

    Args:
        all_runs: List of row lists, one per run.

    Returns:
        List of averaged row dicts.
    """
    grouped: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)

    for run_rows in all_runs:
        for row in run_rows:
            key = make_key(row)
            grouped[key].append(row)

    averaged: List[Dict[str, Any]] = []

    for key, rows in grouped.items():
        base = dict(rows[0])
        base["filename"] = f"avg_{len(rows)}_runs"

        for field in NUMERIC_FIELDS:
            values = [
                v for v in (to_float(r.get(field)) for r in rows)
                if v is not None
            ]
            if values:
                avg = sum(values) / len(values)
                if field == "average_throughput_mb_s":
                    base[field] = round(avg, 1)
                else:
                    base[field] = int(round(avg))
            else:
                base[field] = ""

        averaged.append(base)

    return averaged


def write_csv(
    rows: List[Dict[str, Any]], csv_path: Path
) -> None:
    """Write rows to a CSV file.

    Args:
        rows: List of row dicts.
        csv_path: Output path for the CSV file.
    """
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=CSV_COLUMNS, extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    """Run comprehensive benchmark suite and produce averaged CSV."""
    parser = argparse.ArgumentParser(
        description=(
            "Run the Arcaflow IPC benchmark suite multiple"
            " times and produce a CSV with averaged results."
        ),
    )
    parser.add_argument(
        "--iterations", "-n",
        type=int,
        default=5,
        help="Number of benchmark iterations (default: 5).",
    )
    parser.add_argument(
        "--skip-runs",
        action="store_true",
        help=(
            "Skip running benchmarks; only parse existing"
            " output files in run/out/."
        ),
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help=(
            "Path for the averaged CSV output file."
            " Default: run/out/comprehensive_averaged.csv."
        ),
    )
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    csv_path = (
        Path(args.output) if args.output
        else OUT_DIR / "comprehensive_averaged.csv"
    )

    out_files: List[Path] = []

    if not args.skip_runs:
        for binary in [ARCAFLOW_BIN, CONFIG_FILE, INPUT_FILE]:
            if not binary.exists():
                logger.error("Required file not found: %s", binary)
                return 1

        total_start = time.time()
        for i in range(1, args.iterations + 1):
            try:
                out_file = run_arcaflow(i, args.iterations)
                out_files.append(out_file)
            except RuntimeError as exc:
                logger.error("Aborting: %s", exc)
                return 1

        total_elapsed = time.time() - total_start
        logger.info(
            "All %d iterations completed in %.1fs (%.1fs avg)",
            args.iterations,
            total_elapsed,
            total_elapsed / args.iterations,
        )
    else:
        logger.info("Skipping runs, parsing existing outputs...")
        for f in sorted(OUT_DIR.glob("run*.out")):
            out_files.append(f)
        if not out_files:
            logger.error("No run*.out files found in %s", OUT_DIR)
            return 1
        logger.info("Found %d output files", len(out_files))

    logger.info("Parsing %d output files...", len(out_files))
    all_runs: List[List[Dict[str, Any]]] = []
    for out_file in out_files:
        try:
            rows = parse_output(out_file)
            logger.info(
                "  %s: %d results", out_file.name, len(rows)
            )
            all_runs.append(rows)
        except Exception as exc:
            logger.error(
                "  %s: parse failed: %s", out_file.name, exc
            )

    if not all_runs:
        logger.error("No successful parses — cannot produce CSV.")
        return 1

    logger.info("Averaging across %d runs...", len(all_runs))
    averaged = average_rows(all_runs)
    sort_rows(averaged)

    write_csv(averaged, csv_path)
    logger.info("CSV written to: %s", csv_path)
    logger.info("Total unique tests: %d", len(averaged))

    return 0


if __name__ == "__main__":
    sys.exit(main())
