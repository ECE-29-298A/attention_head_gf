"""
By: Jinyuan Zhao

This is a model of our chip: INT8 in, two-pass softmax, 8-bit weights from a
LUT, 12-bit outputs (INT8 plus 4 fractional bits).

The chip: scores are d = 64 dot products (one SmolLM head), up to 16 tokens,
and each run outputs 4 of V's components (the host picks which 4, so V passed
here is N x 4). Everything here also takes other sizes d and token limits n_max,
and V may be any width: reg_widths() gives the register widths.

score_shift = k (0..15, sent by the host) looks up round(D / 2^k): raw INT8
scores are far bigger than the LUT's 1 unit = 0.25 nat. score_round = True
(the chip) rounds to nearest by adding 2^(k-1) before the shift; False
truncates, which measurably hurt SmolLM accuracy.

Accuracy fixes, measured on SmolLM by python/smollm_compare.py:
1. Per-channel V scales: host side only, see quantize(). No chip change.
2. lut_res: score units per nat. The LUT holds 255 · e^(-D / lut_res).
   4 = the chip (0.25-nat steps, 25 entries); 2 = the original chip (0.5 nat, 13).
3. out_frac: extra fractional output bits. Outputs are round(O · 2^out_frac / L),
   INT(8 + out_frac) codes in units of 2^-out_frac V steps. 4 = the chip; 0 = original.

Two versions, bit-identical:
- chip_attention():    plain Python, one query, readable
- chip_attention_np(): numpy, any batch shape, fast enough for a real model
"""

import math

import numpy as np


def exp_table(lut_res: int = 4) -> list[int]:
    """EXP_TABLE[D] = round(255 · e^(-D / lut_res)), up to the first D that rounds to 0."""
    table = []
    while (w := round(255 * math.exp(-len(table) / lut_res))) > 0:
        table.append(w)
    return table


# Scores are whole numbers, so D = M - S is too, and from D = 25 on the
# weight rounds to 0. So 25 entries cover everything. Must match src/exp_lut.v.
EXP_TABLE = exp_table(4)
# = [255, 199, 155, 120, 94, 73, 57, 44, 35, 27, 21, 16, 13, 10, 8, 6, 5, 4, 3, 2, 2, 1, 1, 1, 1]

# === BIT HELPERS ===

def signed8(n: int) -> int:
    """Byte [0...255] to signed INT8 [-128...127]."""
    return n - 256 if n > 127 else n


def pack_byte(v: int) -> int:
    """Signed INT8 to the byte stored in memory."""
    assert -128 <= v <= 127, f"out of INT8 range: {v}"
    return v & 0xFF


def reg_widths(d: int = 64, n_max: int = 16) -> dict[str, int]:
    """Register widths (bits) the chip needs for head size d and up to n_max tokens.

    d = 64, n_max = 16 gives the RTL: S 22, D 21, L 12, O 20, Z 19.
    """
    s_max = d * 128 * 128               # largest score: (-128)·(-128)·d
    s_min = d * 128 * 127               # magnitude of the smallest: (-128)·127·d
    o_max = n_max * 255 * 128           # largest |sum of W·v|
    return {
        "S": s_max.bit_length() + 1,    # signed
        "D": (s_max + s_min).bit_length(),
        "L": (n_max * 255).bit_length(),
        "O": o_max.bit_length() + 1,    # signed
        "Z": o_max.bit_length(),        # |O| into the divider
    }


def check_width(x: int, bits: int, signed: bool, name: str = "value") -> int:
    """Assert x fits in a register of the given width. Returns x unchanged

    Args:
        x (int): the number x
        bits (int): given width
        signed (bool): is the number signed
        name (str, optional): Which register overflowed

    Returns:
        int: returning x unchanged (We can check inline if it overflowed)
    """
    # If the number is signed
    if signed:
        lo, hi = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    else:
        lo, hi = 0, (1 << bits) - 1
    assert lo <= x <= hi, f"{name} = {x} does not fit in {bits}-bit {'signed' if signed else 'unsigned'} [{lo}, {hi}]"
    return x

# === CHIP MATH STUFF ===

