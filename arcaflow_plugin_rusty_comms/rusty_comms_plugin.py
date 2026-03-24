#!/usr/bin/env python3
"""Arcaflow plugin that wraps the rusty-comms IPC benchmark suite.

Executes the ``ipc-benchmark`` binary, parses the structured JSON output,
and returns strongly-typed results to the Arcaflow engine.
"""

import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import typing

from arcaflow_plugin_sdk import plugin

from rusty_comms_schema import (
    BenchmarkMetadata,
    BenchmarkResult,
    BenchmarkSummary,
    ErrorOutput,
    InputParams,
    LatencyMetrics,
    MechanismSummary,
    OverallSummary,
    PercentileValue,
    PerformanceMetrics,
    SuccessOutput,
    SystemInfo,
    TestConfiguration,
    TestRunConfig,
    ThroughputMetrics,
)

logger = logging.getLogger("rusty_comms_plugin")

BINARY_NAME = "ipc-benchmark"
BINARY_SEARCH_PATHS = [
    "/usr/local/bin",
    "/usr/bin",
    "/app",
]


def _find_binary() -> str:
    """Locate the ipc-benchmark binary on the filesystem.

    Searches common install paths and the system PATH.

    Returns:
        Absolute path to the binary.

    Raises:
        FileNotFoundError: If the binary cannot be found.
    """
    for directory in BINARY_SEARCH_PATHS:
        candidate = os.path.join(directory, BINARY_NAME)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    found = shutil.which(BINARY_NAME)
    if found:
        return found

    raise FileNotFoundError(
        f"Could not find '{BINARY_NAME}' in {BINARY_SEARCH_PATHS}"
        f" or on PATH."
    )


def _build_cli_args(
    params: TestRunConfig, output_file: str
) -> typing.List[str]:
    """Translate a TestRunConfig into CLI arguments for ipc-benchmark.

    Blocking mode is enabled by default unless explicitly set
    to False.

    Args:
        params: Validated test run parameters.
        output_file: Path where JSON results will be written.

    Returns:
        List of CLI argument strings.
    """
    args: typing.List[str] = []

    mechanisms = [m.value for m in params.mechanisms]
    args.extend(["-m"] + mechanisms)

    args.extend(["--output-file", output_file])

    if params.message_size is not None:
        args.extend(["-s", str(params.message_size)])
    if params.msg_count is not None:
        args.extend(["-i", str(params.msg_count)])
    if params.duration is not None and params.duration != "":
        args.extend(["-d", params.duration])
    if params.concurrency is not None:
        args.extend(["-c", str(params.concurrency)])
    if params.blocking is not False:
        args.append("--blocking")
    if params.buffer_size is not None:
        args.extend(["--buffer-size", str(params.buffer_size)])
    if params.warmup_iterations is not None:
        args.extend(["-w", str(params.warmup_iterations)])
    if params.percentiles is not None:
        args.append("--percentiles")
        args.extend([str(p) for p in params.percentiles])
    if params.one_way:
        args.append("--one-way")
    if params.round_trip:
        args.append("--round-trip")
    if params.send_delay is not None:
        args.extend(["--send-delay", params.send_delay])
    if params.server_affinity is not None:
        args.extend(["--server-affinity", str(params.server_affinity)])
    if params.client_affinity is not None:
        args.extend(["--client-affinity", str(params.client_affinity)])
    if params.shm_direct:
        args.append("--shm-direct")
    if params.continue_on_error:
        args.append("--continue-on-error")
    if params.include_first_message:
        args.append("--include-first-message")
    if params.host is not None:
        args.extend(["--host", params.host])
    if params.port is not None:
        args.extend(["--port", str(params.port)])
    if params.pmq_priority is not None:
        args.extend(["--pmq-priority", str(params.pmq_priority)])
    if params.quiet:
        args.append("--quiet")
    if params.extra_args:
        args.extend(params.extra_args)

    return args


# ---------------------------------------------------------------------------
# JSON -> dataclass mapping helpers
# ---------------------------------------------------------------------------


