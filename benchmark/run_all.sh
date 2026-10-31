#!/usr/bin/env bash
# Reproduce baseline + optimized benchmarks for all three scales.
# Requires an installed pytest venv (see README) with dpath deps available.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
D="$HERE/.."
mkdir -p "$D/benchmark/raw"

# Which python to use (pass as $1 if not the default venv)
PY="${1:-/tmp/dvenv/bin/python}"
BASE_SITE="$HERE/../src/dpath_baseline"
OPT_SITE="$HERE/../src/dpath_opt"

for sc in small medium large; do
  for impl in baseline:src/dpath_baseline optimized:src/dpath_opt; do
    name="${impl%%:*}"; src="${impl##*:}"
    "$PY" "$HERE/bench.py" --site "$src" --scale "$sc" \
        --out "$HERE/raw/${name}-${sc}" > "$HERE/raw/${name}-${sc}-summary.json"
  done
done
echo "done; summaries written to benchmark/raw/*-summary.json"