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

from arcaflow_plugin_sdk import plugin, schema
from arcaflow_plugin_sdk.schema import (
    ConstraintException,
    IntType,
    ListType,
    MapType,
    ObjectType,
    RefType,
    ScopeType,
)

from rusty_comms_schema import (
    BenchmarkMetadata,
    BenchmarkResult,
    ErrorOutput,
    InputParams,
    MechanismSummary,
    OverallSummary,
    SuccessOutput,
    TestRunConfig,
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

    The ``blocking`` parameter defaults to ``True`` in the schema,
    overriding the binary's async default for reproducible results.
    Pass ``blocking: false`` to use async Tokio mode.

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
    if params.blocking:
        args.append("--blocking")
    if params.buffer_size is not None:
        args.extend(["--buffer-size", str(params.buffer_size)])
    if params.warmup_iterations is not None:
        args.extend(["-w", str(params.warmup_iterations)])
    if params.percentiles is not None:
        for p in params.percentiles:
            args.extend(["--percentiles", str(p)])
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
# Schema-driven JSON deserialization
# ---------------------------------------------------------------------------

_success_schema = schema.build_object_schema(SuccessOutput)


def _normalize_for_schema(
    data: typing.Any,
    schema_type: typing.Any,
) -> typing.Any:
    """Recursively normalize raw JSON data to match SDK schema types.

    The Arcaflow SDK's ``unserialize`` rejects floats in ``IntType``
    fields and raises on dict keys absent from the schema.  The Rust
    ``ipc-benchmark`` binary emits JSON with floats for some integer
    metrics (e.g. ``mean_ns: 3200.5``) and includes extra keys like
    ``histogram_data`` that the plugin schema intentionally omits.

    This function walks the raw data in parallel with the built SDK
    schema and performs two transformations:

    1. **Strips unknown dict keys** — only keys declared in the
       schema's ``properties`` are kept.
    2. **Coerces float → int** — for fields the schema declares as
       ``IntType``, floats are rounded to the nearest integer.

    Args:
        data: Raw value from ``json.loads`` output.
        schema_type: The SDK type object describing the expected
            shape (``ObjectType``, ``IntType``, etc.).

    Returns:
        A normalized copy of *data* suitable for
        ``schema_type.unserialize()``.
    """
    if data is None:
        return None

    if isinstance(schema_type, (ScopeType, ObjectType, RefType)):
        if not isinstance(data, dict):
            return data
        props = schema_type.properties
        normalized: typing.Dict[str, typing.Any] = {}
        for prop_id, prop in props.items():
            if prop_id in data:
                normalized[prop_id] = _normalize_for_schema(
                    data[prop_id], prop.type
                )
        return normalized

    if isinstance(schema_type, ListType):
        if not isinstance(data, list):
            return data
        return [
            _normalize_for_schema(item, schema_type.items)
            for item in data
        ]

    if isinstance(schema_type, MapType):
        if not isinstance(data, dict):
            return data
        return {
            k: _normalize_for_schema(v, schema_type.values)
            for k, v in data.items()
        }

    if isinstance(schema_type, IntType):
        if isinstance(data, float):
            return int(round(data))
        return data

    return data


def _parse_json_output(
    raw: typing.Dict[str, typing.Any],
) -> SuccessOutput:
    """Parse the complete FinalBenchmarkResults JSON into SuccessOutput.

    The Rust binary serializes its ``Status`` enum as either the
    string ``"Success"`` or the dict ``{"Failure": "reason"}``.
    This function normalizes that into two typed fields
    (``status`` and ``failure_reason``) before handing off to
    the SDK's ``unserialize`` for validated dataclass construction.

    Args:
        raw: Parsed JSON dict from the ipc-benchmark output file.

    Returns:
        Populated SuccessOutput dataclass.

    Raises:
        ConstraintException: If the JSON structure does not
            conform to the SuccessOutput schema after
            normalization.
    """
    for result in raw.get("results", []):
        status = result.get("status")
        if isinstance(status, dict) and "Failure" in status:
            result["status"] = "Failure"
            result["failure_reason"] = status["Failure"]
        elif isinstance(status, str):
            result["failure_reason"] = None
        else:
            result["status"] = str(status)
            result["failure_reason"] = None

    normalized = _normalize_for_schema(raw, _success_schema)
    return _success_schema.unserialize(normalized)


# ---------------------------------------------------------------------------
# SIGTERM forwarding to child process groups
# ---------------------------------------------------------------------------

_active_child: typing.Optional[subprocess.Popen] = None


def _sigterm_handler(signum: int, frame: typing.Any) -> None:
    """Forward SIGTERM to the active child's process group.

    The Arcaflow engine sends SIGTERM to the plugin when shutting
    down.  Python's default handler (``SIG_DFL``) terminates the
    process immediately without running ``finally`` blocks, which
    would orphan any running ``ipc-benchmark`` process group
    started with ``start_new_session=True``.

    This handler sends SIGTERM to the child's process group
    before re-raising SIGTERM with the default handler so the
    plugin exits with the correct signal status.

    Note: This handler intentionally avoids logging and blocking
    waits to remain async-signal-safe.
    """
    proc = _active_child
    if proc is not None:
        try:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    os.kill(os.getpid(), signal.SIGTERM)


signal.signal(signal.SIGTERM, _sigterm_handler)


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
    global _active_child
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    _active_child = proc
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_process_group(proc, test_index)
        raise
    finally:
        if proc.poll() is None:
            _kill_process_group(proc, test_index)
        _active_child = None

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
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        return
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
            result = _run_subprocess(
                cmd, test_index, test_config.timeout
            )
        except subprocess.TimeoutExpired:
            return "error", ErrorOutput(
                error=(
                    f"Test {test_index + 1} timed out after"
                    f" {test_config.timeout} seconds."
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
        except (
            KeyError, TypeError, ValueError, ConstraintException,
        ) as exc:
            return "error", ErrorOutput(
                error=(
                    f"Test {test_index + 1}: Failed to parse"
                    f" results JSON: {exc}"
                )
            )

        _stamp_input_flags(output, test_config)

    return "success", output


def _min_optional(
    a: typing.Optional[int],
    b: typing.Optional[int],
) -> typing.Optional[int]:
    """Return the minimum of two optional ints, ignoring Nones."""
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


def _merge_outputs(
    outputs: typing.List[SuccessOutput],
) -> SuccessOutput:
    """Merge results from multiple test runs into one SuccessOutput.

    Uses the metadata from the first run, concatenates all
    per-mechanism results, and combines the overall summaries.

    When multiple runs benchmark the same mechanism (e.g. UDS
    with different message sizes), their summaries are aggregated:
    total messages are summed, the best throughput is kept, and
    the best (lowest) latencies are kept.  The fastest and
    lowest-latency winners are derived from the final merged
    mechanism data to avoid inconsistencies.

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

    for out in outputs:
        all_results.extend(out.results)
        total_messages += out.summary.total_messages
        total_bytes += out.summary.total_bytes
        total_errors += out.summary.total_errors

        for name, mech in out.summary.mechanisms.items():
            if name not in all_mechanisms:
                all_mechanisms[name] = MechanismSummary(
                    mechanism=mech.mechanism,
                    average_throughput_mbps=(
                        mech.average_throughput_mbps
                    ),
                    total_messages=mech.total_messages,
                    p95_latency_ns=mech.p95_latency_ns,
                    p99_latency_ns=mech.p99_latency_ns,
                )
            else:
                existing = all_mechanisms[name]
                all_mechanisms[name] = MechanismSummary(
                    mechanism=existing.mechanism,
                    average_throughput_mbps=max(
                        existing.average_throughput_mbps,
                        mech.average_throughput_mbps,
                    ),
                    total_messages=(
                        existing.total_messages
                        + mech.total_messages
                    ),
                    p95_latency_ns=_min_optional(
                        existing.p95_latency_ns,
                        mech.p95_latency_ns,
                    ),
                    p99_latency_ns=_min_optional(
                        existing.p99_latency_ns,
                        mech.p99_latency_ns,
                    ),
                )

    fastest_mechanism = None
    fastest_throughput = 0.0
    lowest_latency_mechanism = None
    lowest_latency = float("inf")

    for name, mech in all_mechanisms.items():
        if mech.average_throughput_mbps > fastest_throughput:
            fastest_throughput = mech.average_throughput_mbps
            fastest_mechanism = name
        if (
            mech.p95_latency_ns is not None
            and mech.p95_latency_ns < lowest_latency
        ):
            lowest_latency = mech.p95_latency_ns
            lowest_latency_mechanism = name

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
