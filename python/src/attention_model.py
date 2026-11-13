"""
By: Jinyuan Zhao

This is a model of our chip: INT8, two-pass softmax, 8-bit weights from a LUT.

The chip is d = 4, up to 16 tokens. Everything here also takes other head
sizes d and token limits n_max (e.g. d = 64 for SmolLM) so we can see what
a bigger chip would do and how wide its registers must be: reg_widths().

score_shift = 0 is the chip as built. score_shift = k looks up D >> k, i.e.
k fewer score bits matter (needed when real scores are much bigger than the
LUT's 1 unit = 0.5 nat). NOT IN RTL YET.

Two versions, bit-identical:
- chip_attention():    plain Python, one query, readable
- chip_attention_np(): numpy, any batch shape, fast enough for a real model
"""

import math

import numpy as np


# Build EXP table once: EXP_TABLE[D] = round(255 · e^(-D/2))
# Scores are whole numbers, so D = M - S is too, and from D = 13 on the
# weight rounds to 0. So 13 entries cover everything.
EXP_TABLE = [round(255 * math.exp(-D / 2)) for D in range(13)]
# = [255, 155, 94, 57, 35, 21, 13, 8, 5, 3, 2, 1, 1]

# === BIT HELPERS ===

def signed8(n: int) -> int:
    """Byte [0...255] to signed INT8 [-128...127]."""
    return n - 256 if n > 127 else n


def pack_byte(v: int) -> int:
    """Signed INT8 to the byte stored in memory."""
    assert -128 <= v <= 127, f"out of INT8 range: {v}"
    return v & 0xFF


def reg_widths(d: int = 4, n_max: int = 16) -> dict[str, int]:
    """Register widths (bits) the chip needs for head size d and up to n_max tokens.

    d = 4, n_max = 16 gives the RTL: S 18, D 17, L 12, O 20, Z 19.
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


def exp_weight(M: int, S: int, d: int = 4, score_shift: int = 0) -> int:
    """Softmax step

    We want to calculate W ≈ 255 · e^((S - M) / 2)
    There aint no way we're calculating e^x in hardware, BUT:
    S and M are whole numbers, so D = M - S is a whole number too,
    and once D >= 13 the weight rounds to 0 anyway.
    So we just precompute the 13 answers and look D up.

    (Old version used the 23/32 trick: W = 255 · 2^(-23D/32), table + shifter.
    Only 13 answers either way, and this table is the exact e^x, so it's
    both smaller in hardware and more accurate.)

    Args:
        M (int): maximum score
        S (int): this token's score
        d (int): head size, only for the width check
        score_shift (int): look up D >> score_shift (0 = the chip)

    Returns:
        int: weight, 0 to 255
    """

    D = check_width(M - S, reg_widths(d)["D"], signed=False, name="D") >> score_shift

    W = EXP_TABLE[D] if D < len(EXP_TABLE) else 0

    return check_width(W, 8, signed=False, name="W")

def divide_round(O: int, L: int, n_max: int = 16) -> int:
    """Output = round(O / L), the chip's way: an INT8 weighted average of V.

    Args:
        O (int): sum of weight x value for all the tokens
        L (int): sum of all the weights

    Returns:
        int: signed INT8 output
    """
    # L must be positive 
    assert L > 0, "L must be positive"

    # Save the sign
    G = O < 0
    Z = check_width(abs(O), reg_widths(n_max=n_max)["Z"], signed=False, name="Z")

    # using divmod -> (quotient, remainder)
    q, R = divmod(Z, L)

    # Round to the nearest
    if 2 * R >= L:
        q += 1

    # Put signs back 
    code = -q if G else q
    return check_width(code, 8, signed=True, name="output") # Test on return

# === THE CHIP ===

def chip_attention(Q: list[int], K: list[list[int]], V: list[list[int]],
                   n_max: int = 16, score_shift: int = 0) -> list[int]:
    """One attention pass

    1 <= N <= n_max. Head size d = len(Q) (the chip: d = 4, n_max = 16).

    Args:
        Q (list[int]): d ints
        K (list[list[int]]): N vectors of d ints each
        V (list[list[int]]): N vectors of d ints each
        n_max (int): token limit the registers are sized for
        score_shift (int): see exp_weight (0 = the chip)

    Returns:
        list[int]: d INT8 outputs
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

    L = 0; O = [0] * d
    for k, v in zip(K, V):
        S = dot(Q, k) # The chip is stupid we forgor about the value so we have to recalculate
        W = exp_weight(M, S, d, score_shift) # Turn the score into weight
        L = check_width(L + W, bits["L"], signed=False, name="L") # Add to running total
        # Add W x V to running sums O
        assert len(v) == d and all(-128 <= x <= 127 for x in v), f"value out of INT8 range: {v}"
        for i in range(d):
            O[i] = check_width(O[i] + W * v[i], bits["O"], signed=True, name=f"O{i}")

    # --- Divide ---

    # We divide each sum by L (big L)
    return [divide_round(O[i], L, n_max) for i in range(d)]


EXP_TABLE_NP = np.array(EXP_TABLE + [0], dtype=np.int64)  # index 13 = "D >= 13"


def chip_attention_np(Q: np.ndarray, K: np.ndarray, V: np.ndarray,
                      score_shift: int = 0) -> np.ndarray:
    """chip_attention for many queries at once, bit-identical to it.

    Args:
        Q: int, shape (..., d)
        K: int, shape (..., N, d)
        V: int, shape (..., N, d)
        score_shift: see exp_weight (0 = the chip)

    Returns:
        np.ndarray: int64, shape (..., d), INT8 outputs
    """
    Q, K, V = (np.asarray(x, dtype=np.int64) for x in (Q, K, V))
    for x in (Q, K, V):
        assert x.min() >= -128 and x.max() <= 127, "values out of INT8 range"
    S = np.einsum("...nd,...d->...n", K, Q)                       # all scores
    D = (S.max(axis=-1, keepdims=True) - S) >> score_shift        # >= 0
    W = EXP_TABLE_NP[np.minimum(D, len(EXP_TABLE))]               # (..., N)
    L = W.sum(axis=-1, keepdims=True)                             # >= 255: max token has W = 255
    O = np.einsum("...n,...nd->...d", W, V)
    q, R = np.divmod(np.abs(O), L)
    q = q + (2 * R >= L)                                          # nearest, ties away from zero
    return np.where(O < 0, -q, q)

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