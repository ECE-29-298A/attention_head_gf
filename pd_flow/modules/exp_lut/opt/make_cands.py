#!/usr/bin/env python3
"""make_cands.py: write candidates/<name>.v. Each candidate is the golden snapshot with only the
weight logic (golden lines 55..109) replaced; header, port list, REGISTERED generate block and
handshake are byte-identical to the golden. Tables are generated from the spec formula
round(255*e^(-k/4)), k = 0..24, and checked against the golden's literal table."""
import math, os, re
HERE = os.path.dirname(os.path.abspath(__file__))
G = open(os.path.join(HERE, "../snapshot/exp_lut.v")).read().split("\n")
HEAD, GOLD_BODY, TAIL = G[:54], G[54:109], G[109:]
assert GOLD_BODY[0].startswith("wire [21:0] diff = D;") and TAIL[1].startswith("if (REGISTERED)")

T = [round(255 * math.exp(-k / 4)) for k in range(25)]
golden_lits = [int(x) for x in re.findall(r"5'd\d+:\s*weight = 8'd(\d+);", "\n".join(GOLD_BODY))]
assert golden_lits == T, golden_lits
T2 = [T[(a + 1) >> 1] if (a + 1) >> 1 < 25 else 0 for a in range(64)]  # folded rounding

SHIFTER = """wire [20:0] delta_guard = {D[19:0], 1'b0};
wire [12:0] stage8 = shift[3] ? delta_guard[20:8] : delta_guard[12:0];
wire [8:0] stage4 = shift[2] ? stage8[12:4] : stage8[8:0];
wire [6:0] stage2 = shift[1] ? stage4[8:2] : stage4[6:0];
wire [5:0] aligned = shift[0] ? stage2[6:1] : stage2[5:0];
"""
OVF = """wire window_ovf = (|D[21:20]) ||
    (!shift[3] && (|delta_guard[20:13])) ||
    (!shift[2] && (|stage8[12:9])) ||
    (!shift[1] && (|stage4[8:7])) ||
    (!shift[0] && stage2[6]);
"""


def case5(sel, var="weight", width=5):
    s = [f"        case ({sel})"]
    for k, v in enumerate(T):
        s.append(f"            {width}'d{k}: {var} = 8'd{v};")
    s.append(f"            default: {var} = 8'd0;")
    s.append("        endcase")
    return "\n".join(s)


def case6(sel, var="weight", grouped=True):
    s = [f"        case ({sel})"]
    if grouped:
        s.append(f"            6'd0: {var} = 8'd{T[0]};")
        for k in range(1, 25):
            s.append(f"            6'd{2*k-1}, 6'd{2*k}: {var} = 8'd{T[k]};")
    else:
        for a in range(49):
            s.append(f"            6'd{a}: {var} = 8'd{T2[a]};")
    s.append(f"            default: {var} = 8'd0;")
    s.append("        endcase")
    return "\n".join(s)


B = {}
# c01: fold the rounding increment into a 6-bit table indexed by the window (2D >> shift).
B["c01_fold"] = f"""// Rounding folded into the table: aligned = floor(2D / 2^shift) (6-bit window),
// D' = (aligned + 1) >> 1, so the table is indexed by aligned directly (49 non-zero entries).
{SHIFTER}{OVF}
reg [7:0] weight;
always @(*) begin
    if (window_ovf) begin
        weight = 8'd0;
    end else begin
{case6("aligned")}
    end
end
"""
# c02: golden datapath; overflow saturates the index (5 ORs) instead of zeroing W (8 ANDs).
B["c02_sat"] = f"""{SHIFTER}wire [5:0] index = {{1'b0, aligned[5:1]}} + {{5'b0, aligned[0]}};
{OVF}wire [4:0] sat_index = (window_ovf || index[5]) ? 5'd31 : index[4:0];

reg [7:0] weight;
always @(*) begin
{case5("sat_index")}
end
"""
# c03: fold + saturate the 6-bit window to 63 (table entry 0).
B["c03_fold_sat"] = f"""{SHIFTER}{OVF}wire [5:0] sat_aligned = window_ovf ? 6'd63 : aligned;

reg [7:0] weight;
always @(*) begin
{case6("sat_aligned")}
end
"""
# c04: radix-4 shifter (shift[3:2] then shift[1:0]) written as case muxes, golden rounding.
B["c04_radix4"] = """wire [20:0] delta_guard = {D[19:0], 1'b0};
reg [8:0] coarse;   // window of 9 bits at offset 4*shift[3:2]
reg coarse_ovf;
always @(*) begin
    case (shift[3:2])
        2'd0: begin coarse = delta_guard[8:0];   coarse_ovf = |delta_guard[20:9];  end
        2'd1: begin coarse = delta_guard[12:4];  coarse_ovf = |delta_guard[20:13]; end
        2'd2: begin coarse = delta_guard[16:8];  coarse_ovf = |delta_guard[20:17]; end
        default: begin coarse = delta_guard[20:12]; coarse_ovf = 1'b0; end
    endcase
end
reg [5:0] aligned;
reg fine_ovf;
always @(*) begin
    case (shift[1:0])
        2'd0: begin aligned = coarse[5:0]; fine_ovf = |coarse[8:6]; end
        2'd1: begin aligned = coarse[6:1]; fine_ovf = |coarse[8:7]; end
        2'd2: begin aligned = coarse[7:2]; fine_ovf = coarse[8];    end
        default: begin aligned = coarse[8:3]; fine_ovf = 1'b0;     end
    endcase
end
wire [5:0] index = {1'b0, aligned[5:1]} + {5'b0, aligned[0]};
wire out_of_range = (|D[21:20]) || coarse_ovf || fine_ovf || index[5];

reg [7:0] weight;
always @(*) begin
    if (out_of_range) begin
        weight = 8'd0;
    end else begin
""" + case5("index[4:0]") + """
    end
end
"""
# c05: radix-4 shifter + folded table.
B["c05_radix4_fold"] = B["c04_radix4"].split("wire [5:0] index")[0] + """wire window_ovf = (|D[21:20]) || coarse_ovf || fine_ovf;

reg [7:0] weight;
always @(*) begin
    if (window_ovf) begin
        weight = 8'd0;
    end else begin
""" + case6("aligned") + """
    end
end
"""
# c06: fold, table listed per window value (ungrouped case items).
B["c06_fold_flat"] = B["c01_fold"].replace(case6("aligned"), case6("aligned", grouped=False))
# c07: D' computed as (D >> shift) + round bit with an explicit round-bit mux (no guard zero).
B["c07_roundbit"] = """wire [12:0] s8 = shift[3] ? D[20:8] : D[12:0];
wire [8:0] s4 = shift[2] ? s8[12:4] : s8[8:0];
wire [6:0] s2 = shift[1] ? s4[8:2] : s4[6:0];
wire [5:0] s1 = shift[0] ? s2[6:1] : s2[5:0];        // D >> shift, low 6 bits
// round bit D[shift-1] (0 at shift 0), selected with the same staged structure
wire [7:0] r8 = shift[3] ? D[14:7] : {D[6:0], 1'b0};  // r8[i] = D[i-1+8*shift[3]]
wire [3:0] r4 = shift[2] ? r8[7:4] : r8[3:0];
wire [1:0] r2 = shift[1] ? r4[3:2] : r4[1:0];
wire round_bit = shift[0] ? r2[1] : r2[0];
wire [5:0] index = {1'b0, s1[4:0]} + {5'b0, round_bit};
wire out_of_range = (|D[21:21]) || s1[5] || index[5] ||
    (!shift[3] && (|D[20:13])) || (!shift[2] && (|s8[12:9])) ||
    (!shift[1] && (|s4[8:7])) || (!shift[0] && s2[6]);

reg [7:0] weight;
always @(*) begin
    if (out_of_range) begin
        weight = 8'd0;
    end else begin
""" + case5("index[4:0]") + """
    end
end
"""