def dot(q: list[int], k: list[int]) -> int:
    """_summary_

    Args:
        q (list[int]): Vector Q
        k (list[int]): Vector K

    Returns:
        int: Dot product of the two vectors
    """
    assert len(q) == len(k), "q and k must be the same length"
    assert all(-128 <= v <= 127 for v in q + k), f"values out of INT8 range: {q}, {k}"
    bits = reg_widths(len(q))["S"]

    # Initiate sum
    S = 0
    for x, y in zip(q, k): # Iterate through them
        S = check_width(S + x * y, bits, signed=True, name="S")
    return S


def exp_weight(M: int, S: int, d: int = 64, score_shift: int = 0, lut_res: int = 4,
               score_round: bool = True) -> int:
    """Softmax step

    We want to calculate W ≈ 255 · e^((S - M) / 4)
    There aint no way we're calculating e^x in hardware, BUT:
    S and M are whole numbers, so D = M - S is a whole number too,
    and once D >= 25 the weight rounds to 0 anyway.
    So we just precompute the 25 answers and look D up.

    (Old version used the 23/32 trick: W = 255 · 2^(-23D/32), table + shifter.
    Only 13 answers either way, and this table is the exact e^x, so it's
    both smaller in hardware and more accurate.)

    Args:
        M (int): maximum score
        S (int): this token's score
        d (int): head size, only for the width check
        score_shift (int): look up D >> score_shift (0 = the chip)
        lut_res (int): score units per nat (4 = the chip)
        score_round (bool): round D >> score_shift to nearest (True = the chip)

    Returns:
        int: weight, 0 to 255
    """

    D = check_width(M - S, reg_widths(d)["D"], signed=False, name="D")
    D = (D + ((1 << score_shift) >> 1 if score_round else 0)) >> score_shift

    table = exp_table(lut_res)
    W = table[D] if D < len(table) else 0

    return check_width(W, 8, signed=False, name="W")

def divide_round(O: int, L: int, n_max: int = 16, out_frac: int = 4) -> int:
    """Output = round(O · 2^out_frac / L), the chip's way: a weighted average of V.

    Args:
        O (int): sum of weight x value for all the tokens
        L (int): sum of all the weights
        out_frac (int): extra fractional output bits (4 = the chip)

    Returns:
        int: signed INT(8 + out_frac) output
    """
    # L must be positive 
    assert L > 0, "L must be positive"

    # Save the sign
    G = O < 0
    Z = check_width(abs(O), reg_widths(n_max=n_max)["Z"], signed=False, name="Z") << out_frac

    # using divmod -> (quotient, remainder)
    q, R = divmod(Z, L)

    # Round to the nearest
    if 2 * R >= L:
        q += 1

    # Put signs back 
    code = -q if G else q
    return check_width(code, 8 + out_frac, signed=True, name="output") # Test on return

# === THE CHIP ===

def chip_attention(Q: list[int], K: list[list[int]], V: list[list[int]],
                   n_max: int = 16, score_shift: int = 0, lut_res: int = 4,
                   out_frac: int = 4, score_round: bool = True) -> list[int]:
    """One attention pass

    1 <= N <= n_max. Head size d = len(Q) (the chip: d = 64, V width 2, n_max = 16).

    Args:
        Q (list[int]): d ints
        K (list[list[int]]): N vectors of d ints each
        V (list[list[int]]): N vectors of the same width each (the chip: 2)
        n_max (int): token limit the registers are sized for
        score_shift (int): see exp_weight (0 = the chip)
        lut_res (int): see exp_weight (4 = the chip)
        out_frac (int): see divide_round (4 = the chip)
        score_round (bool): see exp_weight (True = the chip)

    Returns:
        list[int]: one INT(8 + out_frac) output per V component
    """
    # N is the number of K we have.
    N = len(K)
    d = len(Q)
    assert 1 <= N <= n_max and len(V) == N, "womp womp"
    bits = reg_widths(d, n_max)

    # --- PASS 1 ---

    M = float('-inf')
    for k in K:
        S = dot(Q, k)
        M = max(M, S) # Finding maximum
    M = int(M)
    check_width(M, bits["S"], signed=True, name="M")

    # --- PASS 2 ---

    dv = len(V[0])
    L = 0; O = [0] * dv
    for k, v in zip(K, V):
        S = dot(Q, k) # The chip is stupid we forgor about the value so we have to recalculate
        W = exp_weight(M, S, d, score_shift, lut_res, score_round) # Turn the score into weight
        L = check_width(L + W, bits["L"], signed=False, name="L") # Add to running total
        # Add W x V to running sums O
        assert len(v) == dv and all(-128 <= x <= 127 for x in v), f"value out of INT8 range: {v}"
        for i in range(dv):
            O[i] = check_width(O[i] + W * v[i], bits["O"], signed=True, name=f"O{i}")

    # --- Divide ---

    # We divide each sum by L (big L)
    return [divide_round(O[i], L, n_max, out_frac) for i in range(dv)]


