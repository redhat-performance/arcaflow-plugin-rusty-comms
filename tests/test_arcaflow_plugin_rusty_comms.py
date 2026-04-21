#!/usr/bin/env python3
"""Tests for the arcaflow-plugin-rusty-comms plugin.

Covers schema serialization, CLI argument building, JSON parsing,
and functional tests with a mocked subprocess.
"""

import json
import os
import unittest
from unittest import mock

from arcaflow_plugin_sdk import plugin
from arcaflow_plugin_sdk.schema import ConstraintException

import rusty_comms_plugin
from rusty_comms_schema import (
    BenchmarkMetadata,
    BenchmarkResult,
    BenchmarkSummary,
    ErrorOutput,
    InputParams,
    IterationAggregates,
    LatencyMetrics,
    Mechanism,
    TestIterationAggregate,
    MechanismSummary,
    MetricStatistics,
    OverallSummary,
    PercentileValue,
    PerformanceMetrics,
    SuccessOutput,
    SystemInfo,
    TestConfiguration,
    TestRunConfig,
    ThroughputMetrics,
)


# ---------------------------------------------------------------------------
# Sample data used across tests
# ---------------------------------------------------------------------------

SAMPLE_SYSTEM_INFO = SystemInfo(
    os="linux",
    architecture="x86_64",
    cpu_cores=8,
    memory_gb=16.0,
    rust_version="1.82.0",
    benchmark_version="0.1.0",
)

SAMPLE_PERCENTILES = [
    PercentileValue(percentile=50.0, value_ns=3100),
    PercentileValue(percentile=95.0, value_ns=5200),
    PercentileValue(percentile=99.0, value_ns=8500),
]

SAMPLE_LATENCY = LatencyMetrics(
    latency_type="OneWay",
    min_ns=1500,
    max_ns=45000,
    mean_ns=3201.0,
    median_ns=3100.0,
    std_dev_ns=1200.0,
    percentiles=SAMPLE_PERCENTILES,
    total_samples=10000,
)

SAMPLE_THROUGHPUT = ThroughputMetrics(
    messages_per_second=312500.0,
    bytes_per_second=320000000.0,
    total_messages=10000,
    total_bytes=10240000,
    duration_ns=32000000,
)

SAMPLE_PERFORMANCE = PerformanceMetrics(
    latency=SAMPLE_LATENCY,
    throughput=SAMPLE_THROUGHPUT,
    timestamp="2024-01-01T00:00:00Z",
)

SAMPLE_TEST_CONFIG = TestConfiguration(
    message_size=1024,
    buffer_size=8192,
    concurrency=1,
    msg_count=10000,
    duration=None,
    one_way_enabled=True,
    round_trip_enabled=True,
    warmup_iterations=1000,
    percentiles=[50.0, 95.0, 99.0],
)

SAMPLE_BENCHMARK_SUMMARY = BenchmarkSummary(
    total_messages_sent=10000,
    total_bytes_transferred=10240000,
    average_throughput_mbps=305.17,
    peak_throughput_mbps=310.0,
    error_count=0,
    average_latency_ns=3201.0,
    min_latency_ns=1500,
    max_latency_ns=45000,
    p95_latency_ns=5200,
    p99_latency_ns=8500,
)

SAMPLE_RESULT = BenchmarkResult(
    mechanism="UnixDomainSocket",
    status="Success",
    test_config=SAMPLE_TEST_CONFIG,
    summary=SAMPLE_BENCHMARK_SUMMARY,
    timestamp="2024-01-01T00:00:00Z",
    test_duration={"secs": 32, "nanos": 0},
    system_info=SAMPLE_SYSTEM_INFO,
    one_way_results=SAMPLE_PERFORMANCE,
    round_trip_results=None,
)

SAMPLE_MECHANISM_SUMMARY = MechanismSummary(
    mechanism="UnixDomainSocket",
    average_throughput_mbps=305.17,
    total_messages=10000,
    p95_latency_ns=5200,
    p99_latency_ns=8500,
)

SAMPLE_METADATA = BenchmarkMetadata(
    version="0.1.0",
    timestamp="2024-01-01T00:00:00Z",
    total_tests=1,
    system_info=SAMPLE_SYSTEM_INFO,
)

SAMPLE_OVERALL_SUMMARY = OverallSummary(
    total_messages=10000,
    total_bytes=10240000,
    total_errors=0,
    mechanisms={"Unix Domain Socket": SAMPLE_MECHANISM_SUMMARY},
    fastest_mechanism="Unix Domain Socket",
    lowest_latency_mechanism="Unix Domain Socket",
)

