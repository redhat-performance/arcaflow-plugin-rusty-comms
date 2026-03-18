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

import rusty_comms_plugin
from rusty_comms_schema import (
    BenchmarkMetadata,
    BenchmarkResult,
    BenchmarkSummary,
    ErrorOutput,
    InputParams,
    LatencyMetrics,
    Mechanism,
    MechanismSummary,
    OverallSummary,
    PercentileValue,
    PerformanceMetrics,
    SuccessOutput,
    SystemInfo,
    TestConfiguration,
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
    mean_ns=3200.5,
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
    average_latency_ns=3200.5,
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
        """InputParams should serialize and deserialize correctly."""
        plugin.test_object_serialization(
            InputParams(mechanisms=[Mechanism.uds])
        )

    @staticmethod
    def test_input_params_all_fields_serialization():
        """InputParams with all fields should serialize correctly."""
        plugin.test_object_serialization(
            InputParams(
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
    """Verify CLI argument construction from InputParams."""

    def test_minimal_args(self):
        """Minimal input should produce mechanism and output file args."""
        params = InputParams(mechanisms=[Mechanism.uds])
        args = rusty_comms_plugin._build_cli_args(
            params, "/tmp/out.json"
        )
        self.assertIn("-m", args)
        self.assertIn("uds", args)
        self.assertIn("--output-file", args)
        self.assertIn("/tmp/out.json", args)

    def test_all_mechanisms(self):
        """The 'all' mechanism should pass through correctly."""
        params = InputParams(mechanisms=[Mechanism.all])
        args = rusty_comms_plugin._build_cli_args(
            params, "/tmp/out.json"
        )
        self.assertIn("all", args)

    def test_multiple_mechanisms(self):
        """Multiple mechanisms should appear in order."""
        params = InputParams(
            mechanisms=[Mechanism.uds, Mechanism.shm, Mechanism.tcp]
        )
        args = rusty_comms_plugin._build_cli_args(
            params, "/tmp/out.json"
        )
        m_idx = args.index("-m")
        self.assertEqual(args[m_idx + 1], "uds")
        self.assertEqual(args[m_idx + 2], "shm")
        self.assertEqual(args[m_idx + 3], "tcp")

    def test_optional_params_included(self):
        """Optional params should appear only when set."""
        params = InputParams(
            mechanisms=[Mechanism.tcp],
            message_size=4096,
            msg_count=50000,
            blocking=True,
            continue_on_error=True,
        )
        args = rusty_comms_plugin._build_cli_args(
            params, "/tmp/out.json"
        )
        self.assertIn("-s", args)
        self.assertIn("4096", args)
        self.assertIn("-i", args)
        self.assertIn("50000", args)
        self.assertIn("--blocking", args)
        self.assertIn("--continue-on-error", args)

    def test_percentiles_formatting(self):
        """Percentiles should each appear as separate arguments."""
        params = InputParams(
            mechanisms=[Mechanism.uds],
            percentiles=[50.0, 95.0, 99.9],
        )
        args = rusty_comms_plugin._build_cli_args(
            params, "/tmp/out.json"
        )
        self.assertIn("--percentiles", args)
        self.assertIn("50.0", args)
        self.assertIn("95.0", args)
        self.assertIn("99.9", args)

    def test_extra_args_appended(self):
        """Extra args should be appended at the end."""
        params = InputParams(
            mechanisms=[Mechanism.uds],
            extra_args=["--verbose", "--log-file", "/tmp/bench.log"],
        )
        args = rusty_comms_plugin._build_cli_args(
            params, "/tmp/out.json"
        )
        self.assertIn("--verbose", args)
        self.assertIn("--log-file", args)
        self.assertIn("/tmp/bench.log", args)

    def test_false_booleans_not_included(self):
        """Boolean params set to False should not appear as flags."""
        params = InputParams(
            mechanisms=[Mechanism.uds],
            blocking=False,
            shm_direct=False,
        )
        args = rusty_comms_plugin._build_cli_args(
            params, "/tmp/out.json"
        )
        self.assertNotIn("--blocking", args)
        self.assertNotIn("--shm-direct", args)


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
        """Missing required keys should raise an exception."""
        raw = _build_sample_json()
        del raw["metadata"]["version"]
        with self.assertRaises(KeyError):
            rusty_comms_plugin._parse_json_output(raw)


class FunctionalTest(unittest.TestCase):
    """Functional tests with mocked subprocess execution."""

    @mock.patch("rusty_comms_plugin._find_binary")
    @mock.patch("rusty_comms_plugin.subprocess.run")
    def test_success_run(self, mock_run, mock_find):
        """Successful benchmark run should return SuccessOutput."""
        mock_find.return_value = "/usr/local/bin/ipc-benchmark"

        sample_json = _build_sample_json()

        def side_effect(cmd, **kwargs):
            for i, arg in enumerate(cmd):
                if arg == "--output-file" and i + 1 < len(cmd):
                    output_path = cmd[i + 1]
                    os.makedirs(
                        os.path.dirname(output_path), exist_ok=True
                    )
                    with open(output_path, "w") as f:
                        json.dump(sample_json, f)
                    break
            result = mock.Mock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        mock_run.side_effect = side_effect

        params = InputParams(mechanisms=[Mechanism.uds])
        output_id, output_data = rusty_comms_plugin.run_benchmark(
            params=params, run_id="test_run"
        )

        self.assertEqual(output_id, "success")
        self.assertIsInstance(output_data, SuccessOutput)
        self.assertEqual(output_data.metadata.version, "0.1.0")

    @mock.patch("rusty_comms_plugin._find_binary")
    @mock.patch("rusty_comms_plugin.subprocess.run")
    def test_nonzero_exit_returns_error(self, mock_run, mock_find):
        """Non-zero exit code should return ErrorOutput."""
        mock_find.return_value = "/usr/local/bin/ipc-benchmark"

        result = mock.Mock()
        result.returncode = 1
        result.stdout = ""
        result.stderr = "benchmark failed: permission denied"
        mock_run.return_value = result

        params = InputParams(mechanisms=[Mechanism.uds])
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
        params = InputParams(mechanisms=[Mechanism.uds])
        output_id, output_data = rusty_comms_plugin.run_benchmark(
            params=params, run_id="test_run"
        )

        self.assertEqual(output_id, "error")
        self.assertIsInstance(output_data, ErrorOutput)
        self.assertIn("not found", output_data.error)

    @mock.patch("rusty_comms_plugin._find_binary")
    @mock.patch(
        "rusty_comms_plugin.subprocess.run",
        side_effect=OSError("exec format error"),
    )
    def test_os_error_returns_error(self, mock_run, mock_find):
        """OSError during execution should return ErrorOutput."""
        mock_find.return_value = "/usr/local/bin/ipc-benchmark"

        params = InputParams(mechanisms=[Mechanism.tcp])
        output_id, output_data = rusty_comms_plugin.run_benchmark(
            params=params, run_id="test_run"
        )

        self.assertEqual(output_id, "error")
        self.assertIsInstance(output_data, ErrorOutput)
        self.assertIn("exec format error", output_data.error)


if __name__ == "__main__":
    unittest.main()
