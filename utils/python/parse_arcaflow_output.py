#!/usr/bin/env python3
"""
Parse Arcaflow benchmark output YAML and generate a CSV summary.

Reads an Arcaflow engine output file containing YAML benchmark
results and produces a CSV with the same columns as the fullrun
generate_summary_csv.py script.

Usage:
    python parse_arcaflow_output.py --input shmpmq.out
    python parse_arcaflow_output.py --input shmpmq.out --output results.csv
    python parse_arcaflow_output.py --input shmpmq.out --mode "container"
"""

import argparse
import csv
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install PyYAML")
    sys.exit(1)

MECHANISM_MAP = {
    "UnixDomainSocket": "uds",
    "TcpSocket": "tcp",
    "SharedMemory": "shm",
    "PosixMessageQueue": "pmq",
}

CSV_COLUMNS = [
    "test_type",
    "mode",
    "communication_method",
    "mechanism",
    "message_size",
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
    "filename",
    "command",
]


def extract_yaml_from_output(filepath: Path) -> Dict[str, Any]:
    """Extract the YAML data block from an Arcaflow output file.

    Strips leading engine log lines (timestamped info/warning/error
    lines) and trailing ``output_id:`` line, then parses the
    remaining ``output_data:`` YAML block.

    Args:
        filepath: Path to the Arcaflow output file.

    Returns:
        Parsed YAML dict rooted at the ``output_data`` key.

    Raises:
        ValueError: If no YAML data block is found.
    """
    with open(filepath, "r", encoding="utf-8") as fh:
        lines = fh.readlines()

    yaml_lines: List[str] = []
    in_yaml = False

    for line in lines:
        if line.startswith("output_data:"):
            in_yaml = True
            yaml_lines.append(line)
            continue
        if in_yaml:
            if line.startswith("output_id:"):
                break
            yaml_lines.append(line)

    if not yaml_lines:
        raise ValueError(
            f"No 'output_data:' block found in {filepath}"
        )

    raw = yaml.safe_load("".join(yaml_lines))
    return raw.get("output_data", raw)


def get_p99(percentiles: List[Dict[str, Any]]) -> Optional[int]:
    """Find the P99 value from a percentiles list.

    Args:
        percentiles: List of dicts with 'percentile' and 'value_ns'.

    Returns:
        The P99 value in nanoseconds, or None if not found.
    """
    for p in percentiles:
        if p.get("percentile") == 99 or p.get("percentile") == 99.0:
            return p.get("value_ns")
    return None


def extract_latency_metrics(
    perf_data: Optional[Dict[str, Any]], prefix: str
) -> Dict[str, Any]:
    """Extract latency metrics with a column prefix.

    Args:
        perf_data: One-way or round-trip performance results dict.
        prefix: Column prefix, e.g. ``"ow_"`` or ``"rt_"``.

    Returns:
        Dict with prefixed metric keys and integer values.
    """
    empty = {
        f"{prefix}min_ns": "",
        f"{prefix}max_ns": "",
        f"{prefix}mean_ns": "",
        f"{prefix}p99_ns": "",
    }

    if not perf_data:
        return empty

    latency = perf_data.get("latency")
    if not latency:
        return empty

    return {
        f"{prefix}min_ns": latency.get("min_ns", ""),
        f"{prefix}max_ns": latency.get("max_ns", ""),
        f"{prefix}mean_ns": latency.get("mean_ns", ""),
        f"{prefix}p99_ns": get_p99(latency.get("percentiles", [])),
    }


def determine_comm_method(result: Dict[str, Any]) -> str:
    """Determine the communication method from input flags.

    Uses the ``input_*`` fields stamped by the plugin onto each
    result. Falls back to heuristics when those fields are absent
    (e.g. parsing output from an older plugin build).

    Args:
        result: A single mechanism result dict.

    Returns:
        One of ``"async"``, ``"blocking"``, or ``"shm-direct"``.
    """
    shm_direct = result.get("input_shm_direct")
    if shm_direct:
        return "shm-direct"

    blocking = result.get("input_blocking")
    if blocking is False:
        return "async"

    if blocking is True or blocking is None:
        return "blocking"

    return "blocking"