SAMPLE_SUCCESS_OUTPUT = SuccessOutput(
    metadata=SAMPLE_METADATA,
    results=[SAMPLE_RESULT],
    summary=SAMPLE_OVERALL_SUMMARY,
)


def _build_sample_json() -> dict:
    """Build a sample JSON dict matching rusty-comms output format."""
    return {
        "metadata": {
            "version": "0.1.0",
            "timestamp": "2024-01-01T00:00:00Z",
            "total_tests": 1,
            "system_info": {
                "os": "linux",
                "architecture": "x86_64",
                "cpu_cores": 8,
                "memory_gb": 16.0,
                "rust_version": "1.82.0",
                "benchmark_version": "0.1.0",
            },
        },
        "results": [
            {
                "mechanism": "UnixDomainSocket",
                "status": "Success",
                "test_config": {
                    "message_size": 1024,
                    "buffer_size": 8192,
                    "concurrency": 1,
                    "msg_count": 10000,
                    "duration": None,
                    "one_way_enabled": True,
                    "round_trip_enabled": True,
                    "warmup_iterations": 1000,
                    "percentiles": [50.0, 95.0, 99.0],
                },
                "one_way_results": {
                    "latency": {
                        "latency_type": "OneWay",
                        "min_ns": 1500,
                        "max_ns": 45000,
                        "mean_ns": 3200.5,
                        "median_ns": 3100.0,
                        "std_dev_ns": 1200.0,
                        "percentiles": [
                            {"percentile": 50.0, "value_ns": 3100},
                            {"percentile": 95.0, "value_ns": 5200},
                            {"percentile": 99.0, "value_ns": 8500},
                        ],
                        "total_samples": 10000,
                        "histogram_data": [100, 200, 300],
                    },
                    "throughput": {
                        "messages_per_second": 312500.0,
                        "bytes_per_second": 320000000.0,
                        "total_messages": 10000,
                        "total_bytes": 10240000,
                        "duration_ns": 32000000,
                    },
                    "timestamp": "2024-01-01T00:00:00Z",
                },
                "round_trip_results": None,
                "summary": {
                    "total_messages_sent": 10000,
                    "total_bytes_transferred": 10240000,
                    "average_throughput_mbps": 305.17,
                    "peak_throughput_mbps": 310.0,
                    "error_count": 0,
                    "average_latency_ns": 3200.5,
                    "min_latency_ns": 1500,
                    "max_latency_ns": 45000,
                    "p95_latency_ns": 5200,
                    "p99_latency_ns": 8500,
                },
                "timestamp": "2024-01-01T00:00:00Z",
                "test_duration": {"secs": 32, "nanos": 0},
                "system_info": {
                    "os": "linux",
                    "architecture": "x86_64",
                    "cpu_cores": 8,
                    "memory_gb": 16.0,
                    "rust_version": "1.82.0",
                    "benchmark_version": "0.1.0",
                },
            }
        ],
        "summary": {
            "total_messages": 10000,
            "total_bytes": 10240000,
            "total_errors": 0,
            "mechanisms": {
                "Unix Domain Socket": {
                    "mechanism": "UnixDomainSocket",
                    "average_throughput_mbps": 305.17,
                    "total_messages": 10000,
                    "p95_latency_ns": 5200,
                    "p99_latency_ns": 8500,
                }
            },
            "fastest_mechanism": "Unix Domain Socket",
            "lowest_latency_mechanism": "Unix Domain Socket",
        },
    }


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