def _parse_percentiles(
    raw: typing.List[typing.Dict[str, typing.Any]],
) -> typing.List[PercentileValue]:
    """Convert raw percentile dicts to PercentileValue instances."""
    return [
        PercentileValue(
            percentile=p["percentile"],
            value_ns=int(p["value_ns"]),
        )
        for p in raw
    ]


def _parse_latency(
    raw: typing.Optional[typing.Dict[str, typing.Any]],
) -> typing.Optional[LatencyMetrics]:
    """Convert a raw latency dict to a LatencyMetrics instance."""
    if raw is None:
        return None
    return LatencyMetrics(
        latency_type=raw["latency_type"],
        min_ns=int(raw["min_ns"]),
        max_ns=int(raw["max_ns"]),
        mean_ns=int(round(float(raw["mean_ns"]))),
        median_ns=int(round(float(raw["median_ns"]))),
        std_dev_ns=int(round(float(raw["std_dev_ns"]))),
        percentiles=_parse_percentiles(raw.get("percentiles", [])),
        total_samples=int(raw["total_samples"]),
    )


def _parse_throughput(
    raw: typing.Dict[str, typing.Any],
) -> ThroughputMetrics:
    """Convert a raw throughput dict to a ThroughputMetrics instance."""
    return ThroughputMetrics(
        messages_per_second=int(round(float(raw["messages_per_second"]))),
        bytes_per_second=int(round(float(raw["bytes_per_second"]))),
        total_messages=int(raw["total_messages"]),
        total_bytes=int(raw["total_bytes"]),
        duration_ns=int(raw["duration_ns"]),
    )


def _parse_performance(
    raw: typing.Optional[typing.Dict[str, typing.Any]],
) -> typing.Optional[PerformanceMetrics]:
    """Convert raw performance metrics to a PerformanceMetrics instance."""
    if raw is None:
        return None
    return PerformanceMetrics(
        latency=_parse_latency(raw.get("latency")),
        throughput=_parse_throughput(raw["throughput"]),
        timestamp=str(raw.get("timestamp", "")),
    )


def _parse_system_info(
    raw: typing.Dict[str, typing.Any],
) -> SystemInfo:
    """Convert a raw system_info dict to a SystemInfo instance."""
    return SystemInfo(
        os=raw["os"],
        architecture=raw["architecture"],
        cpu_cores=int(raw["cpu_cores"]),
        memory_gb=round(float(raw["memory_gb"]), 1),
        rust_version=raw["rust_version"],
        benchmark_version=raw["benchmark_version"],
    )


def _parse_test_config(
    raw: typing.Dict[str, typing.Any],
) -> TestConfiguration:
    """Convert a raw test_config dict to a TestConfiguration instance."""
    return TestConfiguration(
        message_size=int(raw["message_size"]),
        buffer_size=int(raw["buffer_size"]),
        concurrency=int(raw["concurrency"]),
        msg_count=(
            int(raw["msg_count"]) if raw.get("msg_count") is not None
            else None
        ),
        duration=raw.get("duration"),
        one_way_enabled=bool(raw["one_way_enabled"]),
        round_trip_enabled=bool(raw["round_trip_enabled"]),
        warmup_iterations=int(raw["warmup_iterations"]),
        percentiles=[float(p) for p in raw["percentiles"]],
    )


def _parse_benchmark_summary(
    raw: typing.Dict[str, typing.Any],
) -> BenchmarkSummary:
    """Convert a raw summary dict to a BenchmarkSummary instance."""
    return BenchmarkSummary(
        total_messages_sent=int(raw["total_messages_sent"]),
        total_bytes_transferred=int(raw["total_bytes_transferred"]),
        average_throughput_mbps=round(
            float(raw["average_throughput_mbps"]), 1
        ),
        peak_throughput_mbps=round(
            float(raw["peak_throughput_mbps"]), 1
        ),
        error_count=int(raw["error_count"]),
        average_latency_ns=(
            int(round(float(raw["average_latency_ns"])))
            if raw.get("average_latency_ns") is not None
            else None
        ),
        min_latency_ns=(
            int(raw["min_latency_ns"])
            if raw.get("min_latency_ns") is not None
            else None
        ),
        max_latency_ns=(
            int(raw["max_latency_ns"])
            if raw.get("max_latency_ns") is not None
            else None
        ),
        p95_latency_ns=(
            int(raw["p95_latency_ns"])
            if raw.get("p95_latency_ns") is not None
            else None
        ),
        p99_latency_ns=(
            int(raw["p99_latency_ns"])
            if raw.get("p99_latency_ns") is not None
            else None
        ),
    )


