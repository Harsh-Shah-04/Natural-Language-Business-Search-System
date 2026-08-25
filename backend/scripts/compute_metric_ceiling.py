import sys, collections
sys.path.insert(0, "backend")
sys.path.insert(0, "backend/scripts")
from eval_dataset import GOLDEN_QUERIES

K = 5
rows = []
for gq in GOLDEN_QUERIES:
    n_rel = len(gq["expected_relevant"])
    # precision_at_k divides by len(top_k) == K (corpus is 120, always >= 5 results)
    p_ceiling = min(n_rel, K) / K
    # recall_at_k returns None when n_rel == 0 and is excluded from means
    r_ceiling = None if n_rel == 0 else min(n_rel, K) / n_rel
    rows.append((gq["category"], gq["id"], n_rel, p_ceiling, r_ceiling))

by_cat = collections.defaultdict(list)
for c, i, n, p, r in rows:
    by_cat[c].append((i, n, p, r))

print(f"{'category':<14} {'n':>3} {'maxP@5':>8} {'maxR@5':>8}")
print("-" * 38)
allp = []
for cat in sorted(by_cat):
    items = by_cat[cat]
    ps = [p for _, _, p, _ in items]
    rs = [r for _, _, _, r in items if r is not None]
    allp += ps
    print(f"{cat:<14} {len(items):>3} {sum(ps)/len(ps):>8.4f} {(sum(rs)/len(rs) if rs else float('nan')):>8.4f}")
print("-" * 38)
print(f"{'OVERALL':<14} {len(allp):>3} {sum(allp)/len(allp):>8.4f}")
print()
print("Queries with zero relevant docs (precision pinned at 0.0, averaged IN):")
for c, i, n, p, r in rows:
    if n == 0:
        print(f"  {i} ({c})")
print()
print("Actual hybrid-rerank from report_20260720_200803.md: P@5 = 0.560")
print(f"Ceiling                                            : P@5 = {sum(allp)/len(allp):.4f}")
print(f"Headroom                                           :       {sum(allp)/len(allp) - 0.560:.4f}")
print(f"Percent of ceiling achieved                        :       {0.560/(sum(allp)/len(allp))*100:.1f}%")
