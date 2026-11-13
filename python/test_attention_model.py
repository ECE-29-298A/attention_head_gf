"""Self-checks for the generalized chip model. Run: pytest python/"""
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent / "src"))
from attention_model import chip_attention, chip_attention_np, reg_widths  # noqa: E402


def test_widths_match_rtl():
    # Must match src/: score_mac S, accum L and O, divider quotient.
    # D is the value range of M - S; exp_lut computes it as an 18-bit S plus a sign bit.
    assert reg_widths(4, 16) == {"S": 18, "D": 17, "L": 12, "O": 20, "Z": 19}


def test_numpy_matches_python():
    rng = random.Random(298)
    for d in (4, 64):
        for shift in (0, 3, 9):
            for n in list(range(1, 17)) + [16] * 10:
                vec = lambda: [rng.randint(-128, 127) for _ in range(d)]
                q, K, V = vec(), [vec() for _ in range(n)], [vec() for _ in range(n)]
                want = chip_attention(q, K, V, score_shift=shift)
                got = chip_attention_np(np.array(q), np.array(K), np.array(V), shift)
                assert got.tolist() == want, (d, shift, n)


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
