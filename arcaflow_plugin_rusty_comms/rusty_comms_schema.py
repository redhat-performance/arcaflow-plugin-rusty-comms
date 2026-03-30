#!/usr/bin/env python3
"""Schema definitions for the Arcaflow rusty-comms IPC benchmark plugin.

Defines strongly-typed input parameters and output data structures that
map to the rusty-comms CLI arguments and JSON output format respectively.
"""

import enum
import typing
from dataclasses import dataclass
from arcaflow_plugin_sdk import schema


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Mechanism(enum.Enum):
    """IPC mechanisms supported by rusty-comms."""

    uds = "uds"
    shm = "shm"
    tcp = "tcp"
    pmq = "pmq"
    all = "all"


# ---------------------------------------------------------------------------
# Input schema
# ---------------------------------------------------------------------------


@dataclass
class TestRunConfig:
    """Configuration for a single benchmark test run.

    Each test run specifies which IPC mechanisms to test and
    the parameters for that run. All parameters except
    ``mechanisms`` are optional and fall back to rusty-comms
    defaults when omitted.
    """

    mechanisms: typing.Annotated[
        typing.List[Mechanism],
        schema.name("IPC Mechanisms"),
        schema.description(
            "IPC mechanisms to benchmark. Use 'all' to test every"
            " available mechanism. Valid values: uds, shm, tcp,"
            " pmq, all."
        ),
        schema.min(1),
    ]

    message_size: typing.Annotated[
        typing.Optional[int],
        schema.name("Message Size"),
        schema.description("Message payload size in bytes."),
        schema.min(1),
    ] = None

    msg_count: typing.Annotated[
        typing.Optional[int],
        schema.name("Message Count"),
        schema.description(
            "Number of messages to send. Ignored when duration is set."
        ),
        schema.min(1),
    ] = None

    duration: typing.Annotated[
        typing.Optional[str],
        schema.name("Duration"),
        schema.description(
            "Fixed test duration, e.g. '30s', '5m', '1h'."
            " Takes precedence over message count."
        ),
    ] = None

    concurrency: typing.Annotated[
        typing.Optional[int],
        schema.name("Concurrency"),
        schema.description("Number of concurrent workers/threads."),
        schema.min(1),
    ] = None

    blocking: typing.Annotated[
        typing.Optional[bool],
        schema.name("Blocking Mode"),
        schema.description(
            "Use blocking I/O. The plugin defaults to blocking"
            " mode (true) for reproducible benchmark results,"
            " overriding the binary's async default. Set to"
            " false explicitly for async Tokio mode."
        ),
    ] = True

    buffer_size: typing.Annotated[
        typing.Optional[int],
        schema.name("Buffer Size"),
        schema.description(
            "Internal buffer size in bytes for message queues and"
            " shared memory."
        ),
        schema.min(1),
    ] = None

    warmup_iterations: typing.Annotated[
        typing.Optional[int],
        schema.name("Warmup Iterations"),
        schema.description(
            "Number of warmup messages before measurement starts."
        ),
        schema.min(0),
    ] = None

    percentiles: typing.Annotated[
        typing.Optional[typing.List[float]],
        schema.name("Percentiles"),
        schema.description(
            "Percentile values to compute, e.g. [50.0, 95.0, 99.0, 99.9]."
        ),
    ] = None

    one_way: typing.Annotated[
        typing.Optional[bool],
        schema.name("One-Way Test"),
        schema.description(
            "Run one-way latency tests. If neither one_way nor"
            " round_trip is set, both run by default."
        ),
    ] = None

    round_trip: typing.Annotated[
        typing.Optional[bool],
        schema.name("Round-Trip Test"),
        schema.description(
            "Run round-trip latency tests. If neither one_way nor"
            " round_trip is set, both run by default."
        ),
    ] = None

    send_delay: typing.Annotated[
        typing.Optional[str],
        schema.name("Send Delay"),
        schema.description(
            "Delay between sends, e.g. '10ms', '50us'. Useful for"
            " latency-focused testing under controlled load."
        ),
    ] = None

    server_affinity: typing.Annotated[
        typing.Optional[int],
        schema.name("Server CPU Affinity"),
        schema.description(
            "Pin the server (receiver) process to this CPU core."
        ),
        schema.min(0),
    ] = None

    client_affinity: typing.Annotated[
        typing.Optional[int],
        schema.name("Client CPU Affinity"),
        schema.description(
            "Pin the client (sender) process to this CPU core."
        ),
        schema.min(0),
    ] = None

    shm_direct: typing.Annotated[
        typing.Optional[bool],
        schema.name("SHM Direct Memory"),
        schema.description(
            "Use high-performance direct memory shared memory."
            " Auto-enables blocking mode. Unix only, 8KB max payload."
        ),
    ] = None

    continue_on_error: typing.Annotated[
        typing.Optional[bool],
        schema.name("Continue on Error"),
        schema.description(
            "Continue running remaining mechanisms if one fails."
        ),
    ] = None

    include_first_message: typing.Annotated[
        typing.Optional[bool],
        schema.name("Include First Message"),
        schema.description(
            "Include the first (canary) message in results instead"
            " of discarding it."
        ),
    ] = None

    host: typing.Annotated[
        typing.Optional[str],
        schema.name("TCP Host"),
        schema.description(
            "Host address for TCP socket tests. Default: 127.0.0.1."
        ),
    ] = None

    port: typing.Annotated[
        typing.Optional[int],
        schema.name("TCP Port"),
        schema.description("Port for TCP socket tests. Default: 8080."),
        schema.min(1),
    ] = None

    pmq_priority: typing.Annotated[
        typing.Optional[int],
        schema.name("PMQ Priority"),
        schema.description(
            "Message priority for POSIX Message Queues."
        ),
        schema.min(0),
    ] = None

    quiet: typing.Annotated[
        typing.Optional[bool],
        schema.name("Quiet Mode"),
        schema.description(
            "Silence informational console output."
        ),
    ] = None

    timeout: typing.Annotated[
        typing.Optional[int],
        schema.name("Timeout"),
        schema.description(
            "Maximum seconds to wait for the benchmark to"
            " complete before killing the process. Default:"
            " 3600 (1 hour). Increase for large benchmark"
            " matrices or long-duration tests."
        ),
        schema.min(1),
    ] = None

    extra_args: typing.Annotated[
        typing.Optional[typing.List[str]],
        schema.name("Extra Arguments"),
        schema.description(
            "Additional CLI arguments passed directly to the"
            " ipc-benchmark binary for advanced usage."
        ),
    ] = None


