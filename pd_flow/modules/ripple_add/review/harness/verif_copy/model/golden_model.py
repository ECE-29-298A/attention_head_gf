#!/usr/bin/env python3
"""Independent golden model for ripple_add #(N).

Reference semantics (SPEC.md R1, R2): s = (a + b + cin) mod 2^N, computed with Python's
unbounded integers. It does not model the RTL's bit-level full-adder chain.

Subcommands
  selftest                          known-answer tests of the model itself
  vectors  --n N --random K --seed S --out FILE
                                    directed corners + K random vectors with expected s
  checksum --n N                    position-weighted checksum of s over the exhaustive
                                    (a, b, cin) space, to cross-check the simulator run
"""
import argparse
import random
import sys


def ref(a: int, b: int, cin: int, n: int) -> int:
    if n < 1:
        raise ValueError("N must be >= 1")
    if not (0 <= a < (1 << n) and 0 <= b < (1 << n) and cin in (0, 1)):
        raise ValueError(f"operand out of range for N={n}: a={a} b={b} cin={cin}")
    return (a + b + cin) % (2 ** n)


def ref_sub(a: int, x: int, n: int) -> int:
    """Two's-complement subtract as mac_unit uses it: a + ~x + 1 == a - x (mod 2^N)."""
    return (a - x) % (2 ** n)


# ---------------------------------------------------------------- self test
def selftest() -> int:
    kat = [  # (N, a, b, cin, expected s), hand-computed
        (1, 0, 0, 0, 0), (1, 1, 0, 0, 1), (1, 1, 1, 0, 0), (1, 1, 1, 1, 1), (1, 0, 0, 1, 1),
        (4, 0xF, 0x1, 0, 0x0), (4, 0xF, 0x0, 1, 0x0), (4, 0xF, 0xF, 1, 0xF), (4, 0x7, 0x1, 0, 0x8),
        (4, 0x5, 0xA, 1, 0x0), (4, 0x3, 0x4, 0, 0x7),
        (12, 4095, 255, 0, 254), (12, 100, 200, 0, 300), (12, 0, 0, 1, 1),
        (22, 0x3FFFFF, 0x000001, 0, 0), (22, 0x200000, 0x200000, 0, 0),
        (22, 0x1FFFFF, 0x000001, 0, 0x200000), (22, 5, 0x3FFFFF ^ 3, 1, 2),
        (22, 3, 0x3FFFFF ^ 5, 1, 0x3FFFFE),
    ]
    bad = 0
    for n, a, b, c, e in kat:
        got = ref(a, b, c, n)
        if got != e:
            print(f"KAT FAIL N={n} a={a:#x} b={b:#x} cin={c} got={got:#x} exp={e:#x}")
            bad += 1
    # ref_sub agrees with the a + ~x + 1 form
    rng = random.Random(7)
    for n in (1, 3, 12, 22, 64):
        m = (1 << n) - 1
        for _ in range(1000):
            a, x = rng.getrandbits(n), rng.getrandbits(n)
            if ref(a, x ^ m, 1, n) != ref_sub(a, x, n):
                print(f"SUB FAIL N={n} a={a:#x} x={x:#x}")
                bad += 1
    print(f"RESULT selftest kat={len(kat)} mismatches={bad}")
    return 1 if bad else 0


