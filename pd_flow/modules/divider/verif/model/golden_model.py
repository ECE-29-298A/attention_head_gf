#!/usr/bin/env python3
"""Independent golden model of the divider (SPEC.md section 1), exact integer arithmetic.

    result = round(16 * S / L), nearest, ties away from zero, signed 12-bit

computed as  m = floor((32*|S| + L) / (2*L))  (= floor(16|S|/L + 1/2), the round-half-up of the
magnitude), result = sign(S) * m. No divmod/remainder test as in the RTL or in the project model.
A second formulation with fractions.Fraction is used in the self-test.

Validity (SPEC S3): L != 0, S != -2^19, and the rounded value in range (m <= 2047 for S >= 0,
m <= 2048 for S < 0). CHECK_INVALID = 1: an invalid request gives 0. CHECK_INVALID = 0: the
result is specified only for valid requests (the caller's guarantee, SPEC A2-A4); outside it
the model returns None (don't care).

Commands:
  selftest                      KATs, second formulation, project-model agreement (R20)
  edges --random N --seed K --out FILE
                                edge-case and spot-check points for sim/tb_edge.sv and
                                sim/tb_ref.sv: one line per point "S L e00 e11 class flags",
                                e00 = expected result at 0/0 or 'x' (outside the domain),
                                e11 = expected result at 1/1 (always defined)
"""
import argparse
import random
import sys
from fractions import Fraction
from pathlib import Path

SMIN, SMAX = -(1 << 19), (1 << 19) - 1      # sum_in, signed 20-bit
LMAX = (1 << 12) - 1                         # denominator, unsigned 12-bit
RMIN, RMAX = -(1 << 11), (1 << 11) - 1       # result, signed 12-bit


def magnitude(s: int, l: int) -> int:
    """m = round_half_up(16|s|/l), exact integers; l > 0."""
    return (32 * abs(s) + l) // (2 * l)


def valid(s: int, l: int) -> bool:
    if l == 0 or s == SMIN:
        return False
    m = magnitude(s, l)
    return m <= (2048 if s < 0 else 2047)


def model(s: int, l: int, check_invalid: int):
    assert SMIN <= s <= SMAX and 0 <= l <= LMAX
    if not valid(s, l):
        return 0 if check_invalid else None
    m = magnitude(s, l)
    return -m if s < 0 else m


def model_fraction(s: int, l: int):
    """Second formulation: Fraction, round half away from zero by definition."""
    x = Fraction(16 * s, l)
    a = abs(x)
    n = int(a)                     # floor of the magnitude
    if a - n >= Fraction(1, 2):
        n += 1
    return -n if x < 0 else n


