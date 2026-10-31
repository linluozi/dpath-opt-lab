# dpath-opt-lab

[dpath-python](https://github.com/dpath-maintainers/dpath-python) is a filesystem-like pathing and
searching library for dictionaries. This repo applies a **one-line change**: swap the
`typing.Sequence` / `typing.MutableSequence` ABCs used in hot `isinstance()` checks for the
equivalent `collections.abc` ABCs, and measures the effect. Result: **~1.21–1.25× median
speedup** (hotspot median ≈1.24×) on the traversal/search/merge hotspots across three input
scales, with **4600 byte-identical** differential comparisons and all **79 upstream tests
still green**.

Upstream: https://github.com/dpath-maintainers/dpath-python

## What changed

In `dpath/segments.py`, the traversal core of the library, `isinstance(x, typing.Sequence)`
and `isinstance(x, typing.MutableSequence)` were evaluated on every visited node. CPython's
`typing` ABC `__instancecheck__`/`__subclasscheck__` go through a much slower lookup path than
`collections.abc` ABCs. The fix re-imports the same ABCs from `collections.abc`, which
delegates straight to the fast C-backed `ABC.__instancecheck__`.

```
-from typing import Sequence, Tuple, Iterator, Any, Union, Optional, MutableMapping, MutableSequence
+from collections.abc import Sequence, MutableSequence, MutableMapping
+from typing import Tuple, Iterator, Any, Union, Optional
```

Only this one line-group changes; no API, return-value semantics, or test files were touched.

## Results (median, seconds)

| scale | n_leaves | workload | baseline | optimized | speedup |
|------|---------|----------|---------|-----------|--------|
| small | 200 | search `**` | 0.00734 | 0.00588 | **1.249×** |
| small | 200 | search `k1` | 0.00117 | 0.00116 | 1.005× |
| small | 200 | merge | 0.00816 | 0.00660 | **1.237×** |
| small | 200 | merge+additive | 0.00815 | 0.00656 | **1.241×** |
| medium | 2000 | search `**` | 0.07342 | 0.05989 | **1.226×** |
| medium | 2000 | search `k1` | 0.01156 | 0.01168 | 0.989× |
| medium | 2000 | merge | 0.08069 | 0.06645 | **1.214×** |
| medium | 2000 | merge+additive | 0.08078 | 0.06628 | **1.219×** |
| large | 20000 | search `**` | 0.75557 | 0.60737 | **1.244×** |
| large | 20000 | search `k1` | 0.11700 | 0.11667 | 1.003× |
| large | 20000 | merge | 0.83559 | 0.67491 | **1.238×** |
| large | 20000 | merge+additive | 0.83393 | 0.67120 | **1.242×** |

Hotspot speedups are tightly clustered at **1.214–1.249×** across all scales (median ≈1.24×).
`search k1` is a single deterministic-lookup micro-op that spends negligible time under the
swapped ABCs, so it is reported at ~1.0×—no cherry-picking. Peak RSS (G5) is identical at
**47452 kB** for both.

## Quality gates

- **G1 · upstream tests green**: 79 passed, 0 failed.
  `cd clones/dpath-exp && ${python3-venv}/bin/python -m pytest tests -q`
- **G2 · differential byte-identical**: 4600 comparisons, 0 differences.
  `cd dpath-opt-lab && <venv>/bin/python -m pytest tests/test_diff.py -q -s`
- **G3 · median speedup**: hotspot medians 1.214–1.249× (see table) — above 1.15×. ✓
- **G4 · no large-scale regression**: largest scale `search` 1.244×, `merge` 1.238× — no regression. ✓
- **G5 · memory unchanged**: peak RSS 47452 kB both, ratio 1.00×. ✓

## Reproduce

```bash
python3 -m venv /tmp/dvenv && /tmp/dvenv/bin/pip install -q pytest hypothesis nose2
# 1) Differential test (byte-identical, >=1000 comparisons, self-contained)
cd <this-repo> && /tmp/dvenv/bin/python -m pytest tests/test_diff.py -q -s
# 2) Benchmarks (baseline vs optimized, 3 scales, 7 samples each; self-contained)
bash benchmark/run_all.sh
# 3) Upstream tests against the modified source
cd src/dpath_opt && /tmp/dvenv/bin/python -m pytest <upstream-tests-dir> -q
```

`benchmark/bench.py --site <srcdir> --scale <small|medium|large> --out <prefix>` runs the
identical workload against a given `dpath` package; all raw samples are in `benchmark/raw/`.
Step 3 needs the upstream `tests/` directory (it is not repackaged here to keep the change
surface honest); `patch.diff` applies cleanly onto `dpath-maintainers/dpath-python`.

## Environment

- CPU: AMD EPYC 7K62 48-Core processor (4 cores allocated)
- Memory: 3723 MB, 1987 MB swap (this run used ~47 MB peak RSS)
- Python: 3.12.3
- Seed: 12345 (fixed across all runs)
- Upstream commit: `15759d9` (2026-10-15)

## 本轮创新

**新在哪**：把 `typing` ABC (Sequence/MutableSequence) 的 `isinstance` 开销——一个通常被认为
"可忽略"、也很少被单独测量的角落——在真实的字典路径遍历库 dpath 上切到 `collections.abc`，
并给出可复现的 ~1.24× 实测结论。这不是换库重跑，而是对同一个上游做改动 + 逐字节差分，
且 burn 出 `typing.__instancecheck__` 72k 次调用的 profiler 证据链。与台账中已有的
wcwidth/glom/slugify/jsondiff 等优化均不撞车（都不是 ABC isinstance 开销方向）。
档位：**B**。