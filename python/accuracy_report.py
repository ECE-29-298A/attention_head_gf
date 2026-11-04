"""
Accuracy report: how far is the chip's answer from real attention?

Compares, against float_attention() (exact softmax, same /2 scaling):
  1. The chip as built (INT4, two-pass, chip_attention()).
  2. The proposal's original 23/32-trick table, for comparison.
  3. The chip if we went INT8 (widths left unconstrained, we report what they'd need).
  4. Online softmax (single pass, rescale on new max), INT4.

Errors are in output VALUE units (the real number, i.e. code / 16).
The output itself is rounded to 1/16 = 0.0625, so anything around
0.03 is just that final rounding and can't be beaten.

Run:  python3 python/accuracy_report.py      (writes python/accuracy_report.md)
"""

import math
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from attention_model import chip_attention, exp_weight, float_attention  # noqa: E402

OUT_FRAC = 16  # output code = value · 16

# Weight tables indexed by D = max - score. Scores are integers, so D is too,
# and both tables are 0 from D = 13 on.
TABLE_CHIP = [exp_weight(D, 0) for D in range(13)]                  # what exp_lut.v stores (exact e^(-D/2))
def _old_23_32(D):
    """The proposal's original 23/32 trick, kept here only for comparison."""
    A = 23 * D
    n, r = A >> 5, (A >> 1) & 0xF
    T = round(255 * 2 ** (-r / 16))
    return T if n == 0 else ((T + (1 << (n - 1))) >> n if n <= 8 else 0)


TABLE_OLD = [_old_23_32(D) for D in range(13)]                       # proposal's 23/32 trick


def weight(D, table):
    return table[D] if D < len(table) else 0


def divide_round(O, L):
    """Same rounding as the chip's divider: round half away from zero."""
    q, R = divmod(OUT_FRAC * abs(O), L)
    if 2 * R >= L:
        q += 1
    return -q if O < 0 else q


def two_pass(q, K, V, table, widths):
    """Generic two-pass chip. Tracks the biggest |value| each register sees."""
    S = [int(np.dot(q, k)) for k in K]
    M = max(S)
    L, O = 0, [0, 0, 0, 0]
    for s, v in zip(S, V):
        W = weight(M - s, table)
        L += W
        for i in range(4):
            O[i] += W * v[i]
    widths["S"] = max(widths.get("S", 0), max(abs(s) for s in S))
    widths["L"] = max(widths.get("L", 0), L)
    widths["O"] = max(widths.get("O", 0), max(abs(o) for o in O))
    return [divide_round(o, L) / OUT_FRAC for o in O]


def online(q, K, V, table):
    """Single pass. When a new max shows up, shrink the old sums by
    W(old_max - new_max) / 256 (multiply then >> 8 with rounding, what
    hardware would do with the shared MAC)."""
    m = None
    L, O = 0, [0, 0, 0, 0]
    for k, v in zip(K, V):
        s = int(np.dot(q, k))
        if m is None:
            m = s
        elif s > m:
            f = weight(s - m, table)
            L = (L * f + 128) >> 8
            O = [(o * f + 128) >> 8 for o in O]
            m = s
        W = weight(m - s, table)
        L += W
        for i in range(4):
            O[i] += W * v[i]
    return [divide_round(o, L) / OUT_FRAC for o in O]


def rand_vec(rng, bits):
    lo, hi = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    return [rng.randint(lo, hi) for _ in range(4)]


def stats(errors):
    e = np.abs(np.array(errors))
    return f"{e.mean():.4f}", f"{np.percentile(e, 99):.4f}", f"{e.max():.4f}"


# ---------- test sets ----------

def random_cases(rng, n_tokens, trials, bits=4):
    for _ in range(trials):
        yield (rand_vec(rng, bits),
               [rand_vec(rng, bits) for _ in range(n_tokens)],
               [rand_vec(rng, bits) for _ in range(n_tokens)])


