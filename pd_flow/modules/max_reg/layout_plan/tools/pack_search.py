#!/usr/bin/env python3
"""pack_search.py: exhaustive minimum-footprint search for the a_sdff block (D6, area first).
Model: footprint W sites x H rows on the chip grid; chip taps (2 sites, FIXED) at abs site 0 mod 70 in odd
rows and 35 mod 70 in even rows; the anchor site offset a = s0 mod 70 and anchor row parity decide the rel tap
sites. Cells (LEF site widths, census.json): sdffq_1 38, inv_1 4, nand2_1 5, nor2_1 6, aoi21_1/oai21_1 8;
decode = oai21_1 + 2 x inv_2 (8 + 6 + 6). Bits per row k in {1, 2, 3}: each row holds k bits (flop + compare
stage each; bit 0 has no stage, and its row may be any row); the three decode cells go together in one row. A row is feasible when its cells can
be assigned to its tap-free segments (exact subset packing). Output: every (W, H, k) at the minimum W*H that
has a feasible (a, parity), and the best few, as JSON."""
import itertools, json, sys
FF, STAGE, DEC = 38, [4, 5, 6, 8], [8, 6, 6]
N = 22


def segments(W, a, par):
    ph = 35 if par == 0 else 0           # even rows tap at 35 mod 70, odd at 0 mod 70
    blk = set()
    for s in range(-2, W + 2):
        if (a + s) % 70 == ph:
            blk |= {s, s + 1}
    segs, cur = [], 0
    for s in range(W):
        if s in blk:
            if cur: segs.append(cur)
            cur = 0
        else:
            cur += 1
    if cur: segs.append(cur)
    return segs, len([s for s in blk if 0 <= s < W])


def fits(items, segs):
    items = sorted(items, reverse=True)
    def rec(i, free):
        if i == len(items): return True
        seen = set()
        for j, f in enumerate(free):
            if f >= items[i] and f not in seen:
                seen.add(f)
                nf = list(free); nf[j] -= items[i]
                if rec(i + 1, nf): return True
        return False
    return rec(0, list(segs))


def row_items(k, j):
    it = []
    for b in range(k * j, min(N, k * j + k)):
        it.append(FF)
        if b: it += STAGE
    return it


def feasible(W, k, a, par):
    """Rows hold k bits each; the row holding bit 0 (one stage fewer) may be any row j0 (the bit order in
    the other rows is free: every full row has the same cell multiset). Decode goes in one row with it."""
    H = -(-N // k)
    full = row_items(k, 1)
    nfull = N - k * (H - 1)                      # bits in the last row group (k unless N % k)
    segs = [segments(W, a, (par + j) % 2)[0] for j in range(H)]
    sols = []
    for j0 in range(H):
        rows = []
        for j in range(H):
            if j == j0: it = row_items(k, 0)
            elif nfull < k and j == (H - 1 if j0 != H - 1 else H - 2): it = [FF] * nfull + STAGE * nfull
            else: it = full
            rows.append(it)
        if all(fits(rows[j], segs[j]) for j in range(H)):
            dec = [j for j in range(H) if fits(rows[j] + DEC, segs[j])]
            if dec: sols.append({"bit0_row": j0, "decode_rows_possible": dec})
    return {"bit0_rows": [x["bit0_row"] for x in sols], "decode_rows_possible": sorted({d for x in sols for d in x["decode_rows_possible"]})} if sols else None


res = []
for k, Ws in ((1, range(61, 76)), (2, range(122, 146)), (3, range(183, 200))):
    H = -(-N // k)
    for W in Ws:
        for a in range(70):
            for par in (0, 1):
                f = feasible(W, k, a, par)
                if f:
                    taps = sum(segments(W, a, (par + j) % 2)[1] for j in range(H))
                    res.append({"W": W, "H": H, "k": k, "a": a, "anchor_row_parity": par, "site_rows": W * H,
                                "taps_inside_sites": taps, **f})
        if any(r["W"] == W and r["k"] == k for r in res): break   # smallest W for this k found
res.sort(key=lambda r: (r["site_rows"], -r["taps_inside_sites"]))
cells_sites = N * FF + (N - 1) * sum(STAGE) + sum(DEC)
best = res[0]["site_rows"]
out = {"cell_sites": cells_sites, "best_site_rows": best,
       "best": [r for r in res if r["site_rows"] == best],
       "smallest_per_k": {k: min((r for r in res if r["k"] == k), key=lambda r: r["site_rows"]) for k in (1, 2, 3)
                          if any(r["k"] == k for r in res)}}
json.dump(out, open(sys.argv[1], "w") if len(sys.argv) > 1 else sys.stdout, indent=1)
print(json.dumps({"cell_sites": cells_sites, "best_site_rows": best, "n_best": len(out["best"]),
                  "first": out["best"][0], "smallest_per_k": out["smallest_per_k"]}, indent=1))