@dataclass
class InputParams:
    """Top-level input for the rusty-comms benchmark plugin.

    Contains a list of test run configurations. Each test run
    can specify its own mechanisms and parameters, allowing
    multiple benchmark profiles in a single invocation.
    """

    tests: typing.Annotated[
        typing.List[TestRunConfig],
        schema.name("Test Runs"),
        schema.description(
            "List of benchmark test configurations. Each entry"
            " specifies mechanisms and parameters for one run."
        ),
        schema.min(1),
    ]


# ---------------------------------------------------------------------------
# Output schema – mirrors the rusty-comms FinalBenchmarkResults JSON
# ---------------------------------------------------------------------------


@dataclass
class PercentileValue:
    """A single percentile measurement."""

    percentile: typing.Annotated[
        float,
        schema.name("Percentile"),
        schema.description("Percentile level, e.g. 95.0 for P95."),
    ]

    value_ns: typing.Annotated[
        int,
        schema.name("Value (ns)"),
        schema.description("Latency at this percentile in nanoseconds."),
    ]


@dataclass
class LatencyMetrics:
    """Statistical latency measurements from a benchmark run."""

    latency_type: typing.Annotated[
        str,
        schema.name("Latency Type"),
        schema.description("'OneWay' or 'RoundTrip'."),
    ]

    min_ns: typing.Annotated[
        int,
        schema.name("Min (ns)"),
        schema.description("Minimum observed latency in nanoseconds."),
    ]

    max_ns: typing.Annotated[
        int,
        schema.name("Max (ns)"),
        schema.description("Maximum observed latency in nanoseconds."),
    ]

    mean_ns: typing.Annotated[
        int,
        schema.name("Mean (ns)"),
        schema.description("Mean latency in nanoseconds."),
    ]

    median_ns: typing.Annotated[
        int,
        schema.name("Median (ns)"),
        schema.description("Median (P50) latency in nanoseconds."),
    ]

    std_dev_ns: typing.Annotated[
        int,
        schema.name("Std Dev (ns)"),
        schema.description(
            "Standard deviation of latency in nanoseconds."
        ),
    ]

    percentiles: typing.Annotated[
        typing.List[PercentileValue],
        schema.name("Percentiles"),
        schema.description("Requested percentile values."),
    ]

    total_samples: typing.Annotated[
        int,
        schema.name("Total Samples"),
        schema.description("Number of latency samples collected."),
    ]


