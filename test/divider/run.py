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
    # Sweep every possible positive 12-bit denominator at INT4 ratio bounds,
    # zero, near zero, and representative rounding thresholds.
    for denominator in range(1, 4096):
        for value in sorted({-8*denominator, 7*denominator, 0, -1, 1,
                             denominator//32, denominator//32+1,
                             -(denominator//32), -(denominator//32+1)}):
            yield value, denominator, divide_round(value, denominator)
    # Every numerator in the INT4 worst-case accumulator interval at max L.
    for value in range(-32640, 28561):
        yield value, 4080, divide_round(value, 4080)
    # Every output rounding threshold, on both sides and exactly at the tie.
    for magnitude_code in range(128):
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
        value = rng.randint(-8*denominator, 7*denominator)
        yield value, denominator, divide_round(value, denominator)
    # Invalid requests are outside the Python domain: RTL must complete with 0.
    for value, denominator in [(0, 0), (123, 0), (-123, 0), (-32768, 4095),
                               (32767, 1), (-32767, 1), (255, 32)]:
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