def _parse_result(
    raw: typing.Dict[str, typing.Any],
) -> BenchmarkResult:
    """Convert a raw per-mechanism result dict to BenchmarkResult."""
    return BenchmarkResult(
        mechanism=str(raw["mechanism"]),
        status=raw["status"],
        test_config=_parse_test_config(raw["test_config"]),
        summary=_parse_benchmark_summary(raw["summary"]),
        timestamp=str(raw["timestamp"]),
        test_duration=raw["test_duration"],
        system_info=_parse_system_info(raw["system_info"]),
        one_way_results=_parse_performance(
            raw.get("one_way_results")
        ),
        round_trip_results=_parse_performance(
            raw.get("round_trip_results")
        ),
    )


def _parse_mechanism_summary(
    raw: typing.Dict[str, typing.Any],
) -> MechanismSummary:
    """Convert a raw mechanism summary dict."""
    return MechanismSummary(
        mechanism=str(raw["mechanism"]),
        average_throughput_mbps=round(
            float(raw["average_throughput_mbps"]), 1
        ),
        total_messages=int(raw["total_messages"]),
        p95_latency_ns=(
            int(raw["p95_latency_ns"])
            if raw.get("p95_latency_ns") is not None
            else None
        ),
        p99_latency_ns=(
            int(raw["p99_latency_ns"])
            if raw.get("p99_latency_ns") is not None
            else None
        ),
    )


def _parse_overall_summary(
    raw: typing.Dict[str, typing.Any],
) -> OverallSummary:
    """Convert a raw overall summary dict."""
    mechanisms = {
        name: _parse_mechanism_summary(val)
        for name, val in raw.get("mechanisms", {}).items()
    }
    return OverallSummary(
        total_messages=int(raw["total_messages"]),
        total_bytes=int(raw["total_bytes"]),
        total_errors=int(raw["total_errors"]),
        mechanisms=mechanisms,
        fastest_mechanism=raw.get("fastest_mechanism"),
        lowest_latency_mechanism=raw.get("lowest_latency_mechanism"),
    )


