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
from lab9.graders import GRADERS


def _check_ratchet(spec: dict, base_spec: dict) -> list[str]:
    problems: list[str] = []
    if spec.get("eval_set_version") != base_spec.get("eval_set_version"):
        return problems
    cur_m = {m["id"]: m for m in spec.get("metrics") or []}
    for bm in base_spec.get("metrics") or []:
        mid = bm["id"]
        if mid not in cur_m:
            problems.append(f"ratchet: metric {mid} removed")
            continue
        cm = cur_m[mid]
        if bm.get("blocking") and not cm.get("blocking"):
            problems.append(f"ratchet: metric {mid} became non-blocking")
        bth, cth = bm.get("threshold") or {}, cm.get("threshold") or {}
        if "min" in bth and (cth.get("min") is None or cth["min"] < bth["min"]):
            problems.append(f"ratchet: {mid} min lowered ({cth.get('min')} < {bth['min']})")
        if "max" in bth and (cth.get("max") is None or cth["max"] > bth["max"]):
            problems.append(f"ratchet: {mid} max raised ({cth.get('max')} > {bth['max']})")
        if "max_increase" in bth and (cth.get("max_increase") is None or cth["max_increase"] > bth["max_increase"]):
            problems.append(f"ratchet: {mid} max_increase raised")
        if bth.get("no_significant_drop") and not cth.get("no_significant_drop"):
            problems.append(f"ratchet: {mid} dropped no_significant_drop")

    cur_s = {(s["name"], s["metric"]): s for s in spec.get("slices") or []}
    for bs in base_spec.get("slices") or []:
        key = (bs["name"], bs["metric"])
        if key not in cur_s:
            problems.append(f"ratchet: slice {bs['name']}/{bs['metric']} removed")
            continue
        cs = cur_s[key]
        if bs.get("blocking") and not cs.get("blocking"):
            problems.append(f"ratchet: slice {bs['name']} became non-blocking")
        if "min" in bs and (cs.get("min") is None or cs["min"] < bs["min"]):
            problems.append(f"ratchet: slice {bs['name']} min lowered")
        if "max" in bs and (cs.get("max") is None or cs["max"] > bs["max"]):
            problems.append(f"ratchet: slice {bs['name']} max raised")
        if bs.get("no_significant_drop") and not cs.get("no_significant_drop"):
            problems.append(f"ratchet: slice {bs['name']} dropped no_significant_drop")
    return problems


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted."""
    problems: list[str] = []
    for k, v in (pr.get("metrics") or {}).items():
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            problems.append(f"metric {k} is {v}")

    pr_rows = pr.get("rows") or []
    base_rows = base.get("rows") or []
    manifest = pr.get("manifest") or {}
    expected_n = int(manifest.get("items") or 0) * len(manifest.get("seeds") or [])
    if len(pr_rows) != expected_n:
        problems.append(f"row count {len(pr_rows)} != {expected_n} (items * seeds)")

    pr_pairs = [(r.get("item_id"), r.get("seed")) for r in pr_rows]
    if len(set(pr_pairs)) != len(pr_pairs):
        problems.append("duplicate (item_id, seed) rows in PR")
    base_pairs = {(r.get("item_id"), r.get("seed")) for r in base_rows}
    if set(pr_pairs) != base_pairs:
        problems.append("(item_id, seed) set of PR differs from baseline")

    if pr.get("evaluator_failures"):
        problems.append(f"evaluator_failures non-empty ({len(pr['evaluator_failures'])})")

    graded_ids = [m["id"] for m in spec.get("metrics") or [] if m["id"] in GRADERS]
    for r in pr_rows:
        for mid in graded_ids:
            if r.get(mid) is None:
                problems.append(f"row {r.get('item_id')}@{r.get('seed')} has None for {mid}")
                break

    base_slices = {r.get("item_id"): sorted(r.get("slices") or []) for r in base_rows}
    for r in pr_rows:
        iid = r.get("item_id")
        if iid in base_slices and sorted(r.get("slices") or []) != base_slices[iid]:
            problems.append(f"slice tags for {iid} differ from baseline")
            break

    if base_spec is not None:
        problems.extend(_check_ratchet(spec, base_spec))
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices") or []:
        name, metric = sl["name"], sl["metric"]
        a = per_item(pr, metric, slice_name=name)
        if not a:
            if sl.get("blocking"):
                blocked.append(f"slice:{name}/{metric}")
            lines.append(f"  slice:{name}/{metric:<12} MISSING")
            continue
        val = sum(a.values()) / len(a)
        verdict, note = "ok", ""
        if "min" in sl and val < sl["min"]:
            verdict = "fail"
        if "max" in sl and val > sl["max"]:
            verdict = "fail"
        if sl.get("no_significant_drop"):
            b = per_item(base, metric, slice_name=name)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap(
                [a[k] for k in keys],
                [b[k] for k in keys],
                n_resamples=bs.get("n_resamples", 1000),
                rng=bs.get("rng", 2027),
            )
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and sl.get("blocking"):
            blocked.append(f"slice:{name}/{metric}")
        label = "ok" if verdict == "ok" else ("BLOCK" if sl.get("blocking") else "warn")
        lines.append(f"  slice:{name}/{metric:<12} {val:<8.4f} {note:<28} {label}")
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
