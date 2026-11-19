"""Compare the chip model against SmolLM's float attention on real Q/K/V.

Input: build/smollm_attention.npz from smollm_extract.py. Every (prompt, layer,
head, position) is one attention query with N = position + 1 keys (causal).

Two ways to run a 64-dim SmolLM head:
  chip today    current d=4 RTL. The host computes q·k/8 in float and sends it in
                one lane as whole score units: Q=[1,0,0,0], K_t=[s_t,0,0,0]
  step 2 chip   proposed RTL: INT8 q·k over all 64 dims, D >> score_shift
V's 64 dims are 16 independent 4-wide chip queries; per-dim math is identical,
so one 64-wide call computes all 16 at once.

Each runs as built, then with the accuracy fixes added one at a time:
  1. per-channel V scales (host only)  2. 0.25-nat LUT  3. 4 fractional output bits

Run: .venv/bin/python python/smollm_compare.py
"""
import argparse
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).parent / "src"))
from attention_model import chip_attention, chip_attention_np, quantize  # noqa: E402

AS_BUILT = dict(per_channel=False, lut_res=2, out_frac=0)
FIXES = [("+ 1. per-channel V", dict(per_channel=True)),
         ("+ 2. 0.25-nat LUT", dict(lut_res=4)),
         ("+ 3. 4 output frac bits", dict(out_frac=4))]


def run(q, k, v, step2, per_channel, lut_res, out_frac):
    """Chip estimate of every attention output. Returns (codes, scale): est = codes * scale."""
    group = q.shape[2] // k.shape[2]
    T, d = q.shape[-2:]
    # shortcut: K/V scales see all 16 tokens, incl. future ones; a real decoder
    # would fix scales from calibration. Fine for measuring the arithmetic.
    qi, eq = quantize(q, axis=-1)                       # one scale per query vector
    ki, ek = (np.repeat(a, group, axis=2) for a in quantize(k, axis=(-2, -1)))
    vi, ev = (np.repeat(a, group, axis=2)
              for a in quantize(v, axis=-2 if per_channel else (-2, -1)))
    scores = np.einsum("...td,...sd->...ts", q, np.repeat(k, group, axis=2)) / np.sqrt(d)
    log_res = lut_res.bit_length() - 1
    assert 1 << log_res == lut_res, "lut_res must be a power of two for score_shift"

    codes = np.zeros(q.shape, dtype=np.int64)
    lane = np.array([1, 0, 0, 0])
    for p in range(T):
        n = p + 1
        if step2:
            # q·k_int · 2^-(eq+ek) / 8 nats = that · 2^-(eq+ek+3-log2 lut_res) chip units
            shift = eq[..., p, :] + ek[..., 0, :] + 3 - log_res
            assert (shift >= 0).all(), "negative score_shift: inputs larger than INT8 range"
            args = (qi[..., p, :], ki[..., :n, :], vi[..., :n, :], shift)
        else:
            units = np.round(lut_res * scores[..., p, :n])          # 1 unit = 1/lut_res nat
            units = np.clip(units - units.max(-1, keepdims=True) + 127, -128, 127)
            k_lane = np.zeros(units.shape + (4,), dtype=np.int64)
            k_lane[..., 0] = units
            args = (lane, k_lane, vi[..., :n, :], 0)
        codes[..., p, :] = chip_attention_np(*args[:3], score_shift=args[3],
                                             lut_res=lut_res, out_frac=out_frac)

    # Spot check one real head, last position, against the scalar model and its
    # width checks: as 16 real 4-wide chip queries today, one 64-wide query in step 2.
    i = (0, 14, 4)
    Q, K, V, shift = args
    Q, K, V = (Q[i] if step2 else Q), K[i], V[i]
    opts = dict(score_shift=int(shift[i][0]) if step2 else 0, lut_res=lut_res, out_frac=out_frac)
    if step2:
        got = chip_attention(Q.tolist(), K.tolist(), V.tolist(), **opts)
    else:
        got = sum((chip_attention(Q.tolist(), K.tolist(), V[:, c:c + 4].tolist(), **opts)
                   for c in range(0, d, 4)), [])
    assert got == codes[i][-1].tolist(), "numpy and scalar models differ"

    return codes, 2.0 ** -ev / 2**out_frac


def stats(est, ref, lsb):
    """Per 64-dim output vector: relative L2 error, cosine; per element: error in V LSBs."""
    rel = np.linalg.norm(est - ref, axis=-1) / np.linalg.norm(ref, axis=-1)
    cos = (est * ref).sum(-1) / (np.linalg.norm(est, axis=-1) * np.linalg.norm(ref, axis=-1))
    err = np.abs(est - ref) / lsb
    return (f"{rel.mean():.3f} | {np.median(rel):.3f} | {np.percentile(rel, 99):.3f} | "
            f"{cos.mean():.4f} | {err.mean():.2f} | {np.percentile(err, 99):.2f}")


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=root / "build/smollm_attention.npz")
    args = parser.parse_args()
    data = np.load(args.data)
    q, k, v, ref = (data[n].astype(np.float64) for n in ("q", "k", "v", "out"))
    group = q.shape[2] // k.shape[2]
    # Error unit: one INT8 step of the head's shared V scale, the same for every row.
    lsb = np.repeat(2.0 ** -quantize(v, axis=(-2, -1))[1], group, axis=2)

    print(f"{ref.size // q.shape[-1]} attention outputs: {q.shape[0]} prompts x "
          f"{q.shape[1]} layers x {q.shape[2]} heads x N=1..{q.shape[-2]}\n")
    print("| Chip | rel err mean | median | p99 | cos mean | err LSB mean | p99 |")
    print("|---|---|---|---|---|---|---|")
    for step2, title in ((False, "chip today"), (True, "step 2 chip")):
        opts = dict(AS_BUILT)
        for name, change in [("as built", {})] + FIXES:
            opts.update(change)
            codes, scale = run(q, k, v, step2, **opts)
            print(f"| {title} {name} | {stats(codes * scale, ref, lsb)} |")


if __name__ == "__main__":
    main()