@dataclass
class ThroughputMetrics:
    """Throughput measurements from a benchmark run."""

    messages_per_second: typing.Annotated[
        int,
        schema.name("Messages/sec"),
        schema.description("Message transmission rate."),
    ]

    bytes_per_second: typing.Annotated[
        int,
        schema.name("Bytes/sec"),
        schema.description("Data transmission rate in bytes per second."),
    ]

    total_messages: typing.Annotated[
        int,
        schema.name("Total Messages"),
        schema.description("Total messages transmitted."),
    ]

    total_bytes: typing.Annotated[
        int,
        schema.name("Total Bytes"),
        schema.description("Total bytes transmitted."),
    ]

    duration_ns: typing.Annotated[
        int,
        schema.name("Duration (ns)"),
        schema.description("Measurement duration in nanoseconds."),
    ]


@dataclass
class PerformanceMetrics:
    """Combined latency and throughput metrics for one test type."""

    throughput: typing.Annotated[
        ThroughputMetrics,
        schema.name("Throughput"),
        schema.description("Throughput measurements."),
    ]

    timestamp: typing.Annotated[
        str,
        schema.name("Timestamp"),
        schema.description("ISO-8601 timestamp of measurement."),
    ]

    latency: typing.Annotated[
        typing.Optional[LatencyMetrics],
        schema.name("Latency"),
        schema.description("Latency measurements (if collected)."),
    ] = None


@dataclass
class TestConfiguration:
    """The test configuration used for a benchmark run."""

    message_size: typing.Annotated[
        int,
        schema.name("Message Size"),
        schema.description("Payload size in bytes."),
    ]

    buffer_size: typing.Annotated[
        int,
        schema.name("Buffer Size"),
        schema.description("Internal buffer size in bytes."),
    ]

    concurrency: typing.Annotated[
        int,
        schema.name("Concurrency"),
        schema.description("Number of concurrent workers."),
    ]

    one_way_enabled: typing.Annotated[
        bool,
        schema.name("One-Way Enabled"),
        schema.description("Whether one-way tests were enabled."),
    ]

    round_trip_enabled: typing.Annotated[
        bool,
        schema.name("Round-Trip Enabled"),
        schema.description("Whether round-trip tests were enabled."),
    ]

    warmup_iterations: typing.Annotated[
        int,
        schema.name("Warmup Iterations"),
        schema.description("Warmup messages before measurement."),
    ]

    percentiles: typing.Annotated[
        typing.List[float],
        schema.name("Percentiles"),
        schema.description("Percentile levels computed."),
    ]

    msg_count: typing.Annotated[
        typing.Optional[int],
        schema.name("Message Count"),
        schema.description("Configured message count (None if duration)."),
    ] = None

    duration: typing.Annotated[
        typing.Optional[typing.Dict[str, int]],
        schema.name("Duration"),
        schema.description(
            "Configured duration as {secs, nanos} (None if count)."
        ),
    ] = None


@dataclass
class BenchmarkSummary:
    """Per-mechanism summary statistics."""

    total_messages_sent: typing.Annotated[
        int,
        schema.name("Total Messages Sent"),
        schema.description("Total messages sent across all test types."),
    ]

    total_bytes_transferred: typing.Annotated[
        int,
        schema.name("Total Bytes Transferred"),
        schema.description("Total bytes transferred."),
    ]

    average_throughput_mbps: typing.Annotated[
        float,
        schema.name("Average Throughput (MB/s)"),
        schema.description("Average throughput in megabytes per second."),
    ]

    peak_throughput_mbps: typing.Annotated[
        float,
        schema.name("Peak Throughput (MB/s)"),
        schema.description("Peak throughput in megabytes per second."),
    ]

    error_count: typing.Annotated[
        int,
        schema.name("Error Count"),
        schema.description("Number of errors during the benchmark."),
    ]

    average_latency_ns: typing.Annotated[
        typing.Optional[int],
        schema.name("Average Latency (ns)"),
        schema.description("Average latency in nanoseconds."),
    ] = None

    min_latency_ns: typing.Annotated[
        typing.Optional[int],
        schema.name("Min Latency (ns)"),
        schema.description("Minimum latency in nanoseconds."),
    ] = None

    max_latency_ns: typing.Annotated[
        typing.Optional[int],
        schema.name("Max Latency (ns)"),
        schema.description("Maximum latency in nanoseconds."),
    ] = None

    p95_latency_ns: typing.Annotated[
        typing.Optional[int],
        schema.name("P95 Latency (ns)"),
        schema.description("95th percentile latency in nanoseconds."),
    ] = None

    p99_latency_ns: typing.Annotated[
        typing.Optional[int],
        schema.name("P99 Latency (ns)"),
        schema.description("99th percentile latency in nanoseconds."),
    ] = None


