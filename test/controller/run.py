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


def encode_case(q, k, v):
    """Encode Python-model outputs and intermediate results for RTL assertions."""
    scores = [dot(q, row) for row in k]
    weights = [exp_weight(max(scores), s) for s in scores]
    fields = [len(k), sum(pack_byte(x) << (8 * i) for i, x in enumerate(q))]
    for rows in (k, v):
        for row in rows:
            fields.extend(pack_byte(x) for x in row)
    fields.extend(chip_attention(q, k, v))  # signed 12-bit results
    fields.extend(scores)
    fields.extend(weights)
    return " ".join(str(x) for x in fields)


def vectors():
    rng = random.Random(298)
    # Single token, negative scores, all-equal scores, extrema, and lost tails.
    cases = [
        ([1, 0, 0, 0], [[-128, 0, 0, 0]], [[-128, -1, 0, 127]]),
        ([-128] * 4, [[-128] * 4] * 16, [[-128] * 4] * 16),
        ([-128] * 4, [[127] * 4] * 16, [[127] * 4] * 16),
        ([0] * 4, [[0] * 4] * 2, [[0] * 4, [1] * 4]),
        ([1, 0, 0, 0], [[7, 0, 0, 0]] + [[-18, 0, 0, 0]] * 15,  # D = 25: weight 0
         [[-128] * 4] + [[127] * 4] * 15),
        # The final key changes the maximum: no exponent may run prematurely.
        ([1, 0, 0, 0], [[x, 0, 0, 0] for x in range(-8, 8)],
         [[-128, 127, -1, 1] if x % 2 else [127, -128, 1, -1] for x in range(16)]),
        ([1, 0, 0, 0], [[-7, 0, 0, 0], [-5, 0, 0, 0], [-1, 0, 0, 0]],
         [[-128, 127, 0, 1], [127, -128, 1, 0], [-1, 1, -128, 127]]),
        # Small Q x K spread so several weights are nonzero with full-range V.
        ([1, 1, 0, 0], [[x, -x // 2, 0, 0] for x in range(16)],
         [[(37 * x) % 256 - 128, 127 - 16 * x, -128 + 16 * x, x] for x in range(16)]),
    ]
    for n in range(1, 17):
        for _ in range(8):
            vec = lambda: [rng.randint(-128, 127) for _ in range(4)]
            cases.append((vec(), [vec() for _ in range(n)], [vec() for _ in range(n)]))
    for q, k, v in cases:
        yield encode_case(q, k, v)

    # Weights [255, 1] (D = 22) give denominator 256, so outputs are O / 16.
    # O = +/-8 and +/-264 are ties that round away from zero; neighbors test both sides.
    q, k = [1, 0, 0, 0], [[7, 0, 0, 0], [-15, 0, 0, 0]]
    yield encode_case(q, k, [[0, 0, 0, 0], [8, -8, 7, -9]])
    yield encode_case(q, k, [[1, -1, 1, -1], [9, -9, 10, -10]])
    yield encode_case([0]*4, [[0]*4]*16, [[0]*4]*16)


def main():
    sources = ["test/controller/tb_controller.sv", "src/attention_controller.sv",
               "src/score_mac.v", "src/ripple_add.v", "src/max_reg.v", "src/accum.v",
               "src/exp_lut.v", "src/divider.v"]
    with tempfile.TemporaryDirectory(prefix="attention-controller-") as temporary:
        work = Path(temporary)
        data = work / "vectors.txt"
        data.write_text("\n".join(vectors()) + "\n")
        current = build(work, "tb_controller", sources)
        # Different schedules supplement the deterministic Python input seed.
        for seed in (298, 2026, 16):
            simulate(current, f"+VECTORS={data}", f"+verilator+seed+{seed}")
        for latency in (2, 8, 32):
            simulate(current, f"+VECTORS={data}", f"+MEM_CYCLES={latency}")
        # Exercise the controller's memory-base parameters outside the default map.
        relocated = work / "relocated"
        relocated.mkdir()
        current = build(relocated, "tb_controller", sources,
                        "-GTEST_K_BASE=16'h1200", "-GTEST_V_BASE=16'h3400")
        simulate(current, f"+VECTORS={data}", "+verilator+seed+298")


if __name__ == "__main__":
    main()