def selftest() -> int:
    errs = 0

    def chk(cond, msg):
        nonlocal errs
        if not cond:
            errs += 1
            print("FAIL", msg)

    # hand-derived known answers (S, L, expected at 1/1)
    kat = [(0, 1, 0), (1, 1, 16), (-1, 1, -16), (1, 32, 1), (-1, 32, -1),      # 0.5 ties away
           (1, 33, 0), (-1, 33, 0), (3, 32, 2), (-3, 32, -2),                    # 1.5 -> 2
           (100, 255, 6), (-100, 255, -6), (127 * 255, 255, 2032), (-128 * 255, 255, -2048),
           (4095, 32, 0), (-4097, 32, 0), (4093, 32, 2047), (-4095, 32, -2048),  # range edges
           (127, 1, 2032), (128, 1, 2048 * 0), (-128, 1, -2048), (-129, 1, 0),
           (SMAX, LMAX, 2048 * 0), (SMAX, 4095, 0), (130303, 4095, 509), (-524287, 4095, -2048),
           (0, 0, 0), (5, 0, 0), (SMIN, 4095, 0), (SMIN, 1, 0)]
    # (S, 4095): 16*524287/4095 = 2048.5 -> 2049 out of range; 16*(-524287)/4095 = -2048.49 -> -2048
    for s, l, e in kat:
        chk(model(s, l, 1) == e, f"KAT {s}/{l}: model {model(s, l, 1)} expected {e}")
    chk(model(130303, 4095, 0) == 509, "KAT 0/0 in domain")
    chk(model(0, 0, 0) is None and model(SMIN, 5, 0) is None and model(SMAX, 1, 0) is None,
        "0/0 outside the domain is None")
    nkat = len(kat) + 2
    # second formulation on every L for a few S, plus random points
    rng = random.Random(11)
    n2 = 0
    pts = [(s, l) for l in range(1, LMAX + 1) for s in (0, 1, -1, l // 2, -(l // 2), 127 * l // 16, -8 * l)]
    pts += [(rng.randint(SMIN + 1, SMAX), rng.randint(1, LMAX)) for _ in range(50000)]
    for s, l in pts:
        if not (SMIN <= s <= SMAX):
            continue
        n2 += 1
        f = model_fraction(s, l)
        in_range = RMIN <= f <= RMAX
        chk(valid(s, l) == (in_range and s != SMIN), f"validity {s}/{l}")
        if in_range and s != SMIN:
            chk(model(s, l, 0) == f, f"fraction {s}/{l}: {model(s, l, 0)} vs {f}")
    # ties: 16|S|/L = k + 1/2 exactly -> away from zero
    nt = 0
    for l in (2, 32, 64, 96, 254, 4094):
        for k in range(0, 2049, 7):
            num = (2 * k + 1) * l            # 32|S| = (2k+1) L
            if num % 32:
                continue
            s = num // 32
            for sg in (1, -1):
                if s > SMAX:
                    continue
                nt += 1
                exp = sg * (k + 1)
                if RMIN <= exp <= RMAX:
                    chk(model(sg * s, l, 1) == exp, f"tie {sg * s}/{l}")
    # R20: agreement with the project model python/src/attention_model.py divide_round
    root = Path(__file__).resolve().parents[5]
    sys.path.insert(0, str(root / "python" / "src"))
    from attention_model import divide_round   # noqa: E402
    npm, nraise = 0, 0
    pm = [(s, l) for l in list(range(1, 300)) + list(range(3800, 4096)) + [rng.randint(1, LMAX) for _ in range(300)]
          for s in sorted({0, 1, -1, 127 * l, -128 * l, l // 2, l // 2 + 1, -(l // 2), -(l // 2) - 1,
                           rng.randint(-128 * l, 127 * l), SMAX, SMIN + 1, -SMAX})]
    pm += [(rng.randint(SMIN + 1, SMAX), rng.randint(1, LMAX)) for _ in range(20000)]
    for s, l in pm:
        if not (SMIN < s <= SMAX):
            continue
        try:
            d = divide_round(s, l)
        except AssertionError:
            d = None
            nraise += 1
        npm += 1
        mine = model(s, l, 0)
        chk(d == mine, f"project model {s}/{l}: divide_round {d} vs model {mine}")
    print(f"RESULT selftest kats={nkat} fraction_points={n2} ties={nt} project_model_points={npm} "
          f"(project model out of domain at {nraise}, model None there too) errors={errs}")
    return 1 if errs else 0


def edges(nrand: int, seed: int, out: str) -> int:
    rng = random.Random(seed)
    pts = []    # (S, L, class)

    def add(s, l, c):
        if SMIN <= s <= SMAX and 0 <= l <= LMAX:
            pts.append((s, l, c))

    Ls = [1, 2, 3, 31, 32, 33, 254, 255, 256, 2047, 2048, 4080, 4094, 4095]
    for l in Ls:
        # sign combinations and small numerators
        for s in (0, 1, -1, 2, -2, 15, -15, 16, -16, 17, -17):
            add(s, l, "small")
        # ties at +-0.5 (32|S| = (2k+1) L) and the integers on both sides of each tie
        for k in list(range(0, 12)) + list(range(2040, 2049)) + [rng.randrange(2048) for _ in range(6)]:
            num = (2 * k + 1) * l
            lo, hi = num // 32, -(-num // 32)
            for a in {lo - 1, lo, hi, hi + 1}:
                if a >= 0:
                    add(a, l, "tie" if 32 * a == num else "near_tie")
                    add(-a, l, "tie" if 32 * a == num else "near_tie")
        # +-2047 / -2048 boundaries: the smallest |S| giving m, for m = 2046..2049
        for m in (2046, 2047, 2048, 2049):
            a = -(-(2 * m - 1) * l // 32)      # ceil((2m-1) L / 32): smallest |S| with round(16|S|/L) >= m
            for d in (-1, 0, 1):
                add(a + d, l, "range")
                add(-(a + d), l, "range")
        # INT8 average bounds used by the chip: S = 127 L, -128 L
        add(127 * l, l, "int8")
        add(-128 * l, l, "int8")
    # largest valid |S| and the extremes of sum_in
    for s in (SMAX, SMAX - 1, -SMAX, SMIN, SMIN + 1, SMIN + 2):
        for l in (1, 255, 4095, 4094):
            add(s, l, "extreme")
    # zero denominator (invalid at 1/1, outside the 0/0 domain)
    for s in (0, 1, -1, 1000, -1000, SMAX, SMIN):
        add(s, 0, "l_zero")
    # random spot checks: half in the valid domain (chip-like ratio), half over the full space
    for i in range(nrand):
        l = rng.randint(1, LMAX)
        if i % 2 == 0:
            s = rng.randint(-128 * l, min(127 * l, SMAX))
            add(s, l, "spot_domain")
        else:
            add(rng.randint(SMIN, SMAX), rng.randint(0, LMAX), "spot_full")
    ndom = 0
    with open(out, "w") as f:
        for s, l, c in pts:
            e0, e1 = model(s, l, 0), model(s, l, 1)
            ndom += e0 is not None
            f.write(f"{s} {l} {'x' if e0 is None else e0} {e1} {c}\n")
    cls = {}
    for _, _, c in pts:
        cls[c] = cls.get(c, 0) + 1
    print(f"RESULT edges points={len(pts)} in_domain_00={ndom} classes=" +
          ",".join(f"{k}:{v}" for k, v in sorted(cls.items())))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["selftest", "edges"])
    ap.add_argument("--random", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.cmd == "selftest":
        return selftest()
    return edges(a.random, a.seed, a.out)


if __name__ == "__main__":
    sys.exit(main())