@dataclass
class SystemInfo:
    """System information from the benchmark environment."""

    os: typing.Annotated[
        str,
        schema.name("OS"),
        schema.description("Operating system name."),
    ]

    architecture: typing.Annotated[
        str,
        schema.name("Architecture"),
        schema.description("CPU architecture, e.g. x86_64."),
    ]

    cpu_cores: typing.Annotated[
        int,
        schema.name("CPU Cores"),
        schema.description("Number of CPU cores."),
    ]

    memory_gb: typing.Annotated[
        float,
        schema.name("Memory (GB)"),
        schema.description("System memory in gigabytes."),
    ]

    rust_version: typing.Annotated[
        str,
        schema.name("Rust Version"),
        schema.description("Rust compiler version used to build."),
    ]

    benchmark_version: typing.Annotated[
        str,
        schema.name("Benchmark Version"),
        schema.description("rusty-comms version string."),
    ]


@dataclass
class BenchmarkResult:
    """Results for a single IPC mechanism benchmark run."""

    mechanism: typing.Annotated[
        str,
        schema.name("Mechanism"),
        schema.description(
            "IPC mechanism name, e.g. UnixDomainSocket,"
            " SharedMemory, TcpSocket, PosixMessageQueue."
        ),
    ]

    status: typing.Annotated[
        str,
        schema.name("Status"),
        schema.description(
            "Test outcome: 'Success' or 'Failure'."
        ),
    ]

    test_config: typing.Annotated[
        TestConfiguration,
        schema.name("Test Configuration"),
        schema.description("Configuration used for this test."),
    ]

    summary: typing.Annotated[
        BenchmarkSummary,
        schema.name("Summary"),
        schema.description("Summary statistics for this mechanism."),
    ]

    timestamp: typing.Annotated[
        str,
        schema.name("Timestamp"),
        schema.description("ISO-8601 timestamp of this test."),
    ]

    test_duration: typing.Annotated[
        typing.Dict[str, int],
        schema.name("Test Duration"),
        schema.description("Wall-clock duration as {secs, nanos}."),
    ]

    system_info: typing.Annotated[
        SystemInfo,
        schema.name("System Info"),
        schema.description("System info captured during this test."),
    ]

    failure_reason: typing.Annotated[
        typing.Optional[str],
        schema.name("Failure Reason"),
        schema.description(
            "Error description when status is 'Failure'."
            " None when the test succeeded."
        ),
    ] = None

    one_way_results: typing.Annotated[
        typing.Optional[PerformanceMetrics],
        schema.name("One-Way Results"),
        schema.description("One-way latency/throughput results."),
    ] = None

    round_trip_results: typing.Annotated[
        typing.Optional[PerformanceMetrics],
        schema.name("Round-Trip Results"),
        schema.description("Round-trip latency/throughput results."),
    ] = None

    input_blocking: typing.Annotated[
        typing.Optional[bool],
        schema.name("Input: Blocking"),
        schema.description(
            "Original blocking flag from the test input."
            " True = blocking, False = async, None = default."
        ),
    ] = None

    input_shm_direct: typing.Annotated[
        typing.Optional[bool],
        schema.name("Input: SHM Direct"),
        schema.description(
            "Original shm_direct flag from the test input."
        ),
    ] = None

    input_one_way: typing.Annotated[
        typing.Optional[bool],
        schema.name("Input: One-Way"),
        schema.description(
            "Original one_way flag from the test input."
        ),
    ] = None

    input_round_trip: typing.Annotated[
        typing.Optional[bool],
        schema.name("Input: Round-Trip"),
        schema.description(
            "Original round_trip flag from the test input."
        ),
    ] = None

    input_send_delay: typing.Annotated[
        typing.Optional[str],
        schema.name("Input: Send Delay"),
        schema.description(
            "Original send_delay value from the test input."
        ),
    ] = None

    input_concurrency: typing.Annotated[
        typing.Optional[int],
        schema.name("Input: Concurrency"),
        schema.description(
            "Original concurrency value from the test input."
        ),
    ] = None


