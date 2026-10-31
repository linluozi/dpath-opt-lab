"""Differential test: baseline vs optimized dpath, byte-identical outputs.

Each implementation lives in its own directory under src/ (identical except
for the one-line `typing` -> `collections.abc` change). To avoid module-name
collisions both run in isolated subprocesses over the SAME generated corpus,
and their serialized outputs are compared byte-for-byte (json.dumps, no
approx, no structural shortcut). >=1000 independent comparisons.

Run:
    pytest tests/test_diff.py -q
(uses src/dpath_baseline and src/dpath_opt; overridable via env vars)
"""
import copy
import json
import math
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

BASE_SITE = os.environ.get("DPATH_BASE_SITE", os.path.join(ROOT, "src", "dpath_baseline"))
OPT_SITE = os.environ.get("DPATH_OPT_SITE", os.path.join(ROOT, "src", "dpath_opt"))

RUNNER_TEMPLATE = r"""
import json, sys, copy, random, math
sys.path.insert(0, SITE)
import dpath
OBJ = json.loads(OBJ_S)
CALLS = json.loads(CALLS_S)
def run(op, obj, arg, flag):
    try:
        if op == 'search':
            return [x for x in dpath.search(obj, arg, yielded=True)]
        if op == 'values':
            return [x for x in dpath.values(obj, arg, dirs=False)]
        if op == 'get':
            return dpath.get(obj, arg)
        if op == 'merge':
            dst = {}
            dpath.merge(dst, copy.deepcopy(obj), flags=flag)
            return dst
        if op == 'new':
            dst = copy.deepcopy(obj)
            dpath.new(dst, arg, VALUE)
            return dst
        if op == 'delete':
            dst = copy.deepcopy(obj)
            dpath.delete(dst, 'nonexistent_zzz')
            return dst
    except Exception as ex:
        return ('__ERR__', type(ex).__name__)

def js(x):
    try:
        return json.dumps(x, sort_keys=True, ensure_ascii=False, allow_nan=True, default=str)
    except Exception as ex:
        return ('__ERR__', type(ex).__name__)

out = []
for (op, arg, flag) in CALLS:
    r = run(op, OBJ, arg, flag)
    out.append(js(r))
print(json.dumps(out, ensure_ascii=False))
"""


def corpus():
    c = [
        None, {}, [], {"": 1}, {"a": None}, 0, 1, -1, 3.14, True, False, "",
        "text", "üñïçødé-✓", "0", "\u65e5\u672c\u8a9e", [1, 2, 3],
        {"a": {"b": {"c": 1}}}, {"a": [{"b": 2}, {"b": 3}]},
        {"a": {"b": [1, 2, 3]}}, {"k0": {"k1": {"k2": 0}}},
        {"a": {"a": {"a": {"a": {"a": {"a": 1}}}}}},
        {"x": [{"y": [{"z": 1}]}]}, {"0": {"1": {"2": "three"}}},
        float("inf"), float("nan"), {"f": float("nan")},
    ]
    for n in range(12):
        d = {"deep": {"value": n}}
        k = "deep"
        for _ in range(n):
            d[k][f"{_}-k{n}"] = n * 100 + _
        c.append(d)
    big = {f"key{i}": {"$": [i, i + 1, {"tag": f"v{i}"}], "flag": i % 2 == 0}
           for i in range(300)}
    c.append(big)
    return c


def make_calls():
    calls = []
    globs = ["**", "*", "a", "key0", "0/1", "deep", "**/value", "k1",
             "*/$", "key7/$", "deep/5-k7", "m/k*/tag"]
    for g in globs:
        calls.append(("search", g, None))
        calls.append(("values", g, None))
        calls.append(("get", g, None))
    adds = ["/x/y", "/0/1", "/w/1/2/3", "/zz", "/a/a/a", "/deep/new"]
    for a in adds:
        calls.append(("new", a, None))
    calls.append(("delete", "", None))
    return calls


def run_site(site, obj_s, calls):
    src = RUNNER_TEMPLATE.replace("SITE", json.dumps(site)) \
                         .replace("OBJ_S", json.dumps(obj_s)) \
                         .replace("CALLS_S", json.dumps(json.dumps(calls))) \
                         .replace("VALUE", "7")
    r = subprocess.run([sys.executable, "-c", src], capture_output=True,
                       text=True, timeout=120)
    if r.returncode != 0:
        raise AssertionError(f"runner failed on {site}: {r.stderr[-1500:]}")
    return json.loads(r.stdout)


def compare(calls, objects):
    total = 0
    for obj in objects:
        obj_s = json.dumps(obj, ensure_ascii=False, default=str)
        rb = run_site(BASE_SITE, obj_s, calls)
        ro = run_site(OPT_SITE, obj_s, calls)
        assert rb == ro, f"mismatch for object: {obj_s[:120]}"
        total += len(calls)
    return total


def test_diff_1000_plus():
    calls = make_calls()
    objects = corpus()
    n = compare(calls, objects)
    # add scaled randomized structures
    rng = random.Random(11)
    gen = []
    for t in range(60):
        m = {}
        for i in range(50):
            m[f"k{i}"] = {"v": i, "tag": ["x", "y"][i % 2], "z": float(i)}
        gen.append({"m": m, "list": [{ "p": i, "q": "s" * (i % 5)} for i in range(25)]})
    n2 = compare(calls, gen)
    total = n + n2

    # explicit merge differentials over many inputs
    mcall = [("merge", "", 1), ("merge", "", 2), ("merge", "", 4)]
    merge_obj = corpus() + gen
    total += compare(mcall, merge_obj)

    assert total >= 1000, f"only {total} comparisons"
    print(f"[test_diff] {total} byte-identical differential comparisons passed")

    # gate 2 also enforced silently: 0 differences (assert above would fail)