def nasty_cases(rng):
    """The edge cases from the controller test, plus a few more."""
    named = {}
    # All scores negative
    named["all scores negative"] = [([-8] * 4, [[7] * 4] * 16, [rand_vec(rng, 4) for _ in range(16)])]
    # All scores equal -> plain average
    named["all scores equal"] = [([0] * 4, [rand_vec(rng, 4) for _ in range(16)],
                                  [rand_vec(rng, 4) for _ in range(16)]) for _ in range(200)]
    # One token dominates, the rest are at the value extremes
    named["one dominant token"] = [([1, 0, 0, 0], [[7, 0, 0, 0]] + [[-6, 0, 0, 0]] * 15,
                                    [[-8] * 4] + [[7] * 4] * 15)]
    # Scores close together (D small) -> many tokens share the weight
    cases = []
    for _ in range(500):
        q = [1, 0, 0, 0]
        K = [[rng.randint(4, 7), rng.randint(-8, 7), 0, 0] for _ in range(16)]
        V = [rand_vec(rng, 4) for _ in range(16)]
        cases.append((q, K, V))
    named["close scores (D <= 3)"] = cases
    # Rising scores: worst case for online softmax (max changes every token)
    cases = []
    for _ in range(500):
        q = [1, 1, 0, 0]
        base = sorted(rng.sample(range(-14, 15), 16))
        K = [[min(7, max(-8, b // 2)), min(7, max(-8, b - b // 2)), 0, 0] for b in base]
        V = [rand_vec(rng, 4) for _ in range(16)]
        cases.append((q, K, V))
    named["rising scores"] = cases
    return named


def main():
    rng = random.Random(298)
    lines = ["# Accuracy report", "",
             "Error = |chip output − float attention output|, in real output units "
             "(INT4 values span −8 to 7). The output is rounded to 1/16, so ~0.03 "
             "is the floor.", ""]

    # ---- 1 and 2: INT4 random ----
    lines += ["## INT4, random inputs", "",
              "| Tokens | Trials | Chip mean | Chip p99 | Chip max | Old 23/32 max | Online max |",
              "|---|---|---|---|---|---|---|"]
    widths = {}
    for n in (1, 2, 4, 8, 16):
        chip_err, old_err, online_err = [], [], []
        for q, K, V in random_cases(rng, n, 3000):
            ref = float_attention(q, K, V)
            chip = [c / OUT_FRAC for c in chip_attention(q, K, V)]
            # Sanity: the generic model must agree with the official one
            assert chip == two_pass(q, K, V, TABLE_CHIP, widths), "generic model drifted"
            chip_err += list(np.array(chip) - ref)
            old_err += list(np.array(two_pass(q, K, V, TABLE_OLD, {})) - ref)
            online_err += list(np.array(online(q, K, V, TABLE_CHIP)) - ref)
        m, p, x = stats(chip_err)
        lines.append(f"| {n} | 3000 | {m} | {p} | {x} | {stats(old_err)[2]} | {stats(online_err)[2]} |")
    lines.append("")

    # ---- nasty cases ----
    lines += ["## INT4, nasty cases (16 tokens)", "",
              "| Case | Chip max | Old 23/32 max | Online max |", "|---|---|---|---|"]
    for name, cases in nasty_cases(rng).items():
        chip_err, old_err, online_err = [], [], []
        for q, K, V in cases:
            ref = float_attention(q, K, V)
            chip_err += list(np.array([c / OUT_FRAC for c in chip_attention(q, K, V)]) - ref)
            old_err += list(np.array(two_pass(q, K, V, TABLE_OLD, {})) - ref)
            online_err += list(np.array(online(q, K, V, TABLE_CHIP)) - ref)
        lines.append(f"| {name} | {stats(chip_err)[2]} | {stats(old_err)[2]} | {stats(online_err)[2]} |")
    lines.append("")

    # ---- 3: INT8 ----
    lines += ["## INT8 (same design, wider registers), random inputs", "",
              "Values span −128 to 127 here, so errors are also shown as a % of that range.", "",
              "| Tokens | Trials | Mean | Max | Max as % of range | Avg # tokens with nonzero weight |",
              "|---|---|---|---|---|---|"]
    w8 = {}
    for n in (16, 128):
        err, alive = [], []
        for q, K, V in random_cases(rng, n, 500, bits=8):
            ref = float_attention(q, K, V)
            err += list(np.array(two_pass(q, K, V, TABLE_CHIP, w8)) - ref)
            S = [int(np.dot(q, k)) for k in K]
            alive.append(sum(1 for s in S if max(S) - s < 13))
        m, _, x = stats(err)
        lines.append(f"| {n} | 500 | {m} | {x} | {100 * float(x) / 256:.2f}% | {np.mean(alive):.2f} |")
    lines.append("")

    def bits_unsigned(x):
        return max(1, int(x).bit_length())

    def bits_signed(x):
        return int(x).bit_length() + 1

    lines += ["## Register widths seen", "",
              "| Register | INT4 now (max seen, bits) | INT8 at 128 tokens (max seen, bits) |",
              "|---|---|---|",
              f"| score S (signed) | {widths['S']}, {bits_signed(widths['S'])} | {w8['S']}, {bits_signed(w8['S'])} |",
              f"| weight sum L | {widths['L']}, {bits_unsigned(widths['L'])} | {w8['L']}, {bits_unsigned(w8['L'])} |",
              f"| weighted sum O (signed) | {widths['O']}, {bits_signed(widths['O'])} | {w8['O']}, {bits_signed(w8['O'])} |",
              "", "Max seen on random data, not the worst case. Worst case below.", ""]

    # Exact worst cases. Divider numerator is 16·|O|.
    lines += ["## Register widths, worst case", "",
              "| Config | S | L | O | Divider numerator (16 × O) |",
              "|---|---|---|---|---|"]
    for name, vbits, n, wbits in (("INT4, 16 tokens, 8-bit W (now)", 4, 16, 8),
                                  ("INT4, 128 tokens, 8-bit W", 4, 128, 8),
                                  ("INT4, 128 tokens, 12-bit W", 4, 128, 12),
                                  ("INT8, 128 tokens, 8-bit W", 8, 128, 8),
                                  ("INT8, 128 tokens, 12-bit W", 8, 128, 12)):
        lo = 1 << (vbits - 1)                  # most negative value magnitude
        s_max = 4 * lo * lo                    # (-8)·(-8)·4 or (-128)·(-128)·4
        w_max = (1 << wbits) - 1
        l_max = n * w_max
        o_max = n * w_max * lo                 # all values at -lo
        lines.append(f"| {name} | {bits_signed(s_max)} | {bits_unsigned(l_max)} | "
                     f"{bits_signed(o_max)} | "
                     f"{bits_unsigned(16 * o_max)} |")
    lines.append("")

    # ---- lost tail: many small weights rounded to 0 ----
    def table(bits):
        top = (1 << bits) - 1
        t, D = [], 0
        while round(top * math.exp(-D / 2)) > 0:
            t.append(round(top * math.exp(-D / 2)))
            D += 1
        return t

    lines += ["## Lost tail: one leader, everyone else far behind", "",
              "Token 0 has the top score and value −8. All other tokens sit D below it "
              "with value 7. Each one alone barely matters, but a crowd adds up. "
              "8-bit weights round each of them to 0 (D ≥ 13), so the chip just outputs −8.", "",
              "| Tokens | D | Float | Chip (8-bit weights) | Error | 10-bit | 12-bit | 16-bit |",
              "|---|---|---|---|---|---|---|---|"]
    for n in (16, 128):
        for d in (12, 13, 14):
            q = [1, 0, 0, 0]
            K = [[7, 0, 0, 0]] + [[7 - d, 0, 0, 0]] * (n - 1)
            V = [[-8] * 4] + [[7] * 4] * (n - 1)
            ref = float(float_attention(q, K, V)[0])
            chip = two_pass(q, K, V, TABLE_CHIP, {})[0]
            wider = [abs(two_pass(q, K, V, table(b), {})[0] - ref) for b in (10, 12, 16)]
            lines.append(f"| {n} | {d} | {ref:.3f} | {chip:.3f} | {abs(chip - ref):.3f} | "
                         + " | ".join(f"{e:.3f}" for e in wider) + " |")
    lines += ["", "Wider columns use an exact e^(−D/2) table at that width "
              f"(10-bit: {len(table(10))} entries, 12-bit: {len(table(12))}, 16-bit: {len(table(16))}).", ""]

    # ---- weight table comparison ----
    lines += ["## Weight table: chip now (exact) vs old 23/32 trick", "",
              "| D | " + " | ".join(str(d) for d in range(13)) + " |",
              "|---" * 14 + "|",
              "| chip now (exact) | " + " | ".join(str(w) for w in TABLE_CHIP) + " |",
              "| old 23/32 trick | " + " | ".join(str(w) for w in TABLE_OLD) + " |",
              "| 255·e^(−D/2) | " + " | ".join(f"{255 * math.exp(-d / 2):.1f}" for d in range(13)) + " |", ""]

    report = "\n".join(lines)
    print(report)
    (Path(__file__).resolve().parent / "accuracy_report.md").write_text(report)


if __name__ == "__main__":
    main()