class SerializationTest(unittest.TestCase):
    """Verify all dataclasses can round-trip through SDK serialization."""

    @staticmethod
    def test_input_params_serialization():
        """InputParams with a single test should serialize correctly."""
        plugin.test_object_serialization(
            InputParams(
                tests=[TestRunConfig(mechanisms=[Mechanism.uds])]
            )
        )

    @staticmethod
    def test_input_params_multiple_tests_serialization():
        """InputParams with multiple tests should serialize correctly."""
        plugin.test_object_serialization(
            InputParams(
                tests=[
                    TestRunConfig(
                        mechanisms=[Mechanism.uds, Mechanism.tcp],
                        message_size=4096,
                        msg_count=50000,
                    ),
                    TestRunConfig(
                        mechanisms=[Mechanism.pmq],
                        message_size=1024,
                        duration="30s",
                        blocking=True,
                    ),
                ]
            )
        )

    @staticmethod
    def test_test_run_config_all_fields_serialization():
        """TestRunConfig with all fields should serialize correctly."""
        plugin.test_object_serialization(
            TestRunConfig(
                mechanisms=[Mechanism.uds, Mechanism.tcp],
                message_size=4096,
                msg_count=50000,
                duration="30s",
                concurrency=4,
                blocking=True,
                buffer_size=65536,
                warmup_iterations=1000,
                percentiles=[50.0, 95.0, 99.0, 99.9],
                one_way=True,
                round_trip=False,
                send_delay="10ms",
                server_affinity=0,
                client_affinity=1,
                shm_direct=False,
                continue_on_error=True,
                include_first_message=False,
                host="127.0.0.1",
                port=9090,
                pmq_priority=1,
                quiet=False,
                extra_args=["--verbose"],
            )
        )

    @staticmethod
    def test_success_output_serialization():
        """SuccessOutput should serialize and deserialize correctly."""
        plugin.test_object_serialization(SAMPLE_SUCCESS_OUTPUT)

    @staticmethod
    def test_error_output_serialization():
        """ErrorOutput should serialize and deserialize correctly."""
        plugin.test_object_serialization(
            ErrorOutput(error="Something went wrong")
        )

    @staticmethod
    def test_percentile_value_serialization():
        """PercentileValue should serialize correctly."""
        plugin.test_object_serialization(
            PercentileValue(percentile=99.0, value_ns=8500)
        )

    @staticmethod
    def test_system_info_serialization():
        """SystemInfo should serialize correctly."""
        plugin.test_object_serialization(SAMPLE_SYSTEM_INFO)

    @staticmethod
    def test_latency_metrics_serialization():
        """LatencyMetrics should serialize correctly."""
        plugin.test_object_serialization(SAMPLE_LATENCY)

    @staticmethod
    def test_throughput_metrics_serialization():
        """ThroughputMetrics should serialize correctly."""
        plugin.test_object_serialization(SAMPLE_THROUGHPUT)


class CLIArgsTest(unittest.TestCase):
    """Verify CLI argument construction from TestRunConfig."""

    def test_minimal_args(self):
        """Minimal input should produce mechanism and output file args."""
        config = TestRunConfig(mechanisms=[Mechanism.uds])
        args = rusty_comms_plugin._build_cli_args(
            config, "/tmp/out.json"
        )
        self.assertIn("-m", args)
        self.assertIn("uds", args)
        self.assertIn("--output-file", args)
        self.assertIn("/tmp/out.json", args)

    def test_blocking_default_not_passed(self):
        """Unset blocking should not inject --blocking flag."""
        config = TestRunConfig(mechanisms=[Mechanism.uds])
        args = rusty_comms_plugin._build_cli_args(
            config, "/tmp/out.json"
        )
        self.assertNotIn("--blocking", args)

    def test_blocking_explicit_true(self):
        """Setting blocking to True should pass --blocking."""
        config = TestRunConfig(
            mechanisms=[Mechanism.uds], blocking=True
        )
        args = rusty_comms_plugin._build_cli_args(
            config, "/tmp/out.json"
        )
        self.assertIn("--blocking", args)

    def test_blocking_explicit_false(self):
        """Setting blocking to False should disable it."""
        config = TestRunConfig(
            mechanisms=[Mechanism.uds], blocking=False
        )
        args = rusty_comms_plugin._build_cli_args(
            config, "/tmp/out.json"
        )
        self.assertNotIn("--blocking", args)

    def test_all_mechanisms(self):
        """The 'all' mechanism should pass through correctly."""
        config = TestRunConfig(mechanisms=[Mechanism.all])
        args = rusty_comms_plugin._build_cli_args(
            config, "/tmp/out.json"
        )
        self.assertIn("all", args)

    def test_multiple_mechanisms(self):
        """Multiple mechanisms should appear in order."""
        config = TestRunConfig(
            mechanisms=[Mechanism.uds, Mechanism.shm, Mechanism.tcp]
        )
        args = rusty_comms_plugin._build_cli_args(
            config, "/tmp/out.json"
        )
        m_idx = args.index("-m")
        self.assertEqual(args[m_idx + 1], "uds")
        self.assertEqual(args[m_idx + 2], "shm")
        self.assertEqual(args[m_idx + 3], "tcp")

    def test_optional_params_included(self):
        """Optional params should appear only when set."""
        config = TestRunConfig(
            mechanisms=[Mechanism.tcp],
            message_size=4096,
            msg_count=50000,
            blocking=True,
            continue_on_error=True,
        )
        args = rusty_comms_plugin._build_cli_args(
            config, "/tmp/out.json"
        )
        self.assertIn("-s", args)
        self.assertIn("4096", args)
        self.assertIn("-i", args)
        self.assertIn("50000", args)
        self.assertIn("--blocking", args)
        self.assertIn("--continue-on-error", args)

    def test_percentiles_formatting(self):
        """Percentiles should each appear as separate arguments."""
        config = TestRunConfig(
            mechanisms=[Mechanism.uds],
            percentiles=[50.0, 95.0, 99.9],
        )
        args = rusty_comms_plugin._build_cli_args(
            config, "/tmp/out.json"
        )
        self.assertIn("--percentiles", args)
        self.assertIn("50.0", args)
        self.assertIn("95.0", args)
        self.assertIn("99.9", args)

    def test_extra_args_appended(self):
        """Extra args should be appended at the end."""
        config = TestRunConfig(
            mechanisms=[Mechanism.uds],
            extra_args=["--verbose", "--log-file", "/tmp/bench.log"],
        )
        args = rusty_comms_plugin._build_cli_args(
            config, "/tmp/out.json"
        )
        self.assertIn("--verbose", args)
        self.assertIn("--log-file", args)
        self.assertIn("/tmp/bench.log", args)

    def test_false_booleans_not_included(self):
        """Boolean params set to False should not appear as flags."""
        config = TestRunConfig(
            mechanisms=[Mechanism.uds],
            blocking=False,
            shm_direct=False,
        )
        args = rusty_comms_plugin._build_cli_args(
            config, "/tmp/out.json"
        )
        self.assertNotIn("--blocking", args)
        self.assertNotIn("--shm-direct", args)

    def test_empty_duration_not_passed(self):
        """Empty duration string should not be passed to CLI."""
        config = TestRunConfig(
            mechanisms=[Mechanism.uds],
            duration="",
        )
        args = rusty_comms_plugin._build_cli_args(
            config, "/tmp/out.json"
        )
        self.assertNotIn("-d", args)


