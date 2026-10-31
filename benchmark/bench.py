#!/usr/bin/env python3
"""Benchmark for the dpath `typing` -> `collections.abc` ABC swap.

Measures the realistic hotspots of dpath traversal/search over 3 scales.
Runs identical code against either the baseline or optimized `dpath` package
(selected via --site). Every timed sample is recorded to benchmark/raw/.
Uses time.perf_counter(). Seed fixed for reproducibility.
"""
import argparse
import copy
import json
import os
import random
import statistics
import sys
import time


def build(n):
    """A nested dict with ~n leaves, mixing scalar values, lists and dicts."""
    out = {}
    for i in range(n):
        key = f"k{i}"
        if i % 3 == 0:
            out[key] = [{"x": i, "y": i}]
        elif i % 3 == 1:
            out[key] = {"a": i, "b": {"c": i}}
        else:
            out[key] = i
    return out


def measure(search_obj, merge_obj, samples):
    out = {}
    # workload 1: dpath.search(obj, '**') -- full traversal + glob match
    t0 = time.perf_counter()
    dpath.search(search_obj, "**")
    out["search"] = time.perf_counter() - t0

    # workload 2: dpath.search(obj, 'k1') -- specific select
    t0 = time.perf_counter()
    dpath.search(search_obj, "k1")
    out["search_select"] = time.perf_counter() - t0

    # workload 3: dpath.merge(dst, src) -- hottest op (search + set + types)
    dst = {}
    t0 = time.perf_counter()
    dpath.merge(dst, merge_obj)
    out["merge"] = time.perf_counter() - t0

    # workload 4: dpath.merge with ADDITIVE on lists
    dst = {}
    t0 = time.perf_counter()
    dpath.merge(dst, merge_obj, flags=dpath.MergeType.ADDITIVE)
    out["merge_additive"] = time.perf_counter() - t0
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", required=True, help="path of the dpath package dir")
    ap.add_argument("--scale", choices=["small", "medium", "large"], required=True)
    ap.add_argument("--samples", type=int, default=7)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=12345)
    args = ap.parse_args()

    sys.path.insert(0, args.site)
    global dpath
    import dpath
    rng = random.Random(args.seed)

    n_leaf = {"small": 200, "medium": 2000, "large": 20000}[args.scale]
    obj = build(n_leaf)

    # warmup
    for _ in range(3):
        merge_obj = copy.deepcopy(obj)
        measure(obj, merge_obj, 1)

    # timed samples
    records = {}
    for i in range(args.samples):
        merge_obj = copy.deepcopy(obj)
        rec = measure(obj, merge_obj, 1)
        for wname, secs in rec.items():
            fname = f"{args.out}-{wname}-{i}.json"
            with open(fname, "w") as fh:
                json.dump({"workload": wname, "scale": args.scale, "i": i,
                           "seconds": secs, "seed": args.seed, "n_leaf": n_leaf}, fh)
            records.setdefault(wname, []).append(secs)

    summary = {}
    for wname, samples in records.items():
        s = sorted(samples)
        summary[wname] = {
            "samples": samples,
            "median": statistics.median(samples),
            "p25": s[max(0, len(s) // 4)],
            "p75": s[min(len(s) - 1, len(s) * 3 // 4)],
            "mean": statistics.mean(samples),
            "stdev": statistics.stdev(samples) if len(samples) > 1 else 0.0,
            "rel_stdev": (statistics.stdev(samples) / statistics.mean(samples))
                          if len(samples) > 1 and statistics.mean(samples) else 0.0,
        }
    print(json.dumps({"scale": args.scale, "n_leaf": n_leaf, "seed": args.seed,
                       "workloads": summary}, indent=2))


if __name__ == "__main__":
    main()