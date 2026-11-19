"""Verify the integrated RTL controller; only memory/host behavior is modeled."""
from pathlib import Path
import random
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "test"))
from rtl_sim import build, simulate

sys.path.insert(0, str(ROOT / "python/src"))
from attention_model import chip_attention, dot, exp_weight, pack_byte


def encode_case(q, k, v, shift=0, chunk=0):
    """Encode Python-model outputs and intermediate results for RTL assertions.

    q: 64 ints, k and v: N rows of 64 ints. The chip outputs V chunk `chunk`.
    """
    scores = [dot(q, row) for row in k]
    weights = [exp_weight(max(scores), s, score_shift=shift) for s in scores]
    fields = [len(k), shift, chunk] + [pack_byte(x) for x in q]
    for rows in (k, v):
        for row in rows:
            fields.extend(pack_byte(x) for x in row)
    chunk_v = [row[4 * chunk:4 * chunk + 4] for row in v]
    fields.extend(chip_attention(q, k, chunk_v, score_shift=shift))  # signed 12-bit results
    fields.extend(scores)
    fields.extend(weights)
    return " ".join(str(x) for x in fields)


def vectors():
    rng = random.Random(298)
    vec = lambda lo=-128, hi=127: [rng.randint(lo, hi) for _ in range(64)]
    pad = lambda row: row + [0] * (64 - len(row))

    def at_chunk(rows, chunk):
        """4-wide V rows placed at `chunk`, random bytes elsewhere (a wrong chunk shows up)."""
        out = []
        for row in rows:
            full = vec()
            full[4 * chunk:4 * chunk + 4] = row
            out.append(full)
        return out

    e1 = [1] + [0] * 63
    cases = [
        # Single token, signed extremes.
        (e1, [pad([-128])], at_chunk([[-128, -1, 0, 127]], 0), 0, 0),
        # Largest and smallest 64-dim scores (+/-2^20); all scores equal.
        ([-128] * 64, [[-128] * 64] * 16, at_chunk([[-128] * 4] * 16, 15), 15, 15),
        ([-128] * 64, [[127] * 64] * 16, at_chunk([[127] * 4] * 16, 7), 0, 7),
        # Largest possible D (2088960) at every relevant shift: only shift 15 gets near the table.
        *[([-128] * 64, [[-128] * 64, [127] * 64], at_chunk([[1, 2, 3, 4], [-128, 127, -1, 1]], 3), s, 3)
          for s in (0, 14, 15)],
        ([0] * 64, [[0] * 64] * 2, at_chunk([[0] * 4, [1] * 4], 1), 0, 1),
        # D = 25 at shift 0: the tail tokens get weight 0.
        (e1, [pad([7])] + [pad([-18])] * 15, at_chunk([[-128] * 4] + [[127] * 4] * 15, 2), 0, 2),
        # The final key changes the maximum: no exponent may run prematurely.
        (e1, [pad([x]) for x in range(-8, 8)],
         at_chunk([[-128, 127, -1, 1] if x % 2 else [127, -128, 1, -1] for x in range(16)], 9), 0, 9),
        # Rounded shift at shift 3: D = 19, 20, 21 round to 2, 3 (tie, half up), 3;
        # truncating would give 2, 2, 2.
        (e1, [pad([0]), pad([-19]), pad([-20]), pad([-21])],
         at_chunk([[1, 2, 3, 4], [-128, 127, 0, 0], [0, 0, -128, 127], [64, -64, 32, -32]], 4), 3, 4),
        # Same ties spread over all 64 components with shift 5.
        ([1] * 64, [[0] * 64, [-1] * 48 + [0] * 16, [-1] * 47 + [0] * 17, [-1] * 49 + [0] * 15],
         at_chunk([[5, -5, 100, -100], [-128, 127, 0, 0], [0, 0, -128, 127], [64, -64, 32, -32]], 12), 5, 12),
    ]
    for n in range(1, 17):
        for _ in range(2):
            # Full-range INT8: score gaps up to ~10^5, so shifts 10..15 keep several weights alive.
            cases.append((vec(), [vec() for _ in range(n)], [vec() for _ in range(n)],
                          rng.randint(10, 15), rng.randrange(16)))
        for _ in range(2):
            # SmolLM-like small activations with mid-range shifts.
            cases.append((vec(-40, 40), [vec(-40, 40) for _ in range(n)], [vec() for _ in range(n)],
                          rng.randint(4, 12), rng.randrange(16)))
    for q, k, v, shift, chunk in cases:
        yield encode_case(q, k, v, shift, chunk)

    # Weights [255, 1] (D = 22) give denominator 256, so outputs are O / 16.
    # O = +/-8 and +/-264 are ties that round away from zero; neighbors test both sides.
    q, k = e1, [pad([7]), pad([-15])]
    yield encode_case(q, k, at_chunk([[0, 0, 0, 0], [8, -8, 7, -9]], 6), 0, 6)
    yield encode_case(q, k, at_chunk([[1, -1, 1, -1], [9, -9, 10, -10]], 14), 0, 14)
    yield encode_case([0] * 64, [[0] * 64] * 16, [[0] * 64] * 16, 0, 0)


def main():
    sources = ["test/controller/tb_controller.sv", "src/attention_controller.sv",
               "src/score_mac.v", "src/ripple_add.v", "src/max_reg.v", "src/accum.v",
               "src/exp_lut.v", "src/divider.v"]
    with tempfile.TemporaryDirectory(prefix="attention-controller-") as temporary:
        work = Path(temporary)
        data = work / "vectors.txt"
        lines = list(vectors())
        data.write_text("\n".join(lines) + "\n")
        args = (f"+VECTORS={data}", f"+CASES={len(lines)}")
        current = build(work, "tb_controller", sources)
        # Different schedules supplement the deterministic Python input seed.
        for seed in (298, 2026, 16):
            simulate(current, *args, f"+verilator+seed+{seed}")
        for latency in (2, 8, 32):
            simulate(current, *args, f"+MEM_CYCLES={latency}")
        # Exercise the controller's memory-base parameters outside the default map.
        relocated = work / "relocated"
        relocated.mkdir()
        current = build(relocated, "tb_controller", sources, "-GTEST_Q_BASE=16'h0800",
                        "-GTEST_K_BASE=16'h1200", "-GTEST_V_BASE=16'h3400")
        simulate(current, *args, "+verilator+seed+298")


if __name__ == "__main__":
    main()
