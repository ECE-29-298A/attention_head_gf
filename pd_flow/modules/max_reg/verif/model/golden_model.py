#!/usr/bin/env python3
"""Independent golden model for max_reg (22-bit signed running maximum, no reset).

Reference semantics (SPEC.md section 3), on Python's unbounded signed integers:
  one step   M' = S_in  if en and (first or S_in > M)   else M        (R1 to R5)
  sequence   after a cycle with en = first = 1, M equals max() of every S_in accepted
             (en = 1) since the most recent such cycle, including it          (R7)
Before the first `first` load M is unknown (None): the model never predicts it (R6, R8).
The model does not use the RTL's bit-level comparator; values are converted from 22-bit
two's complement with an explicit subtraction and compared as Python ints.

Subcommands
  selftest                              known-answer tests and model self-consistency
  vectors --random K --seed S --out F   cycle-by-cycle stimulus with expected M, as
                                        "first en S_in M" (hex, M = 'x' when unknown):
                                        directed corners + controller-style sequences +
                                        K cycles of unconstrained random sequences
"""
import argparse
import random
import sys

W = 22
MASK = (1 << W) - 1
MINV = -(1 << (W - 1))          # -2097152, 22'h200000
MAXV = (1 << (W - 1)) - 1       #  2097151, 22'h1FFFFF
SCORE_MIN = 64 * (-128 * 127)   # -1040384: INT8 score range used by the controller
SCORE_MAX = 64 * (-128 * -128)  #  1048576


def to_signed(x: int) -> int:
    x &= MASK
    return x - (1 << W) if x >= (1 << (W - 1)) else x


def to_bits(v: int) -> int:
    if not MINV <= v <= MAXV:
        raise ValueError(f"value {v} out of 22-bit signed range")
    return v & MASK


def step(m, first: int, en: int, s: int):
    """One clock edge. m is the current M (signed int) or None (unknown); s is signed."""
    if en and first:
        return s
    if en and m is not None and s > m:
        return s
    if en and m is None:
        return None             # the compare against an unknown M has an unknown result
    return m


class Sequence:
    """Sequence-level reference (R7): the list of scores accepted since the last first load.
    Expected M = max(list). Kept as a list (not a running compare) so it is a different
    formulation from step(); long lists are compacted to their max, which max() preserves."""

    def __init__(self):
        self.acc = None

    def clock(self, first: int, en: int, s: int):
        if en and first:
            self.acc = [s]
        elif en and self.acc is not None:
            self.acc.append(s)
            if len(self.acc) > 64:
                self.acc = [max(self.acc)]

    def expected(self):
        return None if self.acc is None else max(self.acc)


# ---------------------------------------------------------------- self test
def selftest() -> int:
    bad = 0
    conv = [(0x000000, 0), (0x000001, 1), (0x1FFFFF, MAXV), (0x200000, MINV), (0x3FFFFF, -1),
            (0x200001, MINV + 1), (0x0F0000, 983040), (0x300000, -1048576)]
    for bits, v in conv:
        if to_signed(bits) != v or to_bits(v) != bits:
            print(f"CONV FAIL {bits:#x} {v}")
            bad += 1
    kat = [  # (M, first, en, S, expected M'), hand-computed
        (0, 0, 0, 5, 0), (0, 1, 0, 5, 0),          # en = 0 holds, also with first
        (0, 0, 1, 5, 5), (5, 0, 1, 0, 5),          # greater updates, smaller holds
        (5, 0, 1, 5, 5),                           # tie: unchanged
        (5, 1, 1, -7, -7),                         # first overrides the compare
        (-1, 0, 1, 0, 0), (0, 0, 1, -1, 0),        # signed, not unsigned
        (MINV, 0, 1, MAXV, MAXV), (MAXV, 0, 1, MINV, MAXV),
        (MINV, 0, 1, MINV, MINV), (MAXV, 0, 1, MAXV, MAXV),
        (MAXV, 1, 1, MINV, MINV), (MINV, 0, 1, MINV + 1, MINV + 1),
        (-1040384, 0, 1, 1048576, 1048576), (None, 0, 0, 3, None), (None, 1, 1, 3, 3),
        (None, 0, 1, 3, None),
    ]
    for m, f, e, s, exp in kat:
        got = step(m, f, e, s)
        if got != exp:
            print(f"KAT FAIL M={m} first={f} en={e} S={s} got={got} exp={exp}")
            bad += 1
    # step() iterated from a first load equals max() of the accepted list (two formulations)
    rng = random.Random(11)
    for trial in range(3000):
        seq, m = Sequence(), None
        for _ in range(rng.randrange(1, 40)):
            f, e = int(rng.random() < 0.15), int(rng.random() < 0.7)
            s = rng.choice([rng.randint(MINV, MAXV), rng.randint(-3, 3), MINV, MAXV])
            m = step(m, f, e, s)
            seq.clock(f, e, s)
            if seq.expected() is not None and m != seq.expected():
                print(f"SEQ FAIL trial={trial} step={m} seq={seq.expected()}")
                bad += 1
                break
    print(f"RESULT selftest conv={len(conv)} kat={len(kat)} seq_trials=3000 mismatches={bad}")
    return 1 if bad else 0


