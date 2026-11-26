"""Verify the integrated RTL controller; only memory/host behavior is modeled.

Runs at OUTPUTS = 8 (the chip), 4 and 2 unless --outputs picks some.
"""
import argparse
from pathlib import Path
import random
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "test"))
from rtl_sim import build, simulate

sys.path.insert(0, str(ROOT / "python/src"))
from attention_model import chip_attention, dot, exp_weight, tape


def encode_case(outputs, q, k, v, shift=0, chunks=(0,)):
    """Encode the tape and the Python model's intermediate results for RTL assertions.

    q: 64 ints, k and v: N rows of 64 ints. The chunks run in order: one fresh run, then continue runs.
    """
    scores = [dot(q, row) for row in k]
    weights = [exp_weight(max(scores), s, score_shift=shift) for s in scores]
    image = tape(q, k, v, chunks, outputs)
    fields = [len(k), shift, len(chunks), len(image)] + image + scores + weights
    for chunk in chunks:
        chunk_v = [row[outputs * chunk:outputs * (chunk + 1)] for row in v]
        fields.extend(sum(w * row[c] for w, row in zip(weights, chunk_v)) for c in range(outputs))
        fields.extend(chip_attention(q, k, chunk_v, score_shift=shift))  # signed 12-bit results
    return " ".join(str(x) for x in fields)


def vectors(outputs):
    rng = random.Random(298)
    vec = lambda lo=-128, hi=127: [rng.randint(lo, hi) for _ in range(64)]
    pad = lambda row: row + [0] * (64 - len(row))

    def at_chunk(rows, group):
        """4-wide V rows at components 4*group.., random bytes elsewhere (a wrong chunk shows up).

        Each directed case runs the chunks that hold them (2 runs at OUTPUTS=2, a continue run second).
        """
        out = []
        for row in rows:
            full = vec()
            full[4 * group:4 * group + 4] = row
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
    # Weights [255, 1] (D = 22) give denominator 256, so outputs are O / 16.
    # O = +/-8 and +/-264 are ties that round away from zero; neighbors test both sides.
    q, k = e1, [pad([7]), pad([-15])]
    cases += [(q, k, at_chunk([[0, 0, 0, 0], [8, -8, 7, -9]], 6), 0, 6),
              (q, k, at_chunk([[1, -1, 1, -1], [9, -9, 10, -10]], 14), 0, 14)]
    for q, k, v, shift, group in cases:
        yield encode_case(outputs, q, k, v, shift, sorted({(4 * group + i) // outputs for i in range(4)}))

    for n in range(1, 17):
        for _ in range(2):
            # Full-range INT8: score gaps up to ~10^5, so shifts 10..15 keep several weights alive.
            yield encode_case(outputs, vec(), [vec() for _ in range(n)], [vec() for _ in range(n)],
                              rng.randint(10, 15), rng.sample(range(64 // outputs), 3))
        for _ in range(2):
            # SmolLM-like small activations with mid-range shifts.
            yield encode_case(outputs, vec(-40, 40), [vec(-40, 40) for _ in range(n)], [vec() for _ in range(n)],
                              rng.randint(4, 12), [rng.randrange(64 // outputs)])
    yield encode_case(outputs, [0] * 64, [[0] * 64] * 16, [[0] * 64] * 16, 0)
    # A whole head: all 64 / OUTPUTS chunks from one pass 1.
    yield encode_case(outputs, vec(), [vec() for _ in range(16)], [vec() for _ in range(16)], 13,
                      range(64 // outputs))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outputs", type=int, nargs="+", choices=(2, 4, 8), default=[8, 4, 2])
    sources = ["test/controller/tb_controller.sv", "src/attention_controller.sv",
               "src/mac_unit.v", "src/ripple_add.v", "src/max_reg.v",
               "src/exp_lut.v", "src/divider.v"]
    with tempfile.TemporaryDirectory(prefix="attention-controller-") as temporary:
        work = Path(temporary)
        for outputs in parser.parse_args().outputs:
            build_dir = work / f"outputs{outputs}"
            build_dir.mkdir()
            data = build_dir / "vectors.txt"
            lines = list(vectors(outputs))
            data.write_text("\n".join(lines) + "\n")
            args = (f"+VECTORS={data}", f"+CASES={len(lines)}")
            current = build(build_dir, "tb_controller", sources, f"-GOUTPUTS={outputs}")
            # Different host-ready schedules supplement the deterministic Python input seed.
            for seed in (298, 2026, 16):
                simulate(current, *args, f"+verilator+seed+{seed}")

if __name__ == "__main__":
    main()
