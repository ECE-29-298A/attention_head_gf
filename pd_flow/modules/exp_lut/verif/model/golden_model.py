#!/usr/bin/env python3
"""Independent golden model for exp_lut (softmax exponent weight), SPEC.md section 3.

The model is computed from the mathematical definition, not from the RTL's table or its
barrel shifter:

    D'  = round_half_up(D / 2^shift) = floor(D / 2^shift + 1/2)     (exact rationals)
    W   = round(255 * e^(-D' / 4))                                   (exact enough, see below)

with D an unsigned 22-bit integer and shift 0..15. For shift = 0, floor(D + 1/2) = D, so
"no rounding at shift 0" is not a special case.

Rounding of W: 255 * e^(-k/4) is irrational for k >= 1 (k = 0 gives exactly 255), so it is
never a tie; the model checks that every value for k = 0..63 is at least TIE_MARGIN away
from a half-integer, so round-half-up, round-half-even and round-half-away give the same W.
e^x is evaluated twice, with Python's math.exp (double) and with decimal.Decimal at 60
digits; both must give the same W. For k >= 25, W = 0 follows from monotonicity:
255 * e^(-25/4) = 0.4928... < 1/2 and e^(-k/4) decreases in k.

Where the RTL (and its header) is the specification rather than mathematics:
  S1 the constants 255 (scale) and 4 (D' units per nat), the 8-bit unsigned output;
  S2 round half UP for D' (ties D mod 2^shift = 2^(shift-1) go up), the chosen rule;
  S3 D is unsigned (the controller's signed score bits are read as an unsigned number;
     D[21] = 1 therefore gives D' >= 2^6 and W = 0);
  S4 W = 0 is the result for every D' >= 25 (follows from the math, also stated by the RTL);
  S5 REGISTERED = 1 handshake: synchronous active-low reset clears done and W, done is
     `start` delayed by one clock, W loads on start and holds otherwise (no math source);
  S6 REGISTERED = 0: W combinational in (D, shift), done = start.

Subcommands
  selftest                          known-answer tests and self-consistency, plus agreement
                                    with the project's python/src/attention_model.py
  intervals --out F                 expected function as maximal constant intervals:
                                    lines "shift lo hi W" (decimal); every D in [0, 2^22)
                                    for every shift is in exactly one line
  vhdr --out F                      Verilog include for the formal harness: functions
                                    ref_wtab(k) (W for D' = k, k = 0..63) and
                                    ref_thr(shift, k) (smallest D with D' >= k, k = 1..25)
  edges --random K --seed S --out F
                                    combinational edge cases plus K fixed-seed random spot
                                    checks, lines "D shift W class" (hex D, decimal shift, W;
                                    class names the edge-case family, SPEC section 4)
  vectors --random K --seed S --out F
                                    REGISTERED = 1 cycle stimulus with expected outputs,
                                    lines "rst_n start D shift done W" (hex; W = x while
                                    unknown, i.e. before the first reset or start)
"""
import argparse
import decimal
import math
import os
import random
import sys
from fractions import Fraction

DW = 22                      # D width
DMAX = (1 << DW) - 1
SHIFTS = range(16)
SCALE = 255
RES = 4                      # D' units per nat
TIE_MARGIN = 1e-3            # minimum distance of 255 e^(-k/4) from a half-integer
KMAX_TABLE = 64              # table range used by the generated include (k = 0..63)
SCORE_MIN = 64 * (-128 * 127)   # -1040384
SCORE_MAX = 64 * (-128 * -128)  #  1048576
D_CTX_MAX = SCORE_MAX - SCORE_MIN  # 2088960: largest D the controller can consume

decimal.getcontext().prec = 60


def dprime(d: int, s: int) -> int:
    """round_half_up(d / 2^s) on exact rationals."""
    if not (0 <= d <= DMAX and 0 <= s <= 15):
        raise ValueError((d, s))
    q = Fraction(d, 1 << s) + Fraction(1, 2)
    return q.numerator // q.denominator


def _w_float(k: int) -> int:
    x = SCALE * math.exp(-k / RES)
    return math.floor(x + 0.5)


