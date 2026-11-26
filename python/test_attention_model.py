"""Self-checks for the generalized chip model. Run: pytest python/"""
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent / "src"))
from attention_model import (chip_attention, chip_attention_np, config_frame,  # noqa: E402
                             decode_result_frame, exp_table, quantize, reg_widths, tape,
                             v_planes)


def test_widths_match_rtl():
    # Must match src/: mac_unit S, L and O, divider quotient.
    # D is the value range of M - S; mac_unit's pass-2 S register holds it.
    assert reg_widths(64, 16) == {"S": 22, "D": 21, "L": 12, "O": 20, "Z": 19}


def test_numpy_matches_python():
    rng = random.Random(298)
    for d in (4, 64):
        for shift in (0, 3, 9):
            for lut_res, out_frac, rnd in ((2, 0, False), (4, 4, False), (4, 4, True)):
                for n in list(range(1, 17)) + [16] * 10:
                    vec = lambda: [rng.randint(-128, 127) for _ in range(d)]
                    q, K, V = vec(), [vec() for _ in range(n)], [vec() for _ in range(n)]
                    opts = dict(score_shift=shift, lut_res=lut_res, out_frac=out_frac,
                                score_round=rnd)
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


def test_score_round():
    # D = 6 >> 2: down gives 1, nearest gives 2 (1.5 rounds up); D = 5 >> 2 = 1.25 -> 1.
    from attention_model import exp_weight
    assert exp_weight(6, 0, score_shift=2, score_round=False) == exp_weight(1, 0)
    assert exp_weight(6, 0, score_shift=2, score_round=True) == exp_weight(2, 0)
    assert exp_weight(5, 0, score_shift=2, score_round=True) == exp_weight(1, 0)
    assert exp_weight(6, 0, score_round=True) == exp_weight(6, 0)  # no-op without a shift


def test_narrow_v():
    # The chip: 64-dim Q/K, one 8-wide V chunk; equals the same chunk of a 64-wide V.
    rng = np.random.default_rng(64)
    q, K, V = rng.integers(-128, 128, 64), rng.integers(-128, 128, (16, 64)), rng.integers(-128, 128, (16, 64))
    full = chip_attention_np(q, K, V, score_shift=12)
    for c in (0, 3, 7):
        chunk = V[:, 8 * c:8 * c + 8]
        assert chip_attention(q.tolist(), K.tolist(), chunk.tolist(), score_shift=12) == full[8 * c:8 * c + 8].tolist()


def test_spi_frames():
    assert config_frame(16, 15, 1) == 0x01FF
    assert config_frame(1, 0, 0) == 0
    assert config_frame(5, 9, 0) == 0x0094
    for value in range(-2048, 2048):
        assert decode_result_frame((value & 0xFFF) << 4) == value


def test_v_planes_bit_order():
    # 2 components: a7 b7 a6 b6 ... a0 b0.
    assert v_planes([-128, 0]) == [0x80, 0x00]
    assert v_planes([0, -1]) == [0x55, 0x55]
    assert v_planes([0x0F, -16]) == [0x55, 0xAA]  # a = 0000_1111, b = 1111_0000
    # 8 components: one byte per bit plane, component 0 in the MSB.
    assert v_planes([-128] + [0] * 7) == [0x80] + [0] * 7
    assert v_planes([0] * 7 + [1]) == [0] * 7 + [0x01]
    assert v_planes([-1, 0, 0, 0, 0, 0, 0, 0]) == [0x80] * 8
    rng = random.Random(8)
    for n in (2, 4, 8):
        for _ in range(200):
            vals = [rng.randint(-128, 127) for _ in range(n)]
            word = int.from_bytes(bytes(v_planes(vals)), "big")
            bits = [word >> (8 * n - 1 - i) & 1 for i in range(8 * n)]
            for c, v in enumerate(vals):  # bit i of the stream is bit 7 - i // n of component i % n
                assert sum(bit << (7 - i) for i, bit in enumerate(bits[c::n])) == v & 0xFF


def test_tape_layout():
    rng = random.Random(3)
    n = 3
    Q = [rng.randint(-128, 127) for _ in range(64)]
    K = [[rng.randint(-128, 127) for _ in range(64)] for _ in range(n)]
    V = [[rng.randint(-128, 127) for _ in range(64)] for _ in range(n)]
    rows = [[x & 0xFF for pair in zip(Q, k) for x in pair] for k in K]
    for outputs in (2, 4, 8):
        image = tape(Q, K, V, outputs=outputs)
        chunks = 64 // outputs
        assert len(image) == 128 * n * (1 + chunks) + outputs * n * chunks
        assert image[:128 * n] == sum(rows, [])
        block = 128 * n + n * outputs
        for c in (0, chunks - 1):
            for t in range(n):
                at = 128 * n + c * block + t * (128 + outputs)
                assert image[at:at + 128] == rows[t]
                assert image[at + 128:at + 128 + outputs] == v_planes(V[t][outputs * c:outputs * (c + 1)])
        assert tape(Q, K, V, [2, 0], outputs) == image[:128 * n] + image[128 * n + 2 * block:128 * n + 3 * block] \
            + image[128 * n:128 * n + block]
