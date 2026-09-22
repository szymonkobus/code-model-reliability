#!/usr/bin/env python3
"""Embedding: all-MiniLM-L6-v2 over prompt text. Statistic: mean of the top-5%
pairwise cosines over CROSS-FAMILY pairs. Reports, per batch:
  within_batch   - cross-family top-5% stat inside the batch
  batch_vs_pool  - same stat over batch x pool pairs
  pool_baseline  - the pool's own cross-family stat (all pool records are
                   family-less -> every pair is cross-family)
FLAG if within_batch > pool_baseline + 0.05 or batch_vs_pool > pool_baseline.

Usage: python embed_stats.py --pool pool_prompts.jsonl --batch b1.jsonl ... --out stats.json
"""

import argparse
import json

import numpy as np


def load(path):
    recs = []
    with open(path) as f:
        for line in f:
            r = json.loads(line)
            prov = r.get("provenance", {})
            fam = r.get("family_id") or prov.get("family_id")
            recs.append((r["task_id"], r["prompt"], fam,
                         prov.get("source_task_id")))
    return recs


def top5_mean(sims):
    if sims.size == 0:
        return None
    k = max(1, int(round(sims.size * 0.05)))
    return float(np.sort(sims.ravel())[-k:].mean())


def per_task_top5(row_sims):
    if row_sims.size == 0:
        return None
    k = max(1, int(round(row_sims.size * 0.05)))
    return float(np.sort(row_sims)[-k:].mean())


def cross_family_pairs_within(emb, fams):
    n = len(fams)
    iu = np.triu_indices(n, k=1)
    sims = emb @ emb.T
    mask = np.array([[fams[i] is None or fams[j] is None or fams[i] != fams[j]
                      for j in range(n)] for i in range(n)])
    return sims[iu][mask[iu]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", required=True)
    ap.add_argument("--batch", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    revision = getattr(getattr(model, "model_card_data", None),
                       "base_model_revision", None)

    pool = load(args.pool)
    pool_emb = model.encode([p for _, p, _, _ in pool],
                            normalize_embeddings=True, show_progress_bar=False)
    baseline = top5_mean(cross_family_pairs_within(
        np.asarray(pool_emb), [f for _, _, f, _ in pool]))

    # per-task baseline: each pool task's stat vs the rest of the pool
    pe = np.asarray(pool_emb)
    pool_sims = pe @ pe.T
    np.fill_diagonal(pool_sims, -2.0)
    pool_pertask = [per_task_top5(pool_sims[i]) for i in range(len(pool))]
    baseline_pertask = float(np.mean(pool_pertask))
    pertask_p95 = float(np.quantile(pool_pertask, 0.95))

    report = {"model": "sentence-transformers/all-MiniLM-L6-v2",
              "revision": revision, "pool_n": len(pool),
              "pool_baseline": baseline,
              "pool_baseline_pertask_mean": baseline_pertask,
              "pool_pertask_p95": pertask_p95, "batches": {}}
    pool_ids = [tid for tid, _, _, _ in pool]
    for bpath in args.batch:
        batch = load(bpath)
        b_emb = np.asarray(model.encode([p for _, p, _, _ in batch],
                                        normalize_embeddings=True,
                                        show_progress_bar=False))
        fams = [f for _, _, f, _ in batch]
        within = top5_mean(cross_family_pairs_within(b_emb, fams))
        sims = b_emb @ np.asarray(pool_emb).T
        keep = np.ones_like(sims, dtype=bool)
        for i, (_, _, _, src) in enumerate(batch):
            if src and src in pool_ids:
                keep[i, pool_ids.index(src)] = False
        vs_pool = top5_mean(sims[keep])
        # per-task vs-pool at the P95 anchor: flag-to-audit, neighbors attached
        masked = np.where(keep, sims, -2.0)
        pertask = {batch[i][0]: per_task_top5(masked[i])
                   for i in range(len(batch))}
        flagged = []
        for i in range(len(batch)):
            v = pertask[batch[i][0]]
            if v is not None and v > pertask_p95:
                nn = np.argsort(masked[i])[-3:][::-1]
                flagged.append({"task_id": batch[i][0], "stat": round(v, 4),
                                "nearest_pool": [pool_ids[j] for j in nn]})
        flag = (within is not None and within > baseline + 0.05) or \
               (vs_pool is not None and vs_pool > baseline)
        report["batches"][bpath] = {
            "n": len(batch), "within_batch": within,
            "batch_vs_pool": vs_pool, "flag": bool(flag),
            "pertask_p95_flag_rate": round(len(flagged) / max(1, len(batch)), 4),
            "pertask_p95_flagged": flagged,
            "pertask_vs_pool_max": (max(v for v in pertask.values()
                                        if v is not None)
                                    if pertask else None)}

    with open(args.out, "w") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
