#!/usr/bin/env python3
"""End-to-end vectors for sim/tb_e2e.sv (SPEC.md section 9), from the project's Python model
python/src/attention_model.py (tape layout, chip_attention reference results).

Each case line: N shift nchunks reset_at tape_len tape[...] then, per chunk, OUTPUTS expected
signed 12-bit results. reset_at > 0: the testbench first starts the case's fresh run and resets
the core at that SCK rise (mid-run abort), then runs the case from the start.
Usage: gen_vectors.py --outputs P --out FILE
"""
import argparse
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "python/src"))
from attention_model import chip_attention, tape  # noqa: E402


def case(outputs, q, k, v, shift, chunks, reset_at=0):
    image = tape(q, k, v, chunks, outputs)
    f = [len(k), shift, len(chunks), reset_at, len(image)] + image
    for c in chunks:
        f += chip_attention(q, k, [row[outputs * c:outputs * (c + 1)] for row in v], score_shift=shift)
    return " ".join(str(x) for x in f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outputs", type=int, default=8, choices=(2, 4, 8))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    P = a.outputs
    rng = random.Random(7)
    vec = lambda lo=-128, hi=127: [rng.randint(lo, hi) for _ in range(64)]
    lines = [
        # 1 token at the INT8 extremes: Q = K = -128 (score 2^20), V = -128 / 127 alternating
        case(P, [-128] * 64, [[-128] * 64], [[-128, 127] * 32], 0, [0]),
        # 2 random tokens, a fresh run then a continue run (the next chunk on the tape)
        case(P, vec(), [vec() for _ in range(2)], [vec() for _ in range(2)], 13, [0, 64 // P - 1]),
        # 3 tokens, small activations; first aborted by a reset in pass 2 (SCK rise 40 + 2*128*3 + 300)
        case(P, vec(-40, 40), [vec(-40, 40) for _ in range(3)], [vec() for _ in range(3)], 6, [1],
             reset_at=40 + 2 * 128 * 3 + 300),
    ]
    Path(a.out).write_text("\n".join(lines) + "\n")
    print(f"RESULT vectors outputs={P} cases={len(lines)} runs={sum(int(l.split()[2]) for l in lines)}")


if __name__ == "__main__":
    main()