class JSONParsingTest(unittest.TestCase):
    """Verify JSON output parsing into dataclasses."""

    def test_parse_complete_json(self):
        """A complete sample JSON should parse without errors."""
        raw = _build_sample_json()
        result = rusty_comms_plugin._parse_json_output(raw)
        self.assertIsInstance(result, SuccessOutput)
        self.assertEqual(result.metadata.version, "0.1.0")
        self.assertEqual(len(result.results), 1)
        self.assertEqual(
            result.results[0].mechanism, "UnixDomainSocket"
        )

    def test_parse_latency_metrics(self):
        """Latency metrics should be correctly extracted."""
        raw = _build_sample_json()
        result = rusty_comms_plugin._parse_json_output(raw)
        ow = result.results[0].one_way_results
        self.assertIsNotNone(ow)
        self.assertIsNotNone(ow.latency)
        self.assertEqual(ow.latency.min_ns, 1500)
        self.assertEqual(ow.latency.max_ns, 45000)
        self.assertEqual(len(ow.latency.percentiles), 3)

    def test_parse_null_round_trip(self):
        """Null round-trip results should parse as None."""
        raw = _build_sample_json()
        result = rusty_comms_plugin._parse_json_output(raw)
        self.assertIsNone(result.results[0].round_trip_results)

    def test_parse_overall_summary(self):
        """Overall summary with mechanism map should parse."""
        raw = _build_sample_json()
        result = rusty_comms_plugin._parse_json_output(raw)
        self.assertEqual(result.summary.total_messages, 10000)
        self.assertIn(
            "Unix Domain Socket", result.summary.mechanisms
        )
        mech = result.summary.mechanisms["Unix Domain Socket"]
        self.assertEqual(mech.total_messages, 10000)

    def test_parse_missing_key_raises(self):
        """Missing required keys should raise ConstraintException."""
        raw = _build_sample_json()
        del raw["metadata"]["version"]
        with self.assertRaises(ConstraintException):
            rusty_comms_plugin._parse_json_output(raw)

    def test_float_values_preserved(self):
        """Float values in float fields should pass through as-is."""
        raw = _build_sample_json()
        raw["results"][0]["one_way_results"]["latency"][
            "mean_ns"
        ] = 9999.7
        result = rusty_comms_plugin._parse_json_output(raw)
        ow = result.results[0].one_way_results
        self.assertAlmostEqual(ow.latency.mean_ns, 9999.7)
        self.assertIsInstance(ow.latency.mean_ns, float)

    def test_unknown_keys_stripped(self):
        """Extra keys not in the schema should be silently ignored."""
        raw = _build_sample_json()
        self.assertIn(
            "histogram_data",
            raw["results"][0]["one_way_results"]["latency"],
        )
        result = rusty_comms_plugin._parse_json_output(raw)
        self.assertIsInstance(result, SuccessOutput)

    def test_parse_with_extra_top_level_key(self):
        """Unknown top-level keys should not cause errors."""
        raw = _build_sample_json()
        raw["debug_info"] = {"internal": True}
        result = rusty_comms_plugin._parse_json_output(raw)
        self.assertIsInstance(result, SuccessOutput)

    def test_parse_failure_status_dict(self):
        """Rust {'Failure': 'reason'} status should be normalized."""
        raw = _build_sample_json()
        raw["results"][0]["status"] = {"Failure": "connection refused"}
        result = rusty_comms_plugin._parse_json_output(raw)
        self.assertEqual(result.results[0].status, "Failure")
        self.assertEqual(
            result.results[0].failure_reason, "connection refused"
        )

    def test_parse_success_status_has_no_failure_reason(self):
        """Successful status should have failure_reason=None."""
        raw = _build_sample_json()
        result = rusty_comms_plugin._parse_json_output(raw)
        self.assertEqual(result.results[0].status, "Success")
        self.assertIsNone(result.results[0].failure_reason)


