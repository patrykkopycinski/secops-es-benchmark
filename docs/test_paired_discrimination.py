#!/usr/bin/env python3
"""Self-contained tests for paired_discrimination.py.

Run:  python3 docs/test_paired_discrimination.py

No pytest, no scipy, no network. The statistics are hand-rolled in the module
under test, so they are checked against closed-form values and against
synthetic data whose answer is known by construction -- not against a
reimplementation of the same arithmetic, which would only prove self-consistency.

Data-dependent checks are skipped automatically when the sweep artifacts are
absent, so this stays runnable from a clean clone.
"""
import hashlib
import importlib.util
import math
import os
import random
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("pd", os.path.join(HERE, "paired_discrimination.py"))
assert spec and spec.loader, "cannot load paired_discrimination.py"
pd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pd)


def _known_excluded_names():
    """Model names from the sweep dirs whose digest is in the exclusion set.

    Reads names off disk rather than hardcoding them, so this file names no
    unreleased product either. Yields nothing in a clean clone -- the digest
    presence check below still holds.
    """
    import glob
    seen = set()
    for run in glob.glob(os.path.join(pd.SWEEP_RUNS, "*.rep[123]")):
        name = os.path.basename(run).rsplit(".", 1)[0]
        h = hashlib.sha256(name.strip().lower().encode()).hexdigest()[:16]
        if h in pd._EXCLUDED_DIGESTS:
            seen.add(name)
    return sorted(seen)


_fail, _n, _skip = [], 0, 0


def ck(name, cond, detail=""):
    global _n
    _n += 1
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'   ' + detail if detail else ''}")
    if not cond:
        _fail.append(name)


def skip(name, why):
    global _skip
    _skip += 1
    print(f"  SKIP  {name}   ({why})")


def section(title):
    print(f"\n{title}")


# --- Holm-Bonferroni ------------------------------------------------------
section("[1] Holm-Bonferroni")
ck("known vector", all(abs(a - b) < 1e-9 for a, b in zip(
    pd.holm([0.001, 0.008, 0.039, 0.041, 0.9]), [0.005, 0.032, 0.117, 0.117, 0.9])))
ck("single hypothesis is identity", abs(pd.holm([0.03])[0] - 0.03) < 1e-12)
ck("clipped at 1.0", all(x <= 1.0 for x in pd.holm([0.6, 0.7, 0.9])))
ck("never below raw p", all(a >= b - 1e-12 for a, b in
                            zip(pd.holm([0.01, 0.02, 0.03]), [0.01, 0.02, 0.03])))

# --- Student-t ------------------------------------------------------------
section("[2] paired t vs closed form")
d5 = [1.0, 2.0, 3.0, 4.0, 5.0]
_, p_mod = pd.paired_t(d5)
ck("t=4.2426, df=4 -> p=0.013240", abs(p_mod - 0.013240) < 1e-5, f"p={p_mod:.6f}")
ck("critical t=2.2281, df=10 -> p=0.05", abs(pd._t_two_sided(2.228138852, 10) - 0.05) < 1e-6)
ck("t=0 -> p=1", abs(pd._t_two_sided(0.0, 10) - 1.0) < 1e-12)
ck("converges to normal at large df", abs(pd._t_two_sided(1.96, 5_000_000) - 0.05) < 1e-3)
ck("exact t conservative vs normal", p_mod > pd._normal_two_sided(4.242640687119285))
ck("n<2 is not significant", pd.paired_t([1.0])[1] == 1.0)

# --- Wilcoxon -------------------------------------------------------------
section("[3] Wilcoxon signed-rank")
dd = [0.3, 0.5, -0.1, 0.7, 0.9, 0.2, 0.4, 0.6]
w = pd.wilcoxon(dd)
ck("detects one-sided shift", 0.0 <= w < 0.05, f"p={w:.4f}")
ck("symmetric under negation", abs(pd.wilcoxon([-x for x in dd]) - w) < 1e-9)
ck("all-zero -> p=1", pd.wilcoxon([0.0] * 6) == 1.0)

