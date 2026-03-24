# Arcaflow Plugin: rusty-comms IPC Benchmark

An [Arcaflow](https://arcalot.io/arcaflow) plugin that wraps the
[rusty-comms](https://github.com/redhat-performance/rusty-comms) IPC
benchmark suite. It executes the `ipc-benchmark` binary, parses the
structured JSON output, and returns strongly-typed latency and
throughput results to the Arcaflow engine.

## Supported IPC Mechanisms

| Mechanism | CLI Name | Description |
|-----------|----------|-------------|
| Unix Domain Socket | `uds` | Local inter-process socket |
| TCP Socket | `tcp` | TCP loopback socket |
| Shared Memory | `shm` | POSIX shared memory (with optional direct mode) |
| POSIX Message Queue | `pmq` | Kernel-managed message queue |

Use `all` to benchmark every mechanism in a single run.

## Building the Container Image

The plugin ships as a multi-stage container image that compiles
`ipc-benchmark` from source (Rust) and bundles it with the Python
plugin code.

```bash
podman build -t arcaflow-plugin-rusty-comms .
```

## Running with Arcaflow

### Prerequisites

- [Arcaflow engine](https://github.com/arcalot/arcaflow-engine/releases)
  binary (or built from source)
- A container runtime: Podman (default) or Docker

### Quick Start

1. Build the container image (see above).

2. Create an input file (or use `inputs/example.yaml`):

```yaml
tests:
  - mechanisms:
      - uds
    message_size: 1024
    msg_count: 10000
```

3. Run the workflow:

```bash
arcaflow --input inputs/example.yaml \
         --config config.yaml \
         --workflow workflow.yaml
```

The engine deploys the plugin container, runs the benchmark, and
prints the structured results to stdout.

### Pre-built Test Suites

Two test input files are included for comprehensive benchmarking:

- **`quick-rusty-comms-arcaflow-testing.yaml`** — A small set of
  tests across UDS, TCP, PMQ, and SHM for quick validation.
- **`comprehensive-rusty-comms-arcaflow-testing.yaml`** — A full
  benchmark matrix covering multiple mechanisms, message sizes,
  blocking/async modes, concurrency levels, one-way vs round-trip,
  and send-delay latency profiling.

Example:

```bash
arcaflow --input comprehensive-rusty-comms-arcaflow-testing.yaml \
         --config config.yaml
```

## Input Parameters

Each test run in the `tests` list accepts the following parameters:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `mechanisms` | list of enum | Yes | IPC mechanisms to test (`uds`, `shm`, `tcp`, `pmq`, `all`) |
| `message_size` | int | No | Message payload size in bytes |
| `msg_count` | int | No | Number of messages to send |
| `duration` | string | No | Fixed duration (e.g. `30s`, `5m`); overrides `msg_count` |
| `concurrency` | int | No | Number of concurrent workers |
| `blocking` | bool | No | Use blocking I/O (default: true); set `false` for async |
| `buffer_size` | int | No | Internal buffer size in bytes |
| `warmup_iterations` | int | No | Warmup messages before measurement |
| `percentiles` | list of float | No | Percentile levels to compute |
| `one_way` | bool | No | Run one-way latency tests only |
| `round_trip` | bool | No | Run round-trip latency tests only |
| `send_delay` | string | No | Delay between sends (e.g. `1ms`, `50us`) |
| `server_affinity` | int | No | Pin receiver to a CPU core |
| `client_affinity` | int | No | Pin sender to a CPU core |
| `shm_direct` | bool | No | Use direct memory SHM (8KB max, auto-enables blocking) |
| `continue_on_error` | bool | No | Continue if a mechanism fails |
| `quiet` | bool | No | Silence console output |
| `extra_args` | list of string | No | Additional CLI flags for `ipc-benchmark` |

## Output Schema

On success, the plugin returns:

- **`metadata`** — Version, timestamp, system info (OS, CPU cores,
  memory, Rust version).
- **`results`** — Per-mechanism results including:
  - One-way and round-trip latency (min, max, mean, median, std dev,
    percentiles)
  - Throughput (messages/sec, bytes/sec, totals, duration)
  - Test configuration used
  - Summary statistics (total messages, bytes, throughput, error count)
- **`summary`** — Overall summary across all mechanisms with the
  fastest and lowest-latency mechanism identified.

On error, an `ErrorOutput` with a descriptive error message is returned.

## Utilities

The `utils/` directory contains helper scripts for multi-run
benchmarking and result analysis:

- **`utils/run_benchmarks.sh`** — Builds the container and runs the
  comprehensive suite N times (default 5), producing an averaged CSV.
- **`utils/python/run_comprehensive.py`** — Python runner that
  executes multiple Arcaflow iterations and averages results.
- **`utils/python/parse_arcaflow_output.py`** — Parses Arcaflow engine
  output YAML into a CSV summary for analysis.

### Running the Full Benchmark Suite

```bash
# Run 5 iterations and produce averaged CSV
./utils/run_benchmarks.sh

# Run 3 iterations
./utils/run_benchmarks.sh 3

# Parse existing outputs only (skip running)
./utils/run_benchmarks.sh --skip
```

Results are written to `utils/out/comprehensive_averaged.csv`.

## Development

### Running Tests

From the repository root:

```bash
PYTHONPATH=arcaflow_plugin_rusty_comms \
  python -m pytest tests/ -v
```

Or using unittest directly:

```bash
cd arcaflow_plugin_rusty_comms
python -m unittest discover -s ../tests -v
```

### Dependencies

Managed with [Poetry](https://python-poetry.org/):

```bash
poetry install
```

Runtime dependency: `arcaflow-plugin-sdk >= 0.14.0`

## License

Apache License, Version 2.0. See [LICENSE](LICENSE) for details.
