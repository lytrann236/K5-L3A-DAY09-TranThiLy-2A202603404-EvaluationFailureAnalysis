"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    graded = [m["id"] for m in spec.get("metrics", [])]
    # 1. Every reported number must be a real number (NaN/inf compare False with any floor).
    for name, rep in (("PR", pr), ("baseline", base)):
        for k, v in (rep.get("metrics") or {}).items():
            if isinstance(v, float) and not math.isfinite(v):
                problems.append(f"{name} metric {k} is {v}")
    # 2. Rows must cover items x seeds exactly once, for both reports.
    for name, rep in (("PR", pr), ("baseline", base)):
        man, rows = rep.get("manifest") or {}, rep.get("rows") or []
        want = (man.get("items") or 0) * len(man.get("seeds") or [])
        if len(rows) != want:
            problems.append(f"{name} has {len(rows)} rows, manifest says {want} (items x seeds)")
        keys = [(r.get("item_id"), r.get("seed")) for r in rows]
        dup = len(keys) - len(set(keys))
        if dup:
            problems.append(f"{name} has {dup} duplicated (item, seed) row(s)")
        bad_seeds = sorted({r.get("seed") for r in rows} - set(man.get("seeds") or []), key=str)
        if bad_seeds:
            problems.append(f"{name} rows use seeds not in its manifest: {bad_seeds}")
    # 3. PR and baseline must be graded on the same (item, seed) set and the same seeds.
    pr_keys = {(r.get("item_id"), r.get("seed")) for r in pr.get("rows") or []}
    base_keys = {(r.get("item_id"), r.get("seed")) for r in base.get("rows") or []}
    if pr_keys != base_keys:
        problems.append(f"(item, seed) set differs from baseline: {len(pr_keys - base_keys)} extra, "
                        f"{len(base_keys - pr_keys)} missing")
    if sorted((pr.get("manifest") or {}).get("seeds") or []) != sorted((base.get("manifest") or {}).get("seeds") or []):
        problems.append("seed list differs from baseline")
    # 4. A crashed grader must not silently drop out of the mean.
    for name, rep in (("PR", pr), ("baseline", base)):
        if rep.get("evaluator_failures"):
            problems.append(f"{name} has {len(rep['evaluator_failures'])} evaluator failure(s)")
        row_metrics = {k for r in rep.get("rows") or [] for k in r}
        for mid in graded:
            if mid not in row_metrics:
                continue                       # aggregate-only metric (pass_5, pass_hat_k, cost)
            missing = sum(1 for r in rep.get("rows") or [] if r.get(mid) is None
                          or (isinstance(r.get(mid), float) and not math.isfinite(r[mid])))
            if missing:
                problems.append(f"{name} has {missing} row(s) with no value for {mid}")
        for m in spec.get("metrics", []):
            if m["id"] not in (rep.get("metrics") or {}) and m.get("blocking"):
                problems.append(f"{name} report lacks blocking metric {m['id']}")
    # 5. Slice tags are a property of the item: they may not change between baseline and PR.
    base_tags = {r.get("item_id"): sorted(r.get("slices") or []) for r in base.get("rows") or []}
    for r in pr.get("rows") or []:
        iid = r.get("item_id")
        if iid in base_tags and sorted(r.get("slices") or []) != base_tags[iid]:
            problems.append(f"slice tags of {iid} differ from baseline")
            break
    # 6. Ratchet: on the same eval-set version thresholds may only get stricter.
    if base_spec is not None:
        problems += ratchet_problems(spec, base_spec)
    return problems


def _looser(new: dict, old: dict, where: str) -> list[str]:
    out = []
    if "max" in old and ("max" not in new or new["max"] > old["max"]):
        out.append(f"{where}: max loosened {old['max']} -> {new.get('max')}")
    if "min" in old and ("min" not in new or new["min"] < old["min"]):
        out.append(f"{where}: min loosened {old['min']} -> {new.get('min')}")
    if "max_increase" in old and ("max_increase" not in new or new["max_increase"] > old["max_increase"]):
        out.append(f"{where}: max_increase loosened {old['max_increase']} -> {new.get('max_increase')}")
    if old.get("no_significant_drop") and not new.get("no_significant_drop"):
        out.append(f"{where}: no_significant_drop removed")
    return out


def ratchet_problems(spec: dict, base_spec: dict) -> list[str]:
    if spec.get("eval_set_version") != base_spec.get("eval_set_version"):
        return []                              # new eval-set version: a new baseline, new thresholds
    out: list[str] = []
    new_m = {m["id"]: m for m in spec.get("metrics", [])}
    for m in base_spec.get("metrics", []):
        n = new_m.get(m["id"])
        if n is None:
            out.append(f"ratchet: metric {m['id']} removed")
            continue
        if m.get("blocking") and not n.get("blocking"):
            out.append(f"ratchet: metric {m['id']} no longer blocking")
        out += [f"ratchet: {p}" for p in _looser(n.get("threshold") or {}, m.get("threshold") or {}, m["id"])]
    key = lambda s: (s.get("name"), s.get("metric"))
    new_s = {key(s): s for s in spec.get("slices") or []}
    for s in base_spec.get("slices") or []:
        n = new_s.get(key(s))
        where = f"slice {s.get('name')}/{s.get('metric')}"
        if n is None:
            out.append(f"ratchet: {where} removed")
            continue
        if s.get("blocking") and not n.get("blocking"):
            out.append(f"ratchet: {where} no longer blocking")
        out += [f"ratchet: {p}" for p in _looser(n, s, where)]
    return out


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices") or []:
        name, metric = sl["name"], sl["metric"]
        sid = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        verdict, note = "ok", ""
        if not a:
            verdict, val = "missing", None
        else:
            val = round(sum(a.values()) / len(a), 4)
            if "min" in sl and val < sl["min"]:
                verdict = "fail"
            if sl.get("no_significant_drop"):
                keys = sorted(set(a) & set(b))
                if keys:
                    d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                       n_resamples=bs.get("n_resamples", 1000),
                                                       rng=bs.get("rng", 2027))
                    note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                    if hi < 0:
                        verdict = "fail"
        if verdict != "ok" and sl.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if sl.get("blocking") else "warn")
        th = {k: sl[k] for k in ("min", "no_significant_drop") if k in sl}
        lines.append(f"  {sid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label} (n={len(a)} items)")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