def _w_decimal(k: int) -> int:
    x = decimal.Decimal(SCALE) * (decimal.Decimal(-k) / decimal.Decimal(RES)).exp()
    return int((x + decimal.Decimal("0.5")).to_integral_value(rounding=decimal.ROUND_FLOOR))


def _margin(k: int) -> float:
    x = SCALE * math.exp(-k / RES)
    return abs((x - math.floor(x)) - 0.5)


def w_of_dprime(k: int) -> int:
    """W for D' = k (k >= 0)."""
    if k >= 25:
        return 0            # monotonicity bound, checked in selftest
    a, b = _w_float(k), _w_decimal(k)
    if a != b:
        raise AssertionError(f"float and decimal exp disagree at k={k}: {a} {b}")
    return a


def weight(d: int, s: int) -> int:
    return w_of_dprime(dprime(d, s))


def threshold(s: int, k: int) -> int:
    """Smallest D with D' >= k (k >= 1), from D/2^s + 1/2 >= k  <=>  D >= k*2^s - 2^s/2.
    Ceiling of a rational, computed with Fraction (not the RTL's add-and-shift)."""
    t = Fraction(k * (1 << s)) - Fraction(1 << s, 2)
    return -((-t.numerator) // t.denominator)


def intervals():
    """[(s, lo, hi, w)], maximal runs of constant W over D = 0..DMAX for each shift."""
    out = []
    for s in SHIFTS:
        lo, k = 0, 0
        cur = None
        while lo <= DMAX:
            nxt = threshold(s, k + 1)          # first D of D' = k + 1
            hi = min(DMAX, nxt - 1)
            w = w_of_dprime(k)
            if w == 0:
                hi = DMAX                      # W = 0 for every larger D' (monotone)
            if hi >= lo:
                if cur and cur[3] == w:
                    cur[2] = hi
                else:
                    if cur:
                        out.append(tuple(cur))
                    cur = [s, lo, hi, w]
            lo = hi + 1
            k += 1
        out.append(tuple(cur))
    return out


# ------------------------------------------------------------------ selftest
def selftest() -> int:
    bad = 0

    def check(cond, msg):
        nonlocal bad
        if not cond:
            bad += 1
            print("FAIL", msg)

    # Hand-derived known answers (from e and the definition, not from the RTL table).
    kat_w = {0: 255,          # 255 e^0
             4: 94,           # 255 / e      = 93.81
             8: 35,           # 255 / e^2    = 34.51
             12: 13,          # 255 / e^3    = 12.70
             16: 5,           # 255 / e^4    = 4.67
             20: 2,           # 255 / e^5    = 1.72
             24: 1,           # 255 / e^6    = 0.632
             25: 0,           # 255 e^-6.25  = 0.493
             2: 155,          # 255 / sqrt(e) = 154.66
             1: 199}          # 255 e^-0.25  = 198.59
    for k, w in kat_w.items():
        check(w_of_dprime(k) == w, f"KAT W(D'={k}) = {w_of_dprime(k)}, expected {w}")
    kat_dp = [((0, 0), 0), ((7, 0), 7), ((1, 1), 1), ((2, 2), 1), ((1, 2), 0), ((3, 2), 1),
              ((5, 2), 1), ((6, 2), 2), ((DMAX, 15), 128), ((DMAX, 0), DMAX),
              ((3 << 14, 15), 2), (((3 << 14) - 1, 15), 1), ((1 << 20, 15), 32)]
    for (d, s), k in kat_dp:
        check(dprime(d, s) == k, f"KAT D'({d},{s}) = {dprime(d, s)}, expected {k}")
    for s in range(1, 16):          # exact ties go up (S2)
        check(dprime(1 << (s - 1), s) == 1, f"tie at shift {s} not rounded up")
        check(dprime((1 << (s - 1)) - 1, s) == 0, f"below tie at shift {s}")
    # Rounding of W is unambiguous; the two exp evaluations agree; monotone bound for 25+.
    mins = min(_margin(k) for k in range(1, KMAX_TABLE))
    check(mins >= TIE_MARGIN, f"W tie margin {mins} < {TIE_MARGIN}")
    for k in range(KMAX_TABLE):
        check(_w_float(k) == _w_decimal(k), f"float/decimal disagree at {k}")
    check(SCALE * math.exp(-25 / RES) < 0.5, "monotone bound 255 e^-6.25 < 0.5")
    check(all(_w_decimal(k) == 0 for k in range(25, KMAX_TABLE)), "W(k >= 25) must be 0")
    check(all(_w_decimal(k) >= _w_decimal(k + 1) for k in range(KMAX_TABLE - 1)), "W monotone")
    nz = [w_of_dprime(k) for k in range(25)]
    check(all(w > 0 for w in nz), "W(k < 25) > 0")
    # threshold(): consistent with dprime() (two formulations of the rounding).
    for s in SHIFTS:
        for k in range(1, 40):
            t = threshold(s, k)
            if t <= DMAX:
                check(dprime(t, s) >= k, f"thr({s},{k})={t}: D' {dprime(t, s)} < {k}")
            if 0 <= t - 1 <= DMAX:
                check(dprime(t - 1, s) < k, f"thr({s},{k})-1: D' >= {k}")
    # dprime(): Fraction definition vs an independent integer formulation (2D + 2^s) // 2^(s+1),
    # for every D < 4096 and every shift, plus 20,000 random D.
    rng = random.Random(1)
    ds = list(range(4096)) + [rng.randrange(DMAX + 1) for _ in range(20000)] + [DMAX]
    for s in SHIFTS:
        for d in ds:
            if dprime(d, s) != (2 * d + (1 << s)) // (1 << (s + 1)):
                check(False, f"dprime({d},{s}) formulations disagree")
                break
    # intervals: contiguous cover of [0, DMAX] per shift, W non-increasing, agree with weight().
    iv = intervals()
    for s in SHIFTS:
        rows = [r for r in iv if r[0] == s]
        check(rows[0][1] == 0 and rows[-1][2] == DMAX, f"intervals shift {s} do not cover")
        for a, b in zip(rows, rows[1:]):
            check(b[1] == a[2] + 1 and b[3] < a[3], f"intervals shift {s} gap/order {a} {b}")
        for _, lo, hi, w in rows:
            for d in {lo, hi, (lo + hi) // 2, min(hi, lo + 1), max(lo, hi - 1)}:
                check(weight(d, s) == w, f"interval ({s},{lo},{hi},{w}) at {d}: {weight(d, s)}")
    for _ in range(20000):
        d, s = rng.randrange(DMAX + 1), rng.randrange(16)
        w = next(r[3] for r in iv if r[0] == s and r[1] <= d <= r[2])
        check(weight(d, s) == w, f"random interval check {d},{s}")
    # The project's own Python model (python/src/attention_model.py, exp_weight with
    # score_round=True), which the RTL header says it must match: every interval boundary
    # +-1 and 2,000 random points per shift, over the D range that model accepts.
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), *[".."] * 5))
    sys.path.insert(0, os.path.join(root, "python", "src"))
    npy = 0
    try:
        import attention_model as am  # noqa: E402
        for s in SHIFTS:
            pts = set()
            for _, lo, hi, _ in (r for r in iv if r[0] == s):
                pts |= {lo - 1, lo, lo + 1, hi - 1, hi, hi + 1}
            pts |= {rng.randrange(D_CTX_MAX + 1) for _ in range(2000)}
            for d in sorted(p for p in pts if 0 <= p <= D_CTX_MAX):
                try:
                    ref = am.exp_weight(d, 0, score_shift=s, score_round=True)
                except (AssertionError, ValueError):
                    continue
                npy += 1
                check(ref == weight(d, s), f"python/src exp_weight({d},0,shift={s})={ref} != {weight(d, s)}")
    except ImportError as e:
        check(False, f"cannot import python/src/attention_model.py: {e}")
    check(npy > 10000, f"too few project-model comparisons ({npy})")
    print(f"RESULT selftest kat_w={len(kat_w)} kat_dp={len(kat_dp)} tie_margin_min={mins:.4f} "
          f"intervals={len(iv)} project_model_points={npy} mismatches={bad}")
    return 1 if bad else 0