def determine_test_type(test_config: Dict[str, Any]) -> str:
    """Determine whether the test used iteration count or duration.

    Args:
        test_config: The test_config dict from a mechanism result.

    Returns:
        ``"iter"`` if msg_count was set, ``"dur"`` if duration was
        set, ``"iter"`` as fallback.
    """
    duration = test_config.get("duration")
    if duration is not None and duration != "":
        dur_secs = 0
        if isinstance(duration, dict):
            dur_secs = duration.get("secs", 0)
        elif isinstance(duration, (int, float)):
            dur_secs = duration
        if dur_secs > 0:
            return "dur"

    return "iter"


def reconstruct_command(
    mechanism: str,
    test_config: Dict[str, Any],
    result: Dict[str, Any],
) -> str:
    """Reconstruct the ipc-benchmark CLI command from result data.

    Uses the ``input_*`` fields stamped by the plugin for accurate
    reconstruction of blocking, shm-direct, one-way, round-trip,
    and send-delay flags.

    Args:
        mechanism: Short mechanism name (uds, tcp, shm, pmq).
        test_config: The test_config dict from the result.
        result: The full result dict (for input_* flags).

    Returns:
        Reconstructed command string.
    """
    parts = ["ipc-benchmark", "-m", mechanism]

    msg_size = test_config.get("message_size")
    if msg_size is not None:
        parts.extend(["-s", str(msg_size)])

    msg_count = test_config.get("msg_count")
    if msg_count is not None:
        parts.extend(["-i", str(msg_count)])

    duration = test_config.get("duration")
    if duration is not None and duration != "":
        if isinstance(duration, dict):
            secs = duration.get("secs", 0)
            if secs > 0:
                parts.extend(["-d", f"{secs}s"])
        elif isinstance(duration, (int, float)) and duration > 0:
            parts.extend(["-d", f"{int(duration)}s"])
        elif isinstance(duration, str) and duration:
            parts.extend(["-d", duration])

    concurrency = result.get("input_concurrency")
    if concurrency is not None and concurrency > 1:
        parts.extend(["-c", str(concurrency)])

    warmup = test_config.get("warmup_iterations")
    if warmup is not None and warmup > 0:
        parts.extend(["-w", str(warmup)])

    blocking = result.get("input_blocking")
    if blocking is not False:
        parts.append("--blocking")

    shm_direct = result.get("input_shm_direct")
    if shm_direct:
        parts.append("--shm-direct")

    one_way = result.get("input_one_way")
    round_trip = result.get("input_round_trip")
    if one_way:
        parts.append("--one-way")
    if round_trip:
        parts.append("--round-trip")

    send_delay = result.get("input_send_delay")
    if send_delay:
        parts.extend(["--send-delay", send_delay])

    return " ".join(parts)


def build_rows(
    data: Dict[str, Any],
    mode: str,
    filename: str,
) -> List[Dict[str, Any]]:
    """Build CSV rows from parsed Arcaflow output data.

    One row is produced per mechanism result.

    Args:
        data: Parsed output_data dict.
        mode: Deployment mode label, e.g. "arcaflow".
        filename: Source filename for the CSV row.

    Returns:
        List of row dicts matching CSV_COLUMNS.
    """
    rows: List[Dict[str, Any]] = []

    benchmark = data.get("benchmark_result", data)
    results = benchmark.get("results", [])

    for result in results:
        status = result.get("status")
        if isinstance(status, dict) and "Failure" in status:
            continue
        if status != "Success":
            continue

        raw_mechanism = result.get("mechanism", "Unknown")
        mechanism = MECHANISM_MAP.get(raw_mechanism, raw_mechanism)

        test_config = result.get("test_config", {})
        message_size = test_config.get("message_size", "")
        test_type = determine_test_type(test_config)
        comm_method = determine_comm_method(result)

        summary = result.get("summary", {})
        avg_throughput = summary.get(
            "average_throughput_mb_s",
            summary.get("average_throughput_mbps", ""),
        )

        ow_results = result.get("one_way_results")
        rt_results = result.get("round_trip_results")

        total_messages = ""
        if ow_results:
            tp = ow_results.get("throughput", {})
            total_messages = tp.get("total_messages", "")
        elif rt_results:
            tp = rt_results.get("throughput", {})
            total_messages = tp.get("total_messages", "")

        ow_metrics = extract_latency_metrics(ow_results, "ow_")
        rt_metrics = extract_latency_metrics(rt_results, "rt_")

        command = reconstruct_command(
            mechanism, test_config, result
        )

        row = {
            "test_type": test_type,
            "mode": mode,
            "communication_method": comm_method,
            "mechanism": mechanism,
            "message_size": message_size,
            "total_messages_sent": total_messages,
            "average_throughput_mb_s": avg_throughput,
            **ow_metrics,
            **rt_metrics,
            "filename": filename,
            "command": command,
        }
        rows.append(row)

    return rows


