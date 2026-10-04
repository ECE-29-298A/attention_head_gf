import numpy as np

"""
IMPORTANT INFORMATION:

For Q, K, V:
- Size d = 4
- We are using **INT4**

4 * 4 = 16 bits -> 2 bytes

byte 1: [Q1 | Q0]
byte 0: [Q3 | Q2]


"""

# Build EXP table once
EXP_TABLE = [round(255 * 2 ** (-r / 16)) for r in range(16)]
# = [255, 244, 234, 224, 214, 205, 197, 188, 180, 173, 165, 158, 152, 145, 139, 133]

# === BIT HELPERS ===

def signed4(n: int) -> int:
    """Turning unsigned number into signed number

    [0...15] to [-8...7]

    Meaning, we have to shift 8...15 to -8...-1

    Args:
        n (int): unsigned INT4
    
    Returns:
        int: signed INT4
    """
    return n - 16 if n > 7 else n


def unpack_byte(b: int) -> tuple[int, int]:
    """Separating a number into the lower and upper 4 bits.

    Args:
        b (int): input

    Returns:
        tuple[int, int]: signed low and high
    """
    low = b & 0xF
    high = (b >> 4) & 0xF
    return (signed4(low), signed4(high))


def pack_byte(lo: int, hi: int) -> int:
    """Combining the lower and upper 4 bits into a number

    Args:
        lo (int): lower 4 bits
        hi (int): upper 4 bits

    Returns:
        int: unsigned number
    """

    # Mask out negative numbers
    assert -8 <= lo <= 7 and -8 <= hi <= 7, f"out of INT4 range: {lo}, {hi}"

    return ((hi & 0xF) << 4) | (lo & 0xF)


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

def dot4(q: list[int], k: list[int]) -> int:
    """_summary_

    Args:
        q (list[int]): Vector Q
        k (list[int]): Vector K

    Returns:
        int: Dot product of the two vectors
    """
    assert len(q) == 4 and len(k) == 4, "q and k must have 4 values"
    assert all(-8 <= v <= 7 for v in q + k), f"values out of INT4 range: {q}, {k}"

    # Initiate sum
    S = 0
    for x, y in zip(q, k): # Iterate through them
        S = check_width(S + x * y, 10, signed=True, name="S")
    return S


def exp_weight(M: int, S: int) -> int:
    """Softmax step

    We want to calculate W ≈ 255 · e^((S - M) / 2)
    However, there aint no way we're calculating e^x in this
    So, rewriting e as a power of 2:
        e^(-D/2) = 2^(-D / (2 ln 2)) = 2^(-0.7213 · D)
    We can rewrite the original equation as
    W = 255 · 2^(-23D/32)

    Args:
        M (int): _description_
        S (int): _description_

    Returns:
        int: _description_
    """

    D = check_width(M - S, 9, signed=False, name="D")

    # e^(−D/2) = 2^(−0.721·D) ---> 2^(−23D/32)
    # So we need to compute the 23/32 trick

    A = check_width(23 * D, 14, signed=False, name="A")

    # Split A into a whole part and a fraction part
    n = A >> 5 # n = A * 32
    r = (A >> 1) & 0xF # r = lower 4 bits of A * 64

    T = EXP_TABLE[r] # Look up the fractional part

    # Apply the whole part as a right shift, with rounding
    if n == 0:
        W = T
    elif n <= 8:
        W = (T + (1 << (n - 1))) >> n
    else:
        W = 0

    return check_width(W, 8, signed=False, name="W")

def divide_round(O: int, L: int) -> int:
    """Output code = round(16 * O / L), the chip's way. Value = code / 16

    We multiply O by 16 so the answer keeps 4 bits after the binary point.
    We'll divide the output by 16 later

    Args:
        O (int): sum of weight x value for all the tokens
        L (int): sum of all the weights

    Returns:
        int: _description_
    """
    # L must be positive 
    assert L > 0, "L must be positive"

    # Save the sign
    G = O < 0
    # Numerator is 16 * O
    Z = check_width(16 * abs(O), 19, signed=False, name="Z")

    # using divmod -> (quotient, remainder)
    q, R = divmod(Z, L)

    # Round to the nearest
    if 2 * R >= L:
        q += 1

    # Put signs back 
    code = -q if G else q
    return check_width(code, 8, signed=True, name="output") # Test on return

# === THE CHIP ===

def chip_attention(Q: list[int], K: list[list[int]], V: list[list[int]]) -> list[int]:
    """One attention pass

    1 <= N <= 16

    Args:
        Q (list[int]): 4 ints
        K (list[list[int]]): N vectors of 4 ints each
        V (list[list[int]]): N vectors of 4 ints each

    Returns:
        list[int]: 4 output codes. NOTE: REAL VALUE IS EACH / 16
    """
    # N is the number of K we have.
    N = len(K)
    assert 1 <= N <= 16 and len(V) == N, "womp womp"

    # --- PASS 1 ---

    M = float('-inf')
    for k in K:
        S = dot4(Q, k)
        M = max(M, S) # Finding maximum
    M = int(M)
    check_width(M, 10, signed=True, name="M")

    # --- PASS 2 ---

    L = 0; O = [0, 0, 0, 0]
    for k, v in zip(K, V):
        S = dot4(Q, k) # The chip is stupid we forgor about the value so we have to recalculate
        W = exp_weight(M, S) # Turn the score into weight
        L = check_width(L + W, 12, signed=False, name="L") # Add to running total
        # Add W x V to running sums O
        for i in range(4):
            # Make sure it's still within INT4 range
            assert -8 >= v[i] <= 7, f"value out of INT4 range: {v}"
            O[i] = check_width(O[i] + W * v[i], 16, signed=True, name=f"O{i}")

    # --- Divide ---

    # We divide each sum by L (big L)
    return [divide_round(O[i], L) for i in range(4)]

# === TRUE NUMPY ATTENTION ===


# Thank you Claude Code

def float_attention(q: list[int], keys: list[list[int]], values: list[list[int]]) -> np.ndarray:
    """Exact attention with normal decimal numbers. The 'true answer' to compare the chip against

    Args:
        q (list[int]): query vector, 4 values
        keys (list[list[int]]): N key vectors, 4 values each
        values (list[list[int]]): N value vectors, 4 values each

    Returns:
        np.ndarray: 4 output values as floats (real values, not /16 codes)

    """
    q_array = np.array(q, dtype=float)  # shape (4,)
    K = np.array(keys, dtype=float)     # shape (N, 4): one row per token
    V = np.array(values, dtype=float)   # shape (N, 4)

    scores = K @ q_array / np.sqrt(len(q_array))  # 1. all N scores at once, divided by √d = 2
    w = np.exp(scores - scores.max())   # 2. e^(score - max), same trick as the chip
    w = w / w.sum()                     # 3. make the weights add up to 1
    return w @ V                        # 4. weighted average of the values, shape (4,)