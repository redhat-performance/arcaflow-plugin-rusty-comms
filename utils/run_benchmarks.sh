#!/usr/bin/env bash
#
# Run the comprehensive Arcaflow IPC benchmark suite.
#
# Builds the container, runs N iterations (default 5),
# and produces an averaged CSV in utils/out/.
#
# Usage:
#   ./utils/run_benchmarks.sh            # 5 iterations
#   ./utils/run_benchmarks.sh 3          # 3 iterations
#   ./utils/run_benchmarks.sh --skip     # parse only
#
set -euo pipefail

UTILS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$UTILS_DIR")"
PYTHON_DIR="$UTILS_DIR/python"
OUT_DIR="$UTILS_DIR/out"

ITERATIONS="${1:-5}"
SKIP_RUNS=false

if [[ "$ITERATIONS" == "--skip" ]]; then
    SKIP_RUNS=true
fi

echo "============================================"
echo " Arcaflow IPC Benchmark Suite"
echo "============================================"
echo ""

if [[ "$SKIP_RUNS" == false ]]; then
    echo "[1/3] Building container..."
    podman build -t arcaflow-plugin-rusty-comms "$PLUGIN_DIR" \
        2>&1 | tail -3
    echo ""

    echo "[2/3] Running $ITERATIONS iterations..."
    echo "      (each takes ~17 minutes)"
    echo ""
    python3 "$PYTHON_DIR/run_comprehensive.py" \
        --iterations "$ITERATIONS"
else
    echo "[1/2] Skipping container build (--skip)"
    echo ""
    echo "[2/2] Parsing existing outputs..."
    python3 "$PYTHON_DIR/run_comprehensive.py" --skip-runs
fi

echo ""
echo "============================================"
echo " Complete"
echo "============================================"
echo " CSV: $OUT_DIR/comprehensive_averaged.csv"
echo " Raw: $OUT_DIR/run*.out"
echo "============================================"