def _parse_json_output(
    raw: typing.Dict[str, typing.Any],
) -> SuccessOutput:
    """Parse the complete FinalBenchmarkResults JSON into SuccessOutput.

    Args:
        raw: Parsed JSON dict from the ipc-benchmark output file.

    Returns:
        Populated SuccessOutput dataclass.
    """
    meta_raw = raw["metadata"]
    metadata = BenchmarkMetadata(
        version=meta_raw["version"],
        timestamp=str(meta_raw["timestamp"]),
        total_tests=int(meta_raw["total_tests"]),
        system_info=_parse_system_info(meta_raw["system_info"]),
    )

    results = [_parse_result(r) for r in raw["results"]]

    summary = _parse_overall_summary(raw["summary"])

    return SuccessOutput(
        metadata=metadata,
        results=results,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Arcaflow step
# ---------------------------------------------------------------------------


def _run_subprocess(
    cmd: typing.List[str],
    test_index: int,
    timeout: int = 3600,
) -> subprocess.CompletedProcess:
    """Run ipc-benchmark in its own process group.

    Uses ``start_new_session=True`` so the binary and all its
    forked children (server/client pairs) share a single process
    group.  If the parent exits but orphan children remain (e.g.
    a stuck SHM server), the entire group is killed so
    ``subprocess.Popen.communicate`` never blocks on dangling
    pipes.

    Args:
        cmd: Full command list including the binary path.
        test_index: Zero-based index for log messages.
        timeout: Maximum seconds before the process is killed.

    Returns:
        A ``CompletedProcess`` with captured stdout/stderr.

    Raises:
        subprocess.TimeoutExpired: If the timeout elapses.
        OSError: If the binary cannot be executed.
    """
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_process_group(proc, test_index)
        raise
    finally:
        if proc.poll() is None:
            _kill_process_group(proc, test_index)

    return subprocess.CompletedProcess(
        args=cmd,
        returncode=proc.returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _kill_process_group(
    proc: subprocess.Popen,
    test_index: int,
) -> None:
    """Kill the entire process group of a Popen instance.

    Sends SIGTERM first, then SIGKILL after 5 seconds if
    any processes survive.

    Args:
        proc: The Popen object whose session should be killed.
        test_index: Zero-based index for log messages.
    """
    pgid = os.getpgid(proc.pid)
    logger.warning(
        "Test %d: Killing process group %d",
        test_index + 1,
        pgid,
    )
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        logger.warning(
            "Test %d: SIGTERM did not stop group %d;"
            " sending SIGKILL",
            test_index + 1,
            pgid,
        )
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=5)


def _stamp_input_flags(
    output: SuccessOutput,
    config: TestRunConfig,
) -> None:
    """Copy original input flags onto each BenchmarkResult.

    The ipc-benchmark binary does not record flags like
    ``--blocking``, ``--shm-direct``, ``--one-way``, or
    ``--send-delay`` in its output JSON.  This function
    stamps those values from the original input onto every
    result so downstream parsers can distinguish test modes.

    Args:
        output: Parsed SuccessOutput to modify in-place.
        config: The original TestRunConfig for this run.
    """
    for result in output.results:
        result.input_blocking = config.blocking
        result.input_shm_direct = config.shm_direct
        result.input_one_way = config.one_way
        result.input_round_trip = config.round_trip
        result.input_send_delay = config.send_delay
        result.input_concurrency = config.concurrency


def _run_single_test(
    binary: str,
    test_config: TestRunConfig,
    test_index: int,
) -> typing.Tuple[str, typing.Union[SuccessOutput, ErrorOutput]]:
    """Execute a single benchmark test run.

    Args:
        binary: Path to the ipc-benchmark binary.
        test_config: Parameters for this test run.
        test_index: Zero-based index for logging context.

    Returns:
        A tuple of (output_id, output_data).
    """
    with tempfile.TemporaryDirectory(
        prefix=f"rusty_comms_{test_index}_"
    ) as tmp_dir:
        output_file = os.path.join(tmp_dir, "results.json")
        cli_args = _build_cli_args(test_config, output_file)
        cmd = [binary] + cli_args

        logger.info(
            "Test %d: Running: %s",
            test_index + 1,
            " ".join(cmd),
        )

        try:
            result = _run_subprocess(cmd, test_index)
        except subprocess.TimeoutExpired:
            return "error", ErrorOutput(
                error=(
                    f"Test {test_index + 1} timed out after"
                    f" 3600 seconds."
                )
            )
        except OSError as exc:
            return "error", ErrorOutput(
                error=(
                    f"Test {test_index + 1}: Failed to execute"
                    f" {binary}: {exc}"
                )
            )

        if result.returncode != 0:
            stderr_tail = (
                result.stderr[-2000:] if result.stderr else ""
            )
            return "error", ErrorOutput(
                error=(
                    f"Test {test_index + 1}:"
                    f" ipc-benchmark exited with code"
                    f" {result.returncode}."
                    f" stderr: {stderr_tail}"
                )
            )

        if not os.path.isfile(output_file):
            return "error", ErrorOutput(
                error=(
                    f"Test {test_index + 1}: ipc-benchmark"
                    f" completed but did not produce an output"
                    f" file at {output_file}."
                    f" stdout: {result.stdout[-1000:]}"
                )
            )

        try:
            with open(output_file, "r", encoding="utf-8") as fh:
                raw_json = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            return "error", ErrorOutput(
                error=(
                    f"Test {test_index + 1}: Failed to read"
                    f" results JSON: {exc}"
                )
            )

        try:
            output = _parse_json_output(raw_json)
        except (KeyError, TypeError, ValueError) as exc:
            return "error", ErrorOutput(
                error=(
                    f"Test {test_index + 1}: Failed to parse"
                    f" results JSON: {exc}"
                )
            )

        _stamp_input_flags(output, test_config)

    return "success", output


def _merge_outputs(
    outputs: typing.List[SuccessOutput],
) -> SuccessOutput:
    """Merge results from multiple test runs into one SuccessOutput.

    Uses the metadata from the first run, concatenates all
    per-mechanism results, and combines the overall summaries.

    Args:
        outputs: List of successful test run outputs.

    Returns:
        A single merged SuccessOutput.
    """
    first_meta = outputs[0].metadata
    all_results: typing.List[BenchmarkResult] = []
    total_messages = 0
    total_bytes = 0
    total_errors = 0
    all_mechanisms: typing.Dict[str, MechanismSummary] = {}
    fastest_mechanism = None
    fastest_throughput = 0.0
    lowest_latency_mechanism = None
    lowest_latency = float("inf")

    for out in outputs:
        all_results.extend(out.results)
        total_messages += out.summary.total_messages
        total_bytes += out.summary.total_bytes
        total_errors += out.summary.total_errors
        all_mechanisms.update(out.summary.mechanisms)

        if (
            out.summary.fastest_mechanism
            and out.summary.mechanisms
        ):
            key = out.summary.fastest_mechanism
            if key in out.summary.mechanisms:
                tp = out.summary.mechanisms[key].average_throughput_mbps
                if tp > fastest_throughput:
                    fastest_throughput = tp
                    fastest_mechanism = key

        if (
            out.summary.lowest_latency_mechanism
            and out.summary.mechanisms
        ):
            key = out.summary.lowest_latency_mechanism
            if key in out.summary.mechanisms:
                lat = out.summary.mechanisms[key].p95_latency_ns
                if lat is not None and lat < lowest_latency:
                    lowest_latency = lat
                    lowest_latency_mechanism = key

    merged_summary = OverallSummary(
        total_messages=total_messages,
        total_bytes=total_bytes,
        total_errors=total_errors,
        mechanisms=all_mechanisms,
        fastest_mechanism=fastest_mechanism,
        lowest_latency_mechanism=lowest_latency_mechanism,
    )

    merged_metadata = BenchmarkMetadata(
        version=first_meta.version,
        timestamp=first_meta.timestamp,
        total_tests=len(all_results),
        system_info=first_meta.system_info,
    )

    return SuccessOutput(
        metadata=merged_metadata,
        results=all_results,
        summary=merged_summary,
    )


@plugin.step(
    id="run-benchmark",
    name="Run IPC Benchmark",
    description=(
        "Executes one or more rusty-comms IPC benchmark test runs"
        " and returns structured latency and throughput results."
    ),
    outputs={"success": SuccessOutput, "error": ErrorOutput},
)
def run_benchmark(
    params: InputParams,
) -> typing.Tuple[str, typing.Union[SuccessOutput, ErrorOutput]]:
    """Run benchmark tests and return merged results.

    Iterates over each test configuration in ``params.tests``,
    executes ipc-benchmark for each, and merges the results
    into a single output.

    Args:
        params: Input containing a list of test run configs.

    Returns:
        A tuple of (output_id, output_data) where output_id is
        'success' or 'error'.
    """
    try:
        binary = _find_binary()
    except FileNotFoundError as exc:
        return "error", ErrorOutput(error=str(exc))

    successful_outputs: typing.List[SuccessOutput] = []

    for idx, test_config in enumerate(params.tests):
        output_id, output_data = _run_single_test(
            binary, test_config, idx
        )
        if output_id == "error":
            return "error", output_data
        successful_outputs.append(output_data)

    merged = _merge_outputs(successful_outputs)
    return "success", merged


if __name__ == "__main__":
    sys.exit(
        plugin.run(
            plugin.build_schema(
                run_benchmark,
            )
        )
    )