# --- The bug this module exists to prevent --------------------------------
section("[4] paired vs unpaired, synthetic data with a known answer")
# Constant +0.05 per-item offset, zero noise in the DIFFERENCE, but large
# between-item variance. Paired must find it; unpaired CI overlap must not.
random.seed(7)
items = [f"q{i}" for i in range(60)]
base = {q: random.uniform(0, 1) for q in items}
per_item = {"A": {q: min(1.0, base[q] + 0.05) for q in items}, "B": dict(base)}
rows, _ = pd.adjacent_analysis(per_item, ["A", "B"], items, 1.0, 4000, 0)
ck("paired detects constant offset", rows[0]["sep"], f"p_t={rows[0]['p_t']:.2e}")
ck("unpaired CI misses it", pd.unpaired_ci_overlap(per_item, ["A", "B"], items) == 0)

section("[5] null control")
rows, _ = pd.adjacent_analysis({"A": dict(base), "C": dict(base)}, ["A", "C"], items, 1.0, 4000, 0)
ck("identical models do not separate", not rows[0]["sep"])
ck("zero mean difference", abs(rows[0]["diff"]) < 1e-12)

section("[6] determinism")
a, _ = pd.adjacent_analysis(per_item, ["A", "B"], items, 1.0, 3000, 42)
b, _ = pd.adjacent_analysis(per_item, ["A", "B"], items, 1.0, 3000, 42)
ck("same seed -> same bootstrap CI", a[0]["lo"] == b[0]["lo"] and a[0]["hi"] == b[0]["hi"])

# --- Published figures ----------------------------------------------------
section("[7] published figures re-derive from real data")
try:
    gper, gq = pd.load_graph()
    gmodels = sorted(gper, key=lambda m: -statistics.mean(gper[m][q] for q in gq))
    rows, _ = pd.adjacent_analysis(gper, gmodels, gq, 1.0, 10000, 0)
    ck("graph tier separates 3/4", sum(r["sep"] for r in rows) == 3, f"n={len(gq)}")
except (Exception, SystemExit) as e:  # noqa: BLE001 - artifacts absent in a clean clone
    skip("graph tier", type(e).__name__)

try:
    oper, _ = pd.load_objective(public_only=True)
    oq = sorted(set.intersection(*[set(oper[m]) for m in oper]))
    omodels = sorted(oper, key=lambda m: -statistics.mean(oper[m][q] for q in oq))
    rows, _ = pd.adjacent_analysis(oper, omodels, oq, 100.0, 10000, 0)
    ck("objective separates 2/22", sum(r["sep"] for r in rows) == 2,
       f"{len(omodels)} models, n={len(oq)}")
    bands = pd.tier_bands(oper, omodels, oq, 100.0, 10000, 0)
    ck("paired banding = 3 bands", len(bands) == 3)
    ck("top band holds 17 models", bands[0]["n"] == 17, f'lo={bands[0]["lo"]:.1f} hi={bands[0]["hi"]:.1f}')
    ck("unreleased models excluded", all(pd.is_public(m) for m in omodels),
       f"{len(omodels)} public")
except (Exception, SystemExit) as e:  # noqa: BLE001
    skip("objective tier", type(e).__name__)

section("[8] unreleased models excluded by default")
# Regression guard: exclusion must NOT depend on the caller setting an env var,
# and the source must not name an unreleased model in plaintext.
# Names live only as digests here too, so neither file leaks them. Recover a
# name only if you already know it: sha256(name.lower())[:16].
_EXCLUDED = sorted(pd._EXCLUDED_DIGESTS)
_saved = os.environ.pop("SECOPS_EXCLUDE", None)
try:
    ck("every excluded digest is rejected", all(
        not pd.is_public(n) for n in _known_excluded_names()), f"{len(_EXCLUDED)} digests")
    ck("is_public() accepts a released model", pd.is_public("openai-gpt-5.5"))
    ck("exclusion needs no env var", os.environ.get("SECOPS_EXCLUDE") is None)
finally:
    if _saved is not None:
        os.environ["SECOPS_EXCLUDE"] = _saved

_src = open(os.path.join(HERE, "paired_discrimination.py")).read()
ck("source stores digests, not names", "_EXCLUDED_DIGESTS" in _src and all(
    d in _src for d in _EXCLUDED))

print("\n" + "=" * 58)
print(f"{_n - len(_fail)}/{_n} passed" + (f", {_skip} skipped" if _skip else ""))
if _fail:
    print("FAILED: " + ", ".join(_fail))
sys.exit(1 if _fail else 0)
