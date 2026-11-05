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
from attention_model import chip_attention, dot4, exp_weight, pack_byte


def encode_case(q, k, v):
    """Encode Python-model outputs and intermediate results for RTL assertions."""
    scores = [dot4(q, row) for row in k]
    weights = [exp_weight(max(scores), s) for s in scores]
    fields = [len(k), sum((x & 15) << (4 * i) for i, x in enumerate(q))]
    for rows in (k, v):
        for row in rows:
            fields.extend([pack_byte(*row[:2]), pack_byte(*row[2:])])
    fields.extend(x & 255 for x in chip_attention(q, k, v))
    fields.extend(s & 65535 for s in scores)
    fields.extend(weights)
    return " ".join(str(x) for x in fields)


def vectors():
    rng = random.Random(298)
    # Single token, negative scores, all-equal scores, extrema, and lost tails.
    cases = [
        ([1, 0, 0, 0], [[-8, 0, 0, 0]], [[-8, -1, 0, 7]]),
        ([-8] * 4, [[-8] * 4] * 16, [[-8] * 4] * 16),
        ([-8] * 4, [[7] * 4] * 16, [[7] * 4] * 16),
        ([0] * 4, [[0] * 4] * 2, [[0] * 4, [1] * 4]),
        ([1, 0, 0, 0], [[7, 0, 0, 0]] + [[-6, 0, 0, 0]] * 15,
         [[-8] * 4] + [[7] * 4] * 15),
        # The final key changes the maximum: no exponent may run prematurely.
        ([1, 0, 0, 0], [[x, 0, 0, 0] for x in range(-8, 8)],
         [[-8, 7, -1, 1] if x % 2 else [7, -8, 1, -1] for x in range(16)]),
        ([1, 0, 0, 0], [[-7, 0, 0, 0], [-5, 0, 0, 0], [-1, 0, 0, 0]],
         [[-8, 7, 0, 1], [7, -8, 1, 0], [-1, 1, -8, 7]]),
    ]
    for n in range(1, 17):
        for _ in range(8):
            vec = lambda: [rng.randint(-8, 7) for _ in range(4)]
            cases.append((vec(), [vec() for _ in range(n)], [vec() for _ in range(n)]))
    for q, k, v in cases:
        yield encode_case(q, k, v)

    # Weights [255, 1] give denominator 256. O=+/-248 rounds +/-15.5
    # away from zero; neighboring sums test both sides of the tie.
    q, k = [1, 0, 0, 0], [[7, 0, 0, 0], [-4, 0, 0, 0]]
    yield encode_case(q, k, [[1, -1, 0, 0], [-7, 7, 0, 0]])
    yield encode_case(q, k, [[1, -1, 1, -1], [-8, 6, -6, 7]])
    yield encode_case([0]*4, [[0]*4]*16, [[0]*4]*16)


def main():
    sources = ["test/controller/tb_controller.sv", "src/attention_controller.sv",
               "src/score_mac.v", "src/max_reg.v", "src/accum.v",
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