# ---------------------------------------------------------------- vectors
def directed(n: int):
    m = (1 << n) - 1
    vals = {0, 1, 2, 3, m, m - 1 if m > 0 else 0, m >> 1, 1 << (n - 1), (1 << (n - 1)) + 1,
            int("5" * ((n + 3) // 4), 16) & m, int("A" * ((n + 3) // 4), 16) & m}
    for k in range(n):
        vals |= {1 << k, m ^ (1 << k), (1 << k) - 1, m ^ ((1 << k) - 1)}
    vals |= {v ^ m for v in list(vals)}  # closed under complement (subtract operands)
    vals = sorted(v & m for v in vals)
    for a in vals:
        for b in vals:
            for c in (0, 1):
                yield a, b, c
    # full carry propagate through every bit: a ^ b == all ones, cin = 1
    rng = random.Random(n)
    for _ in range(64):
        a = rng.getrandbits(n)
        yield a, a ^ m, 1
        yield a, a ^ m, 0
    # carry generated at bit k and propagated to the MSB
    for k in range(n):
        a = (m >> k) << k            # ones from bit k up; +2^k generates at k, wraps to 0
        yield a, 1 << k, 0
        yield a, 0, 1                # cin into a run of ones that starts at bit k
    if n == 22:  # mac_unit score/V use: b = term or ~term, cin = neg
        for q in (0, 1, -1, 127, -128, 255, 85, -86):
            x = (q & 0x1FF) | (0x1FFE00 if q < 0 else 0)  # {{13{x[8]}}, x}, 9-bit x
            for k in range(8):
                term = (x << k) & m
                for s in (0, 1, m, 1 << 21, (1 << 21) - 1, 0x155555, 0x2AAAAA):
                    yield s, term, 0
                    yield s, term ^ m, 1
    if n == 12:  # mac_unit L use: a = L or 0, b = {4'b0, W}, cin = 0
        for a in (0, 1, 255, 256, 2047, 2048, 3840, 4094, 4095):
            for w in range(256):
                yield a, w, 0


def gen_vectors(n: int, k: int, seed: int, path: str) -> None:
    m = (1 << n) - 1
    rng = random.Random(seed)
    count = 0
    with open(path, "w") as f:
        f.write(f"# ripple_add golden vectors N={n} random={k} seed={seed}\n")
        f.write("# a b cin s (hex)\n")

        def emit(a, b, c):
            nonlocal count
            f.write(f"{a:x} {b:x} {c:x} {ref(a, b, c, n):x}\n")
            count += 1

        for a, b, c in directed(n):
            emit(a, b, c)
        for i in range(k):
            sel = i & 3
            a = rng.getrandbits(n)
            if sel < 2:                      # uniform
                b = rng.getrandbits(n)
            elif sel == 2:                   # long carry chains: mostly propagate bits
                b = (a ^ m) ^ (rng.getrandbits(n) & rng.getrandbits(n) & rng.getrandbits(n))
            else:                            # sparse/dense operands
                a &= rng.getrandbits(n) & rng.getrandbits(n)
                b = m ^ (rng.getrandbits(n) & rng.getrandbits(n))
            emit(a, b & m, rng.getrandbits(1))
    print(f"RESULT vectors N={n} written={count} file={path}")


# ---------------------------------------------------------------- checksum
def checksum(n: int) -> int:
    """sum over idx of s(idx) * splitmix64(idx) mod 2^64, idx = (a << (N+1)) | (b << 1) | cin.
    Same definition as tb_ripple_add.cpp. Needs numpy; vectorised in chunks."""
    import numpy as np
    m = (1 << n) - 1
    total = 1 << (2 * n + 1)
    chunk = 1 << 22
    acc = np.uint64(0)
    with np.errstate(over="ignore"):
        for start in range(0, total, chunk):
            idx = np.arange(start, min(total, start + chunk), dtype=np.uint64)
            a = idx >> np.uint64(n + 1)
            b = (idx >> np.uint64(1)) & np.uint64(m)
            c = idx & np.uint64(1)
            s = (a + b + c) & np.uint64(m)
            z = idx + np.uint64(0x9E3779B97F4A7C15)
            z = (z ^ (z >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
            z = (z ^ (z >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
            z = z ^ (z >> np.uint64(31))
            acc = acc + np.sum(s * z, dtype=np.uint64)
    return int(acc)


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("selftest")
    v = sub.add_parser("vectors")
    v.add_argument("--n", type=int, required=True)
    v.add_argument("--random", type=int, default=100000)
    v.add_argument("--seed", type=int, default=1)
    v.add_argument("--out", required=True)
    c = sub.add_parser("checksum")
    c.add_argument("--n", type=int, required=True)
    args = p.parse_args()
    if args.cmd == "selftest":
        return selftest()
    if args.cmd == "vectors":
        gen_vectors(args.n, args.random, args.seed, args.out)
        return 0
    if args.cmd == "checksum":
        if 2 * args.n + 1 > 31:
            print("checksum: exhaustive space too large", file=sys.stderr)
            return 2
        print(f"CHECKSUM N={args.n} vectors={1 << (2 * args.n + 1)} checksum=0x{checksum(args.n):016x}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
