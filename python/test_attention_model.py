"""Self-checks for the generalized chip model. Run: pytest python/"""
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent / "src"))
from attention_model import (chip_attention, chip_attention_np, exp_table,  # noqa: E402
                             quantize, reg_widths)


def test_widths_match_rtl():
    # Must match src/: score_mac S, accum L and O, divider quotient.
    # D is the value range of M - S; exp_lut computes it as an 18-bit S plus a sign bit.
    assert reg_widths(4, 16) == {"S": 18, "D": 17, "L": 12, "O": 20, "Z": 19}


def test_numpy_matches_python():
    rng = random.Random(298)
    for d in (4, 64):
        for shift in (0, 3, 9):
            for lut_res, out_frac in ((2, 0), (4, 4)):  # the chip, and fixes 2 + 3
                for n in list(range(1, 17)) + [16] * 10:
                    vec = lambda: [rng.randint(-128, 127) for _ in range(d)]
                    q, K, V = vec(), [vec() for _ in range(n)], [vec() for _ in range(n)]
                    opts = dict(score_shift=shift, lut_res=lut_res, out_frac=out_frac)
                    want = chip_attention(q, K, V, **opts)
                    got = chip_attention_np(np.array(q), np.array(K), np.array(V), **opts)
                    assert got.tolist() == want, (d, shift, lut_res, out_frac, n)


def test_numpy_batches_and_extremes():
    rng = np.random.default_rng(298)
    q = rng.integers(-128, 128, size=(3, 5, 64))
    K = rng.integers(-128, 128, size=(3, 5, 16, 64))
    V = rng.integers(-128, 128, size=(3, 5, 16, 64))
    K[0, 0], V[0, 0], q[0, 0] = -128, -128, -128  # largest score and |O|
    out = chip_attention_np(q, K, V, score_shift=4)
    assert out.shape == (3, 5, 64)
    for b in range(3):
        for h in range(5):
            assert out[b, h].tolist() == chip_attention(
                q[b, h].tolist(), K[b, h].tolist(), V[b, h].tolist(), score_shift=4)


def test_exp_tables():
    # lut_res = 2 is what exp_lut.v stores; 4 is the finer table (fix 2).
    assert exp_table(2) == [255, 155, 94, 57, 35, 21, 13, 8, 5, 3, 2, 1, 1]
    fine = exp_table(4)
    assert len(fine) == 25 and fine[::2] == [round(255 * np.exp(-D / 2)) for D in range(13)]


def test_out_frac_extremes():
    # Fix 3: 4 fractional bits make outputs INT12; the extremes still fit.
    one, lo = [[1, 0, 0, 0]], [[-128, 127, 0, 1]]
    assert chip_attention([1, 0, 0, 0], one, lo, out_frac=4) == [-2048, 2032, 0, 16]


def test_per_channel_quantize():
    # Fix 1: an outlier column no longer flattens the others.
    v = np.array([[18.0, 0.5], [-9.0, -0.25]])
    vi, e = quantize(v, axis=-2)
    assert vi[:, 1].tolist() == [64, -32] and np.allclose(vi * 2.0**-e, v)
    shared, _ = quantize(v, axis=(-2, -1))
    assert shared[:, 1].tolist() == [2, -1]  # 32x coarser