def chip_attention_np(Q: np.ndarray, K: np.ndarray, V: np.ndarray,
                      score_shift=0, lut_res: int = 4, out_frac: int = 4,
                      score_round: bool = True) -> np.ndarray:
    """chip_attention for many queries at once, bit-identical to it.

    Args:
        Q: int, shape (..., d)
        K: int, shape (..., N, d)
        V: int, shape (..., N, dv), any width dv (the chip: 2)
        score_shift: see exp_weight (0 = the chip); an int or an array of
            shape (..., 1) for a per-query shift
        lut_res: see exp_weight (4 = the chip)
        out_frac: see divide_round (4 = the chip)
        score_round: see exp_weight (True = the chip)

    Returns:
        np.ndarray: int64, shape (..., dv), INT(8 + out_frac) outputs
    """
    Q, K, V = (np.asarray(x, dtype=np.int64) for x in (Q, K, V))
    for x in (Q, K, V):
        assert x.min() >= -128 and x.max() <= 127, "values out of INT8 range"
    S = np.einsum("...nd,...d->...n", K, Q)                       # all scores
    half = (np.int64(1) << score_shift) >> 1 if score_round else 0
    D = (S.max(axis=-1, keepdims=True) - S + half) >> score_shift # >= 0
    table = np.array(exp_table(lut_res) + [0], dtype=np.int64)   # last entry = "D past the table"
    W = table[np.minimum(D, len(table) - 1)]                      # (..., N)
    L = W.sum(axis=-1, keepdims=True)                             # >= 255: max token has W = 255
    O = np.einsum("...n,...nd->...d", W, V) << out_frac
    q, R = np.divmod(np.abs(O), L)
    q = q + (2 * R >= L)                                          # nearest, ties away from zero
    return np.where(O < 0, -q, q)

# === HOST SIDE: REAL NUMBERS TO INT8 ===

def quantize(x: np.ndarray, axis) -> tuple[np.ndarray, np.ndarray]:
    """Power-of-two INT8: x ≈ x_int · 2^-e, one exponent e per slice over axis.

    For V (shape (..., N, d)), axis=-2 gives every column its own scale
    (per-channel). That costs the chip nothing: output column i only ever uses
    V column i, so the host just multiplies output i by 2^-e[i] afterwards.
    Q and K can't do this, because q·k adds all columns together.

    Returns:
        (x_int, e): int64 INT8 values, and int64 exponents (keepdims shape)
    """
    peak = np.maximum(np.abs(x).max(axis=axis, keepdims=True), 1e-30)
    e = np.floor(np.log2(127 / peak)).astype(np.int64)
    return np.clip(np.round(x * 2.0**e), -128, 127).astype(np.int64), e

# === TRUE NUMPY ATTENTION ===


# Thank you Claude Code

def float_attention(q: list[int], keys: list[list[int]], values: list[list[int]]) -> np.ndarray:
    """Exact attention with normal decimal numbers. The 'true answer' to compare the chip against

    Args:
        q (list[int]): query vector, d values
        keys (list[list[int]]): N key vectors, d values each
        values (list[list[int]]): N value vectors, d values each

    Returns:
        np.ndarray: d output values as floats

    """
    q_array = np.array(q, dtype=float)  # shape (d,)
    K = np.array(keys, dtype=float)     # shape (N, d): one row per token
    V = np.array(values, dtype=float)   # shape (N, d)

    scores = K @ q_array / np.sqrt(len(q_array))  # 1. all N scores at once, divided by √d
    w = np.exp(scores - scores.max())   # 2. e^(score - max), same trick as the chip
    w = w / w.sum()                     # 3. make the weights add up to 1
    return w @ V                        # 4. weighted average of the values, shape (d,)