# ------------------------------------------------------------------ outputs
def write_intervals(path):
    iv = intervals()
    with open(path, "w") as f:
        for s, lo, hi, w in iv:
            f.write(f"{s} {lo} {hi} {w}\n")
    print(f"RESULT intervals lines={len(iv)}")


def write_vhdr(path):
    with open(path, "w") as f:
        f.write("// generated by model/golden_model.py vhdr from the mathematical definition\n")
        f.write("function [7:0] ref_wtab(input [5:0] k);\n  case (k)\n")
        for k in range(KMAX_TABLE):
            f.write(f"    6'd{k}: ref_wtab = 8'd{w_of_dprime(k)};\n")
        f.write("    default: ref_wtab = 8'd0;\n  endcase\nendfunction\n")
        f.write("function [22:0] ref_thr(input [3:0] s, input [4:0] k);\n  case ({s, k})\n")
        for s in SHIFTS:
            for k in range(1, 26):
                f.write(f"    {{4'd{s}, 5'd{k}}}: ref_thr = 23'd{threshold(s, k)};\n")
        f.write("    default: ref_thr = 23'h7fffff;\n  endcase\nendfunction\n")
    print(f"RESULT vhdr wtab={KMAX_TABLE} thresholds={16 * 25}")


def edge_points():
    """Directed edge cases [(D, shift, class)] for the combinational function (SPEC section 4)."""
    pts = []
    trans = [k for k in range(1, 26) if w_of_dprime(k) != w_of_dprime(k - 1)]   # W changes at D' = k
    fixed = [0, 1, 2, 3, (1 << 20) - 1, 1 << 20, (1 << 20) + 1, (1 << 21) - 1, 1 << 21,
             (1 << 21) + 1, DMAX - 1, DMAX, D_CTX_MAX, D_CTX_MAX + 1]

    def add(d, s, c):
        if 0 <= d <= DMAX:
            pts.append((d, s, c))

    for s in SHIFTS:
        h = (1 << s) >> 1
        for k in (0, 1, 24, 25):                       # D' boundaries incl. the zero-region edge
            t = threshold(s, k) if k else 0
            for off in (-1, 0, 1):
                add(t + off, s, "dprime_edge")
        for k in trans:                                # every output transition point
            t = threshold(s, k)
            for off in (-1, 0, 1):
                add(t + off, s, "transition")
        for k in range(0, 34):                         # rounding: k*2^s +- 1 and (2k+1)*2^(s-1) +- 0/1
            for off in (-1, 1):
                add(k * (1 << s) + off, s, "half_way")
            if s:
                m = (2 * k + 1) * h
                for off in (-1, 0, 1):
                    add(m + off, s, "half_way")
        for d in fixed:                                # extremes of D
            add(d, s, "fixed")
        add(threshold(s, 25) - 1, s, "last_nonzero")
        for k in list(range(25)) + [25, 31, 32]:       # D[21] = 1 classes: low bits that alone
            t = threshold(s, k) if k else 0            # would give every D' (masked to 0)
            add((1 << 21) | t, s, "d21_set")
            add((1 << 21) | (1 << 20) | t, s, "d21_d20_set")
            add((1 << 20) | t, s, "d20_set")
        for d in ((1 << 21) | ((1 << 21) - 1), (1 << 21) | 0x155555, (1 << 21) | 0x0AAAAA):
            add(d, s, "d21_set")
    return pts