# ---------------------------------------------------------------- stimulus
def directed(rng):
    """Directed corners. Each yields (first, en, S). Expected values come from Sequence."""
    # power-up preamble: no first load yet; en = 1 with and without first = 0
    for s in (0, MAXV, MINV, -1, 1, 12345):
        yield 0, 1, s
    yield 1, 0, MAXV                      # first without en does nothing
    yield 0, 0, MINV

    def load(v):
        return [(1, 1, v)]
    corners = [MINV, MINV + 1, -2, -1, 0, 1, 2, MAXV - 1, MAXV, SCORE_MIN, SCORE_MAX,
               -(1 << 20), (1 << 20) - 1, 1 << 20, -(1 << 20) - 1]
    out = []
    # every ordered pair of corner values: load M = a, then offer b (non-first), then
    # offer b with en = 0, then with first = 1 and en = 0, then a first load of b
    for a in corners:
        for b in corners:
            out += load(a) + [(0, 0, b), (1, 0, b), (0, 1, b), (0, 1, a), (0, 0, MAXV)]
            out += load(a) + [(1, 1, b), (0, 1, a)]
    # single-bit differences at every bit, both directions, around several bases
    for base in (0, -1, MINV, MAXV, 0x0AAAAA, to_signed(0x355555), SCORE_MIN, SCORE_MAX):
        for k in range(W):
            other = to_signed(to_bits(base) ^ (1 << k))
            out += load(base) + [(0, 1, other)]
            out += load(other) + [(0, 1, base)]
            for d in (-1, 1):
                v = base + d * (1 << k)
                if MINV <= v <= MAXV:
                    out += load(base) + [(0, 1, v), (0, 1, base)]
    # ties and near ties
    for v in corners:
        out += load(v) + [(0, 1, v), (0, 1, v), (0, 0, v)]
        if v > MINV:
            out += [(0, 1, v - 1)]
        if v < MAXV:
            out += [(0, 1, v + 1)]
    # monotone up and down runs, repeated firsts
    up = sorted(rng.sample(range(SCORE_MIN, SCORE_MAX), 40))
    out += load(up[0]) + [(0, 1, v) for v in up[1:]]
    out += load(up[-1]) + [(0, 1, v) for v in reversed(up[:-1])]
    out += [(1, 1, v) for v in up] + [(1, 1, v) for v in reversed(up)]
    out += [(1, 1, MAXV), (1, 1, MINV), (0, 1, MINV), (0, 0, MAXV)]
    for t in out:
        yield t