def sort_rows(rows: List[Dict[str, Any]]) -> None:
    """Sort rows by test_type, mechanism, comm_method, size.

    Sorts in-place using the same ordering conventions as the
    fullrun generate_summary_csv.py script.

    Args:
        rows: List of row dicts to sort.
    """
    def sort_key(row):
        test_order = 0 if row["test_type"] == "iter" else 1
        mech_order = {"uds": 0, "tcp": 1, "shm": 2, "pmq": 3}.get(
            row["mechanism"], 9
        )
        variant_order = {
            "async": 0,
            "blocking": 1,
            "shm-direct": 2,
        }.get(row["communication_method"], 9)
        try:
            size = int(row["message_size"])
        except (ValueError, TypeError):
            size = 0
        return (test_order, mech_order, variant_order, size)

    rows.sort(key=sort_key)


def print_preview(rows: List[Dict[str, Any]]) -> None:
    """Print a formatted preview table of the first 15 rows.

    Args:
        rows: List of row dicts to preview.
    """
    print("\nPreview:")
    print("-" * 130)
    header = (
        f"{'type':<5} {'mode':<12} {'comm_method':<12} "
        f"{'mech':<4} {'size':<6} {'msgs':<8} "
        f"{'MB/s':<10} {'ow_mean':<12} {'rt_mean':<12}"
    )
    print(header)
    print("-" * 130)

    for row in rows[:15]:
        ow_mean = row.get("ow_mean_ns", "")
        rt_mean = row.get("rt_mean_ns", "")
        ow_str = f"{int(ow_mean):,}" if ow_mean != "" else "-"
        rt_str = f"{int(rt_mean):,}" if rt_mean != "" else "-"

        line = (
            f"{row.get('test_type', ''):<5} "
            f"{row.get('mode', ''):<12} "
            f"{row.get('communication_method', ''):<12} "
            f"{row.get('mechanism', ''):<4} "
            f"{str(row.get('message_size', '')):<6} "
            f"{str(row.get('total_messages_sent', '')):<8} "
            f"{str(row.get('average_throughput_mb_s', ''))[:8]:<10} "
            f"{ow_str:<12} {rt_str:<12}"
        )
        print(line)

    if len(rows) > 15:
        print(f"... and {len(rows) - 15} more rows")


def main() -> int:
    """Parse Arcaflow output and write CSV summary."""
    parser = argparse.ArgumentParser(
        description=(
            "Parse Arcaflow benchmark output YAML into a CSV"
            " matching the fullrun benchmark_results.csv format."
        ),
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Path to the Arcaflow output file.",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help=(
            "Path for the CSV output file.  Defaults to the"
            " input filename with a .csv extension."
        ),
    )
    parser.add_argument(
        "--mode", "-m",
        default="arcaflow",
        help=(
            "Deployment mode label for the CSV, e.g. 'arcaflow',"
            " 'container', 'standalone'. Default: arcaflow."
        ),
    )
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        return 1

    if args.output:
        csv_path = Path(args.output).expanduser().resolve()
    else:
        csv_path = input_path.with_suffix(".csv")

    print(f"Parsing {input_path} ...")

    try:
        data = extract_yaml_from_output(input_path)
    except (ValueError, yaml.YAMLError) as exc:
        print(f"ERROR: Failed to parse output: {exc}")
        return 1

    rows = build_rows(data, args.mode, input_path.name)

    if not rows:
        print("No successful mechanism results found!")
        return 1

    sort_rows(rows)

    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=CSV_COLUMNS, extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"CSV written to: {csv_path}")
    print(f"Total rows: {len(rows)}")
    print_preview(rows)

    return 0


if __name__ == "__main__":
    sys.exit(main())
