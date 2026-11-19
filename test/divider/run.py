"""Check divider RTL against the actual Python divide_round function."""
from pathlib import Path
import random
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "test"))
sys.path.insert(0, str(ROOT / "python/src"))
from rtl_sim import build, simulate
from attention_model import divide_round


def cases():
    # Sweep every possible positive 12-bit denominator at INT8 ratio bounds,
    # zero, near zero, and representative rounding thresholds.
    for denominator in range(1, 4096):
        for value in sorted({-128*denominator, 127*denominator, 0, -1, 1,
                             denominator//2, denominator//2+1,
                             -(denominator//2), -(denominator//2+1)}):
            yield value, denominator, divide_round(value, denominator)
    # Every numerator in the INT8 worst-case accumulator interval at max L.
    for value in range(-128*4080, 127*4080 + 1):
        yield value, 4080, divide_round(value, 4080)
    # Every output rounding threshold, on both sides and exactly at the tie:
    # with L = 32 the output is round(O / 2), so odd O are ties.
    for magnitude_code in range(2049):
        for offset in (-1, 0, 1):
            value = 2*magnitude_code + 1 + offset
            for sign in (-1, 1):
                try:
                    expected = divide_round(sign*value, 32)
                except AssertionError:
                    continue
                yield sign*value, 32, expected
    rng = random.Random(298)
    for _ in range(10000):
        denominator = rng.randint(1, 4080)
        value = rng.randint(-128*denominator, 127*denominator)
        yield value, denominator, divide_round(value, denominator)
    # Invalid requests are outside the Python domain: RTL must complete with 0.
    # (4095, 32) and (-4097, 32) round to 2048 and -2049, just outside 12 bits.
    for value, denominator in [(0, 0), (123, 0), (-123, 0), (-524288, 4095),
                               (524287, 1), (-524287, 1), (256, 2), (-259, 2),
                               (4095, 32), (-4097, 32)]:
        yield value, denominator, 0


def main():
    with tempfile.TemporaryDirectory(prefix="attention-divider-") as directory:
        work = Path(directory)
        vectors = work / "vectors.txt"
        vectors.write_text("\n".join(f"{o} {l} {y}" for o, l, y in cases()) + "\n")
        binary = build(work, "tb_divider", ["test/divider/tb_divider.sv", "src/divider.v"])
        simulate(binary, f"+VECTORS={vectors}")


if __name__ == "__main__":
    main()