class MergeOutputsTest(unittest.TestCase):
    """Verify _merge_outputs aggregation of duplicate mechanisms."""

    def _make_output(
        self, mechanism_name, throughput, messages, p95, p99,
    ):
        """Build a minimal SuccessOutput for merge testing.

        Args:
            mechanism_name: Display name key for the mechanism.
            throughput: Average throughput in MB/s.
            messages: Total messages for this mechanism.
            p95: P95 latency in nanoseconds (or None).
            p99: P99 latency in nanoseconds (or None).

        Returns:
            A SuccessOutput with one mechanism in its summary.
        """
        return SuccessOutput(
            metadata=SAMPLE_METADATA,
            results=[SAMPLE_RESULT],
            summary=OverallSummary(
                total_messages=messages,
                total_bytes=messages * 1024,
                total_errors=0,
                mechanisms={
                    mechanism_name: MechanismSummary(
                        mechanism="UnixDomainSocket",
                        average_throughput_mbps=throughput,
                        total_messages=messages,
                        p95_latency_ns=p95,
                        p99_latency_ns=p99,
                    )
                },
                fastest_mechanism=mechanism_name,
                lowest_latency_mechanism=mechanism_name,
            ),
        )

    def test_duplicate_mechanisms_aggregated(self):
        """Same mechanism from two runs should be merged, not overwritten."""
        out1 = self._make_output("UDS", 300.0, 10000, 5000, 8000)
        out2 = self._make_output("UDS", 250.0, 20000, 4000, 7000)
        merged = rusty_comms_plugin._merge_outputs([out1, out2])

        mech = merged.summary.mechanisms["UDS"]
        self.assertEqual(mech.total_messages, 30000)
        self.assertAlmostEqual(
            mech.average_throughput_mbps, 300.0,
        )
        self.assertEqual(mech.p95_latency_ns, 4000)
        self.assertEqual(mech.p99_latency_ns, 7000)

    def test_distinct_mechanisms_both_kept(self):
        """Different mechanisms should both appear in the merged output."""
        out1 = self._make_output("UDS", 300.0, 10000, 5000, 8000)
        out2 = self._make_output("TCP", 200.0, 10000, 6000, 9000)
        merged = rusty_comms_plugin._merge_outputs([out1, out2])

        self.assertIn("UDS", merged.summary.mechanisms)
        self.assertIn("TCP", merged.summary.mechanisms)
        self.assertEqual(merged.summary.fastest_mechanism, "UDS")
        self.assertEqual(
            merged.summary.lowest_latency_mechanism, "UDS",
        )

    def test_fastest_derived_from_merged_data(self):
        """Fastest mechanism should reflect aggregated throughput."""
        out1 = self._make_output("UDS", 100.0, 10000, 5000, 8000)
        out2 = self._make_output("TCP", 200.0, 10000, 6000, 9000)
        out3 = self._make_output("UDS", 300.0, 10000, 4500, 7500)
        merged = rusty_comms_plugin._merge_outputs(
            [out1, out2, out3]
        )

        self.assertEqual(merged.summary.fastest_mechanism, "UDS")
        uds = merged.summary.mechanisms["UDS"]
        self.assertAlmostEqual(
            uds.average_throughput_mbps, 300.0,
        )

    def test_lowest_latency_with_none_values(self):
        """None latencies should be ignored when finding the minimum."""
        out1 = self._make_output("UDS", 300.0, 10000, None, None)
        out2 = self._make_output("UDS", 250.0, 10000, 5000, 8000)
        merged = rusty_comms_plugin._merge_outputs([out1, out2])

        mech = merged.summary.mechanisms["UDS"]
        self.assertEqual(mech.p95_latency_ns, 5000)
        self.assertEqual(mech.p99_latency_ns, 8000)