def controller(rng, queries):
    """Stimulus as attention_controller drives max_reg: first = (token == 0) as a level,
    en = score_done && !second_pass as a one-cycle pulse per key; S_in carries MAC partial
    sums (arbitrary values) while en = 0. Continue runs (second_pass = 1 from start) never
    assert en, so M must hold the previous query's maximum."""
    started = False
    for _ in range(queries):
        n = rng.randint(1, 16)
        cont = started and rng.random() < 0.25
        idle = rng.randint(1, 6)
        for _ in range(idle):                     # IDLE: token = 0
            yield 1, 0, rng.randint(MINV, MAXV)
        if not cont:
            started = True
            scores = []
            for k in range(n):                    # pass 1
                gap = rng.choice([0, 1, 2, rng.randint(3, 12), rng.randint(13, 40)])
                for _ in range(gap):
                    yield int(k == 0), 0, rng.randint(MINV, MAXV)
                r = rng.random()
                if r < 0.1 and scores:
                    s = rng.choice(scores)        # tie with an earlier score
                elif r < 0.2 and scores:
                    s = max(scores) + rng.choice([-1, 1])
                elif r < 0.3:
                    s = rng.randint(MINV, MAXV)
                else:
                    s = rng.randint(SCORE_MIN, SCORE_MAX)
                s = min(MAXV, max(MINV, s))
                scores.append(s)
                yield int(k == 0), 1, s
        for k in range(n):                        # pass 2 (and the whole continue run)
            for _ in range(rng.randint(0, 8)):
                yield int(k == 0), 0, rng.randint(MINV, MAXV)
            yield int(k == 0), 0, rng.randint(MINV, MAXV)   # score_done, en = 0
            for _ in range(rng.randint(0, 4)):              # VALUE: token advances
                yield 0, 0, rng.randint(MINV, MAXV)


def unconstrained(rng, cycles, model):
    """Random first/en/S_in with regime switching (probabilities and value distributions)."""
    i = 0
    while i < cycles:
        p_first = rng.choice([0.0, 1 / 64, 1 / 8, 0.5, 1.0])
        p_en = rng.choice([0.05, 0.5, 0.95, 1.0])
        mode = rng.randrange(6)
        for _ in range(min(cycles - i, rng.randint(50, 2000))):
            m = model.expected()
            if mode == 0 or m is None:
                s = rng.randint(MINV, MAXV)
            elif mode == 1:
                s = rng.choice([MINV, MINV + 1, -1, 0, 1, MAXV - 1, MAXV])
            elif mode == 2:
                s = min(MAXV, max(MINV, m + rng.randint(-3, 3)))
            elif mode == 3:
                s = m if rng.random() < 0.5 else to_signed(to_bits(m) ^ (1 << rng.randrange(W)))
            elif mode == 4:
                s = rng.randint(SCORE_MIN, SCORE_MAX)
            else:
                s = to_signed(rng.getrandbits(W) & rng.getrandbits(W)) if rng.random() < 0.5 \
                    else to_signed(rng.getrandbits(W) | rng.getrandbits(W))
            yield int(rng.random() < p_first), int(rng.random() < p_en), s
            i += 1


def gen_vectors(k: int, seed: int, path: str) -> None:
    rng = random.Random(seed)
    model = Sequence()
    count = known = 0
    with open(path, "w") as f:
        f.write(f"# max_reg golden vectors random={k} seed={seed}\n")
        f.write("# first en S_in M_after_edge (hex; M = x while unknown)\n")

        def emit(first, en, s):
            nonlocal count, known
            model.clock(first, en, s)
            e = model.expected()
            f.write(f"{first} {en} {to_bits(s):06x} {'x' if e is None else format(to_bits(e), '06x')}\n")
            count += 1
            known += e is not None

        for t in directed(rng):
            emit(*t)
        for t in controller(rng, 3000):
            emit(*t)
        for t in unconstrained(rng, k, model):
            emit(*t)
    print(f"RESULT vectors written={count} checked_values={known} file={path}")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("selftest")
    v = sub.add_parser("vectors")
    v.add_argument("--random", type=int, default=200000)
    v.add_argument("--seed", type=int, default=1)
    v.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "selftest":
        return selftest()
    gen_vectors(a.random, a.seed, a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