@dataclass
class BenchmarkMetadata:
    """Top-level metadata about the benchmark run."""

    version: typing.Annotated[
        str,
        schema.name("Version"),
        schema.description("rusty-comms version."),
    ]

    timestamp: typing.Annotated[
        str,
        schema.name("Timestamp"),
        schema.description("ISO-8601 timestamp when run started."),
    ]

    total_tests: typing.Annotated[
        int,
        schema.name("Total Tests"),
        schema.description("Number of mechanism tests executed."),
    ]

    system_info: typing.Annotated[
        SystemInfo,
        schema.name("System Info"),
        schema.description("System information."),
    ]


@dataclass
class MechanismSummary:
    """Summary for a single mechanism in the overall summary."""

    mechanism: typing.Annotated[
        str,
        schema.name("Mechanism"),
        schema.description("IPC mechanism enum variant name."),
    ]

    average_throughput_mbps: typing.Annotated[
        float,
        schema.name("Average Throughput (MB/s)"),
        schema.description("Average throughput for this mechanism."),
    ]

    total_messages: typing.Annotated[
        int,
        schema.name("Total Messages"),
        schema.description("Total messages for this mechanism."),
    ]

    p95_latency_ns: typing.Annotated[
        typing.Optional[int],
        schema.name("P95 Latency (ns)"),
        schema.description("P95 latency in nanoseconds."),
    ] = None

    p99_latency_ns: typing.Annotated[
        typing.Optional[int],
        schema.name("P99 Latency (ns)"),
        schema.description("P99 latency in nanoseconds."),
    ] = None


@dataclass
class OverallSummary:
    """Overall summary across all tested mechanisms."""

    total_messages: typing.Annotated[
        int,
        schema.name("Total Messages"),
        schema.description("Sum of messages across all mechanisms."),
    ]

    total_bytes: typing.Annotated[
        int,
        schema.name("Total Bytes"),
        schema.description("Sum of bytes across all mechanisms."),
    ]

    total_errors: typing.Annotated[
        int,
        schema.name("Total Errors"),
        schema.description("Sum of errors across all mechanisms."),
    ]

    mechanisms: typing.Annotated[
        typing.Dict[str, MechanismSummary],
        schema.name("Mechanisms"),
        schema.description(
            "Per-mechanism summary keyed by display name."
        ),
    ]

    fastest_mechanism: typing.Annotated[
        typing.Optional[str],
        schema.name("Fastest Mechanism"),
        schema.description("Mechanism with highest throughput."),
    ] = None

    lowest_latency_mechanism: typing.Annotated[
        typing.Optional[str],
        schema.name("Lowest Latency Mechanism"),
        schema.description("Mechanism with lowest latency."),
    ] = None


# ---------------------------------------------------------------------------
# Top-level output dataclasses
# ---------------------------------------------------------------------------


@dataclass
class SuccessOutput:
    """Successful benchmark results returned to Arcaflow.

    Mirrors the ``FinalBenchmarkResults`` JSON produced by rusty-comms.
    """

    metadata: typing.Annotated[
        BenchmarkMetadata,
        schema.name("Metadata"),
        schema.description("Run metadata and system information."),
    ]

    results: typing.Annotated[
        typing.List[BenchmarkResult],
        schema.name("Results"),
        schema.description("Per-mechanism benchmark results."),
    ]

    summary: typing.Annotated[
        OverallSummary,
        schema.name("Overall Summary"),
        schema.description("Aggregated summary across mechanisms."),
    ]


@dataclass
class ErrorOutput:
    """Error output returned when the benchmark fails."""

    error: typing.Annotated[
        str,
        schema.name("Error"),
        schema.description("Error message describing the failure."),
    ]
