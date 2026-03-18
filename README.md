# Arcaflow Plugin: rusty-comms IPC Benchmark

An [Arcaflow](https://arcalot.io/arcaflow/) plugin that wraps the
[rusty-comms](https://github.com/redhat-performance/rusty-comms) IPC
benchmark suite. It executes the `ipc-benchmark` binary inside a
container and returns strongly-typed latency and throughput results
suitable for automated workflows.

## Supported IPC Mechanisms

| Mechanism | CLI value | Description |
|-----------|-----------|-------------|
| Unix Domain Sockets | `uds` | High-performance local communication |
| Shared Memory | `shm` | Direct memory with ring buffers |
| TCP Sockets | `tcp` | Network-capable communication |
| POSIX Message Queues | `pmq` | Kernel-managed messaging (Linux) |
| All | `all` | Test every available mechanism |

## Quick Start

### Build the container image

```bash
docker build -t arcaflow-plugin-rusty-comms .
```

### Run standalone

```bash
cat inputs/example.yaml | \
  docker run -i --rm arcaflow-plugin-rusty-comms -f -
```

### Run with Arcaflow

Reference this plugin in your workflow:

```yaml
steps:
  benchmark:
    plugin:
      deployment_type: image
      src: arcaflow-plugin-rusty-comms:latest
    input:
      mechanisms:
        - uds
        - tcp
      message_size: 4096
      msg_count: 50000
```

## Step: `run-benchmark`

### Input

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `mechanisms` | list of enum | **yes** | IPC mechanisms to test |
| `message_size` | int | no | Payload size in bytes |
| `msg_count` | int | no | Number of messages to send |
| `duration` | string | no | Test duration, e.g. `30s` |
| `concurrency` | int | no | Concurrent workers |
| `blocking` | bool | no | Use blocking I/O mode |
| `buffer_size` | int | no | Internal buffer size |
| `warmup_iterations` | int | no | Warmup messages |
| `percentiles` | list of float | no | Percentile levels |
| `one_way` | bool | no | Enable one-way tests |
| `round_trip` | bool | no | Enable round-trip tests |
| `send_delay` | string | no | Delay between sends |
| `server_affinity` | int | no | Pin receiver to CPU core |
| `client_affinity` | int | no | Pin sender to CPU core |
| `shm_direct` | bool | no | Direct memory SHM mode |
| `continue_on_error` | bool | no | Continue on failure |
| `include_first_message` | bool | no | Include canary message |
| `host` | string | no | TCP host address |
| `port` | int | no | TCP port |
| `pmq_priority` | int | no | PMQ message priority |
| `quiet` | bool | no | Silence console output |
| `extra_args` | list of string | no | Additional CLI flags |

### Outputs

**`success`** - Returns the complete benchmark results including:

- `metadata` - Version, timestamp, system information
- `results` - Per-mechanism results with latency metrics (percentiles,
  min/max/mean/median/stddev), throughput metrics (messages/sec, bytes/sec),
  and summary statistics
- `summary` - Overall summary with fastest mechanism and lowest latency
  mechanism

**`error`** - Returns an error message when the benchmark fails.

## Development

### Local testing

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m pytest tests/
```

### Run the plugin schema

```bash
python arcaflow_plugin_rusty_comms/rusty_comms_plugin.py --schema
```

## License

Apache License 2.0