# Don't-care merging: when a stage keeps its low window (shift bit 0), a set bit among the
# discarded high bits already forces W = 0 (window_ovf). So for the window positions whose
# shifted-in source is one of those discarded bits, the mux may be replaced by an OR:
#   shift ? hi : lo  ->  hi | (!shift & lo)
# (equal when shift = 1; when shift = 0 it differs only if hi = 1, which is an overflow).
# The overflow terms stay correct on the merged values because OR only adds ones, and an added
# one appears only when a discarded bit of an earlier stage is set (already an overflow).
ORSHIFTER = """wire [20:0] dg = {D[19:0], 1'b0};
wire [12:0] w8 = {dg[20:13] | ({8{!shift[3]}} & dg[12:5]),
                  shift[3] ? dg[12:8] : dg[4:0]};
wire [8:0] w4 = {w8[12:9] | ({4{!shift[2]}} & w8[8:5]),
                 shift[2] ? w8[8:4] : w8[4:0]};
wire [6:0] w2 = {w4[8:7] | ({2{!shift[1]}} & w4[6:5]),
                 shift[1] ? w4[6:2] : w4[4:0]};
wire [5:0] win = {w2[6] | (!shift[0] & w2[5]),
                  shift[0] ? w2[5:1] : w2[4:0]};
wire win_ovf = (|D[21:20]) ||
    (!shift[3] && (|dg[20:13])) ||
    (!shift[2] && (|w8[12:9])) ||
    (!shift[1] && (|w4[8:7])) ||
    (!shift[0] && w2[6]);
"""
B["c08_ormerge"] = ORSHIFTER + """wire [5:0] rnd = {1'b0, win[5:1]} + {5'b0, win[0]};

reg [7:0] weight;
always @(*) begin
    if (win_ovf || rnd[5]) begin
        weight = 8'd0;
    end else begin
""" + case5("rnd[4:0]") + """
    end
end
"""
B["c09_ormerge_fold"] = ORSHIFTER + """
reg [7:0] weight;
always @(*) begin
    if (win_ovf) begin
        weight = 8'd0;
    end else begin
""" + case6("win") + """
    end
end
"""
# 3-bit saturation: on overflow force win[5], win[4], win[0] to 1, so the index is >= 49
# (110001b), where the folded table is 0. Three ORs instead of zeroing eight W bits.
SAT3 = """wire [5:0] idx = {win[5] | win_ovf, win[4] | win_ovf, win[3:1], win[0] | win_ovf};

reg [7:0] weight;
always @(*) begin
""" + case6("idx") + """
end
"""
B["c10_ormerge_fold_sat3"] = ORSHIFTER + SAT3
B["c11_fold_sat3"] = (SHIFTER + OVF).replace("aligned", "win").replace("window_ovf", "win_ovf") + SAT3

os.makedirs(os.path.join(HERE, "candidates"), exist_ok=True)
for name, body in B.items():
    txt = "\n".join(HEAD) + "\n" + body.rstrip("\n") + "\n" + "\n".join(TAIL)
    open(os.path.join(HERE, "candidates", name + ".v"), "w").write(txt)
    print("wrote", name)