class IterationTest(unittest.TestCase):
    """Tests for iteration and statistical aggregation."""

    def test_iterations_default_is_one(self):
        """TestRunConfig iterations should default to 1."""
        config = TestRunConfig(mechanisms=[Mechanism.uds])
        self.assertEqual(config.iterations, 1)

    def test_iterations_serialization(self):
        """TestRunConfig with iterations should serialize."""
        plugin.test_object_serialization(
            TestRunConfig(
                mechanisms=[Mechanism.uds], iterations=3,
            )
        )

    def test_iteration_aggregates_serialization(self):
        """SuccessOutput with iteration_aggregates should serialize."""
        agg = IterationAggregates(
            tests=[
                TestIterationAggregate(
                    mechanism="UnixDomainSocket",
                    message_size=1024,
                    direction="one_way",
                    iterations_completed=3,
                    throughput_mbps=MetricStatistics(
                        mean=300.0,
                        stddev=10.0,
                        min_value=290.0,
                        max_value=310.0,
                        sample_count=3,
                    ),
                )
            ]
        )
        output = SuccessOutput(
            metadata=SAMPLE_METADATA,
            results=[SAMPLE_RESULT],
            summary=SAMPLE_OVERALL_SUMMARY,
            iteration_aggregates=agg,
        )
        plugin.test_object_serialization(output)

    def test_compute_stats_single_value(self):
        """Single value should yield stddev=0."""
        stats = rusty_comms_plugin._compute_stats([100.0])
        self.assertEqual(stats.mean, 100.0)
        self.assertEqual(stats.stddev, 0.0)
        self.assertEqual(stats.min_value, 100.0)
        self.assertEqual(stats.max_value, 100.0)
        self.assertEqual(stats.sample_count, 1)

    def test_compute_stats_multiple_values(self):
        """Multiple values should compute correct statistics."""
        stats = rusty_comms_plugin._compute_stats(
            [100.0, 200.0, 300.0]
        )
        self.assertAlmostEqual(stats.mean, 200.0)
        self.assertAlmostEqual(stats.stddev, 100.0)
        self.assertEqual(stats.min_value, 100.0)
        self.assertEqual(stats.max_value, 300.0)
        self.assertEqual(stats.sample_count, 3)

    def test_compute_stats_identical_values(self):
        """Identical values should yield stddev=0."""
        stats = rusty_comms_plugin._compute_stats(
            [42.0, 42.0, 42.0]
        )
        self.assertEqual(stats.mean, 42.0)
        self.assertEqual(stats.stddev, 0.0)

    def _make_output_with_summary(self, throughput, latency):
        """Build a SuccessOutput with specific summary metrics.

        Args:
            throughput: Average throughput in MB/s.
            latency: Average latency in ns (or None).

        Returns:
            A SuccessOutput with one UDS mechanism result.
        """
        summary = BenchmarkSummary(
            total_messages_sent=10000,
            total_bytes_transferred=10240000,
            average_throughput_mbps=throughput,
            peak_throughput_mbps=throughput + 10,
            error_count=0,
            average_latency_ns=(
                float(latency) if latency is not None
                else None
            ),
            p95_latency_ns=5200 if latency else None,
            p99_latency_ns=8500 if latency else None,
        )
        result = BenchmarkResult(
            mechanism="UnixDomainSocket",
            status="Success",
            test_config=SAMPLE_TEST_CONFIG,
            summary=summary,
            timestamp="2024-01-01T00:00:00Z",
            test_duration={"secs": 32, "nanos": 0},
            system_info=SAMPLE_SYSTEM_INFO,
        )
        return SuccessOutput(
            metadata=SAMPLE_METADATA,
            results=[result],
            summary=SAMPLE_OVERALL_SUMMARY,
        )

    def _find_test_agg(
        self, agg, mechanism, msg_size=1024,
        direction="one_way",
    ):
        """Find a TestIterationAggregate by its identity fields."""
        for t in agg.tests:
            if (t.mechanism == mechanism
                    and t.message_size == msg_size
                    and t.direction == direction):
                return t
        self.fail(
            f"No aggregate for {mechanism}/"
            f"{msg_size}/{direction}"
        )

    def test_iteration_aggregates_computed(self):
        """Aggregates should reflect statistics across outputs."""
        outputs = [
            self._make_output_with_summary(300.0, 3200),
            self._make_output_with_summary(310.0, 3100),
            self._make_output_with_summary(290.0, 3300),
        ]
        agg = rusty_comms_plugin._compute_iteration_aggregates(
            outputs
        )
        self.assertEqual(len(agg.tests), 1)
        t = self._find_test_agg(agg, "UnixDomainSocket")
        self.assertEqual(t.iterations_completed, 3)
        self.assertAlmostEqual(
            t.throughput_mbps.mean, 300.0,
        )
        self.assertEqual(
            t.throughput_mbps.min_value, 290.0,
        )
        self.assertEqual(
            t.throughput_mbps.max_value, 310.0,
        )
        self.assertIsNotNone(t.mean_latency_ns)
        self.assertIsNotNone(t.p95_latency_ns)
        self.assertIsNotNone(t.p99_latency_ns)

    def test_aggregates_without_latency(self):
        """Tests without latency should have None aggregates."""
        outputs = [
            self._make_output_with_summary(300.0, None),
            self._make_output_with_summary(310.0, None),
        ]
        agg = rusty_comms_plugin._compute_iteration_aggregates(
            outputs
        )
        t = self._find_test_agg(agg, "UnixDomainSocket")
        self.assertIsNotNone(t.throughput_mbps)
        self.assertIsNone(t.mean_latency_ns)
        self.assertIsNone(t.p95_latency_ns)
        self.assertIsNone(t.p99_latency_ns)

    def test_single_iteration_aggregates(self):
        """Single iteration should produce valid aggregates."""
        outputs = [
            self._make_output_with_summary(300.0, 3200),
        ]
        agg = rusty_comms_plugin._compute_iteration_aggregates(
            outputs
        )
        t = self._find_test_agg(agg, "UnixDomainSocket")
        self.assertEqual(t.iterations_completed, 1)
        self.assertEqual(t.throughput_mbps.stddev, 0.0)
        self.assertEqual(
            t.throughput_mbps.min_value,
            t.throughput_mbps.max_value,
        )


