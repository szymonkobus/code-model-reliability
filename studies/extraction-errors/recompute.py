#!/usr/bin/env python3
"""Recomputes the extraction-error bound from this study's per-arm table and checks its arms against the registry.

Reads this study's ``per_arm.csv`` (per arm on wave 1: judged attempts, attempts whose judged code was not the answer
the model settled on, the verdicts that changed when both versions were judged, and the pass rate and the two crossings
as judged and corrected) and the registry's ``arms.jsonl``. Prints the shares over all attempts, the largest moves of
the reliability crossing and of the pass rate, and checks that every arm is an arm of record. The raw replies the
study read do not ship, so the per-arm counts are the study's record and the shares are recomputed from them. Exits 1
when a check fails.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tables  # noqa: E402

HERE = Path(__file__).resolve().parent


def num(s: str):
    return float(s) if s not in ("", None) else None


def main() -> int:
    args = tables.arg_parser(__doc__.splitlines()[0]).parse_args()
    data = Path(args.data)
    rows = tables.read_csv(HERE / "per_arm.csv")
    registry = {r["arm"] for r in tables.read_registry_arms(data)}
    rep = tables.Report()

    attempts = sum(int(r["attempts"]) for r in rows)
    wrong = sum(int(r["wrong_code_attempts"]) for r in rows)
    ff = sum(int(r["false_fail"]) for r in rows)
    fp = sum(int(r["false_pass"]) for r in rows)
    not_rejudged = sum(int(r["not_rejudged"]) for r in rows)
    rep.say(f"arms: {len(rows)}; judged attempts on wave 1: {attempts:,}")
    rep.say(f"judged on code that was not the model's answer: {wrong:,} ({wrong / attempts:.2%}); of these not re-judged: {not_rejudged}")
    rep.say(f"verdicts that change when the model's own code is judged: {ff + fp:,} ({(ff + fp) / attempts:.2%}): "
            f"failures that should have been passes {ff:,} ({ff / attempts:.2%}), passes whose later version fails {fp:,} ({fp / attempts:.3%})")
    rep.check(all(r["arm"] in registry for r in rows), "every arm of the study is an arm of record in the registry")

    moves = []
    for r in rows:
        a, b = num(r["d99_pct_as_judged"]), num(r["d99_pct_corrected"])
        pa, pb = num(r["pass_rate_as_judged"]), num(r["pass_rate_corrected"])
        moves.append((abs(b - a) if a is not None and b is not None else 0.0, r["arm"], a, b,
                      abs(pb - pa) * 100 if pa is not None and pb is not None else 0.0, pa, pb))
    moves.sort(reverse=True)
    rep.say()
    rep.say("largest moves of the reliability crossing (D99, as a difficulty percentage) with a correct extractor from the start:")
    for d, arm, a, b, dp, pa, pb in moves[:6]:
        rep.say(f"  {arm:<58} {a:6.2f}% -> {b:6.2f}%  ({d:+.2f} points); pass rate {pa:.1%} -> {pb:.1%}")
    rep.say(f"largest move of any arm's reliability crossing: {moves[0][0]:.2f} points of difficulty; of any pass rate: {max(m[4] for m in moves):.2f} points")
    bound = [r["arm"] for r in rows if num(r["d99_pct_as_judged"]) is None]
    rep.say(f"arms whose reliability crossing lies below the easiest task (no number to move): {len(bound)}")
    rep.say()
    rep.say(f"{'arm':<58}{'attempts':>9}{'wrong code':>12}{'false fail':>12}{'false pass':>12}")
    for r in sorted(rows, key=lambda r: -int(r["wrong_code_attempts"]) / int(r["attempts"]))[:10]:
        rep.say(f"{r['arm']:<58}{int(r['attempts']):>9}{int(r['wrong_code_attempts']) / int(r['attempts']):>12.2%}"
                f"{int(r['false_fail']) / int(r['attempts']):>12.2%}{int(r['false_pass']) / int(r['attempts']):>12.3%}")
    return rep.finish()


if __name__ == "__main__":
    sys.exit(main())