def write_edges(path, nrand, seed):
    rng = random.Random(seed)
    pts = edge_points()
    for _ in range(nrand):                             # fixed-seed spot checks
        s = rng.randrange(16)
        r = rng.random()
        if r < 0.5:
            d = rng.randrange(min(DMAX, threshold(s, 27)) + 1)   # the non-zero region and its edge
        elif r < 0.75:
            d = rng.randrange(D_CTX_MAX + 1)                    # the range the controller consumes
        else:
            d = rng.randrange(DMAX + 1)                         # full 22-bit, half of it D[21] = 1
        pts.append((d, s, "random"))
    cls = {}
    with open(path, "w") as f:
        for d, s, c in pts:
            f.write(f"{d:06x} {s} {weight(d, s)} {c}\n")
            cls[c] = cls.get(c, 0) + 1
    print(f"RESULT edges points={len(pts)} " + " ".join(f"{k}={v}" for k, v in sorted(cls.items())))


def write_vectors(path, nrand, seed):
    rng = random.Random(seed)
    iv = intervals()
    bnd = {s: sorted({x for r in iv if r[0] == s for x in (r[1], r[2])}) for s in SHIFTS}
    rows = []
    st = {"W": None}

    def cyc(rst_n, start, d, s):
        d &= DMAX
        s &= 15
        done = 1 if (rst_n and start) else 0
        if not rst_n:
            st["W"] = 0
        elif start:
            st["W"] = weight(d, s)
        rows.append((rst_n, start, d, s, done, st["W"]))

    def rand_d(s):
        r = rng.random()
        if r < 0.35:
            b = rng.choice(bnd[s])
            return min(DMAX, max(0, b + rng.randint(-2, 2)))
        if r < 0.55:
            return rng.randrange(min(DMAX, threshold(s, 26)) + 1)
        if r < 0.75:
            return rng.randrange(D_CTX_MAX + 1)
        if r < 0.85:
            return rng.randrange(1 << 21, 1 << 22)      # D[21] set
        return rng.randrange(DMAX + 1)

    # power-up: W unknown until the first start or reset
    for _ in range(3):
        cyc(1, 0, rng.randrange(DMAX + 1), rng.randrange(16))
    cyc(1, 1, 5, 0)                                         # start before any reset
    cyc(1, 0, 0, 0)
    cyc(0, 1, 0, 0)                                         # reset wins over start
    cyc(1, 0, 0, 0)
    for s in SHIFTS:                                        # every D' 0..33 at every shift,
        for k in range(34):                                 # at, below and above each tie
            for off in (-1, 0, 1):
                t = threshold(s, k) if k else 0
                d = t + off
                if 0 <= d <= DMAX:
                    cyc(1, 1, d, s)
        cyc(1, 1, DMAX, s)
        cyc(1, 1, 1 << 21, s)
        cyc(1, 1, (1 << 20) - 1, s)
    for _ in range(64):                                     # hold with changing inputs
        cyc(1, 1, rng.randrange(64), 0)
        for _ in range(rng.randint(1, 6)):
            cyc(1, 0, rng.randrange(DMAX + 1), rng.randrange(16))
    cyc(0, 0, 0, 0)
    for _ in range(4):
        cyc(1, 0, rng.randrange(DMAX + 1), rng.randrange(16))
    # random regimes
    while len(rows) < nrand + 6000:
        p_start = rng.choice([0.0, 0.1, 0.5, 0.9, 1.0])
        p_rst = rng.choice([0.0, 0.0, 0.01, 0.1])
        for _ in range(rng.randint(20, 500)):
            s = rng.randrange(16)
            cyc(0 if rng.random() < p_rst else 1, 1 if rng.random() < p_start else 0, rand_d(s), s)
    with open(path, "w") as f:
        for r in rows:
            w = "x" if r[5] is None else f"{r[5]:02x}"
            f.write(f"{r[0]} {r[1]} {r[2]:06x} {r[3]:x} {r[4]} {w}\n")
    known = sum(r[5] is not None for r in rows)
    print(f"RESULT vectors written={len(rows)} checked_values={known}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["selftest", "intervals", "vhdr", "edges", "vectors"])
    ap.add_argument("--out")
    ap.add_argument("--random", type=int, default=200000)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    if a.cmd == "selftest":
        return selftest()
    if not a.out:
        ap.error("--out required")
    if a.cmd == "intervals":
        write_intervals(a.out)
    elif a.cmd == "vhdr":
        write_vhdr(a.out)
    elif a.cmd == "edges":
        write_edges(a.out, a.random, a.seed)
    else:
        write_vectors(a.out, a.random, a.seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