class FunctionalTest(unittest.TestCase):
    """Functional tests with mocked subprocess execution."""

    def _make_popen_mock(
        self, returncode=0, stdout="", stderr=""
    ):
        """Create a mock Popen instance with communicate().

        Args:
            returncode: Exit code returned by the process.
            stdout: Standard output text.
            stderr: Standard error text.

        Returns:
            A configured Mock that behaves like Popen.
        """
        proc = mock.Mock()
        proc.communicate.return_value = (stdout, stderr)
        proc.returncode = returncode
        proc.poll.return_value = returncode
        proc.pid = 12345
        return proc

    @mock.patch("rusty_comms_plugin._find_binary")
    @mock.patch("rusty_comms_plugin.subprocess.Popen")
    def test_success_run(self, mock_popen, mock_find):
        """Successful benchmark run should return SuccessOutput."""
        mock_find.return_value = "/usr/local/bin/ipc-benchmark"

        sample_json = _build_sample_json()

        def side_effect(cmd, **kwargs):
            for i, arg in enumerate(cmd):
                if arg == "--output-file" and i + 1 < len(cmd):
                    output_path = cmd[i + 1]
                    os.makedirs(
                        os.path.dirname(output_path),
                        exist_ok=True,
                    )
                    with open(output_path, "w") as f:
                        json.dump(sample_json, f)
                    break
            return self._make_popen_mock()

        mock_popen.side_effect = side_effect

        params = InputParams(
            tests=[TestRunConfig(
                mechanisms=[Mechanism.uds], iterations=1,
            )]
        )
        output_id, output_data = rusty_comms_plugin.run_benchmark(
            params=params, run_id="test_run"
        )

        self.assertEqual(output_id, "success")
        self.assertIsInstance(output_data, SuccessOutput)
        self.assertEqual(output_data.metadata.version, "0.1.0")

    @mock.patch("rusty_comms_plugin._find_binary")
    @mock.patch("rusty_comms_plugin.subprocess.Popen")
    def test_multiple_tests_run(self, mock_popen, mock_find):
        """Multiple test runs should merge results."""
        mock_find.return_value = "/usr/local/bin/ipc-benchmark"

        sample_json = _build_sample_json()

        def side_effect(cmd, **kwargs):
            for i, arg in enumerate(cmd):
                if arg == "--output-file" and i + 1 < len(cmd):
                    output_path = cmd[i + 1]
                    os.makedirs(
                        os.path.dirname(output_path),
                        exist_ok=True,
                    )
                    with open(output_path, "w") as f:
                        json.dump(sample_json, f)
                    break
            return self._make_popen_mock()

        mock_popen.side_effect = side_effect

        params = InputParams(
            tests=[
                TestRunConfig(
                    mechanisms=[Mechanism.uds], iterations=1,
                ),
                TestRunConfig(
                    mechanisms=[Mechanism.tcp], iterations=1,
                ),
            ]
        )
        output_id, output_data = rusty_comms_plugin.run_benchmark(
            params=params, run_id="test_run"
        )

        self.assertEqual(output_id, "success")
        self.assertIsInstance(output_data, SuccessOutput)
        self.assertEqual(len(output_data.results), 2)
        self.assertEqual(mock_popen.call_count, 2)

    @mock.patch("rusty_comms_plugin._find_binary")
    @mock.patch("rusty_comms_plugin.subprocess.Popen")
    def test_nonzero_exit_returns_error(
        self, mock_popen, mock_find
    ):
        """Non-zero exit code should return ErrorOutput."""
        mock_find.return_value = "/usr/local/bin/ipc-benchmark"

        mock_popen.return_value = self._make_popen_mock(
            returncode=1,
            stderr="benchmark failed: permission denied",
        )

        params = InputParams(
            tests=[TestRunConfig(
                mechanisms=[Mechanism.uds], iterations=1,
            )]
        )
        output_id, output_data = rusty_comms_plugin.run_benchmark(
            params=params, run_id="test_run"
        )

        self.assertEqual(output_id, "error")
        self.assertIsInstance(output_data, ErrorOutput)
        self.assertIn("permission denied", output_data.error)

    @mock.patch(
        "rusty_comms_plugin._find_binary",
        side_effect=FileNotFoundError("not found"),
    )
    def test_missing_binary_returns_error(self, mock_find):
        """Missing binary should return ErrorOutput."""
        params = InputParams(
            tests=[TestRunConfig(
                mechanisms=[Mechanism.uds], iterations=1,
            )]
        )
        output_id, output_data = rusty_comms_plugin.run_benchmark(
            params=params, run_id="test_run"
        )

        self.assertEqual(output_id, "error")
        self.assertIsInstance(output_data, ErrorOutput)
        self.assertIn("not found", output_data.error)

    @mock.patch("rusty_comms_plugin._find_binary")
    @mock.patch(
        "rusty_comms_plugin.subprocess.Popen",
        side_effect=OSError("exec format error"),
    )
    def test_os_error_returns_error(
        self, mock_popen, mock_find
    ):
        """OSError during execution should return ErrorOutput."""
        mock_find.return_value = "/usr/local/bin/ipc-benchmark"

        params = InputParams(
            tests=[TestRunConfig(
                mechanisms=[Mechanism.tcp], iterations=1,
            )]
        )
        output_id, output_data = rusty_comms_plugin.run_benchmark(
            params=params, run_id="test_run"
        )

        self.assertEqual(output_id, "error")
        self.assertIsInstance(output_data, ErrorOutput)
        self.assertIn("exec format error", output_data.error)

    @mock.patch("rusty_comms_plugin._find_binary")
    @mock.patch("rusty_comms_plugin.subprocess.Popen")
    def test_iterations_runs_n_times(
        self, mock_popen, mock_find
    ):
        """Each test config should run iterations times."""
        mock_find.return_value = "/usr/local/bin/ipc-benchmark"

        sample_json = _build_sample_json()

        def side_effect(cmd, **kwargs):
            for i, arg in enumerate(cmd):
                if arg == "--output-file" and i + 1 < len(cmd):
                    output_path = cmd[i + 1]
                    os.makedirs(
                        os.path.dirname(output_path),
                        exist_ok=True,
                    )
                    with open(output_path, "w") as f:
                        json.dump(sample_json, f)
                    break
            return self._make_popen_mock()

        mock_popen.side_effect = side_effect

        params = InputParams(
            tests=[TestRunConfig(
                mechanisms=[Mechanism.uds], iterations=3,
            )]
        )
        output_id, output_data = rusty_comms_plugin.run_benchmark(
            params=params, run_id="test_run"
        )

        self.assertEqual(output_id, "success")
        self.assertEqual(mock_popen.call_count, 3)
        self.assertEqual(len(output_data.results), 3)
        self.assertIsNotNone(
            output_data.iteration_aggregates
        )
        self.assertGreaterEqual(
            len(output_data.iteration_aggregates.tests), 1
        )
        uds_aggs = [
            t for t in
            output_data.iteration_aggregates.tests
            if t.mechanism == "UnixDomainSocket"
        ]
        self.assertEqual(len(uds_aggs), 1)
        self.assertEqual(
            uds_aggs[0].iterations_completed, 3
        )


if __name__ == "__main__":
    unittest.main()
