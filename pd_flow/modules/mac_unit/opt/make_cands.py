#!/usr/bin/env python3
"""make_cands.py: candidates (candidates/) and golden cosmetic rewrites (variants/) as exact, asserted
text substitutions on the immutable golden snapshot/mac_unit.v. Every name the tests or the cone rule
use (ring, S, L, ports, parameter) is kept."""
import os
H = os.path.dirname(os.path.abspath(__file__))
G = open(os.path.join(H, "../snapshot/mac_unit.v")).read()
X = "    wire [8:0] x = accum_mode ? {1'b0, W} : {qi[7], qi};\n"
TERM = "    wire [21:0] term = bit_on ? ({{13{x[8]}}, x} << bit_sel) : 22'd0;\n"
ADD = "    ripple_add #(.N(22)) adder (.a(a), .b(neg ? ~term : term), .cin(neg), .s(sum));\n"
LADD = "    ripple_add #(.N(12)) l_adder (.a(first ? 12'd0 : L), .b({4'b0, W}), .cin(1'b0), .s(L_next));\n"
SUPD = ("        if (load) S <= subtract ? M : 22'sd0;\n"
        "        else if (score_en) S <= $signed(sum);\n")
A = "    wire [21:0] a = accum_mode ? (load_o ? 22'd0 : {{2{O0[19]}}, O0}) : S;\n"
RING = "        ring <= {accum_mode ? sum[19:0] : O0, ring[20*OUTPUTS-1:20]};\n"
LUPD = "        if (accum_en && ~|sel && bit_sel == 3'd0) L <= L_next;\n"
# c01: invert before the shift (9 XORs instead of 22); the shifter fills the low bits with neg.
PREXOR_OR = (TERM, "    wire [8:0] xn = bit_on ? x ^ {9{neg}} : {9{neg}};\n"
    "    wire [21:0] term = ({{13{xn[8]}}, xn} << bit_sel) | ({22{neg}} & ~(22'h3FFFFF << bit_sel));\n")
PREXOR_SR = (TERM, "    wire [8:0] xn = bit_on ? x ^ {9{neg}} : {9{neg}};\n"
    "    wire [28:0] t29 = {{13{xn[8]}}, xn, {7{neg}}};\n"
    "    wire [28:0] tsh = t29 >> (3'd7 - bit_sel);\n"
    "    wire [21:0] term = tsh[21:0];\n"
    "    wire _unused_t = &{tsh[28:22], 1'b0};\n")
PREXOR_ADD = (ADD, "    ripple_add #(.N(22)) adder (.a(a), .b(term), .cin(neg), .s(sum));\n")
# c02: negate the 9-bit multiplicand before the shift (x in [-128, 255], so -x fits 9 bits); cin = 0.
PRENEG = (TERM, "    wire [8:0] xn = bit_on ? (x ^ {9{neg}}) + {8'd0, neg} : 9'd0;\n"
    "    wire [21:0] term = {{13{xn[8]}}, xn} << bit_sel;\n")
PRENEG_ADD = (ADD, "    ripple_add #(.N(22)) adder (.a(a), .b(term), .cin(1'b0), .s(sum));\n")
PLUS_ADD = (ADD, "    assign sum = a + (neg ? ~term : term) + {21'd0, neg};\n")
PLUS_L = (LADD, "    assign L_next = (first ? 12'd0 : L) + {4'b0, W};\n")
LMUX = (LADD, "    wire [11:0] L_sum;\n"
    "    ripple_add #(.N(12)) l_adder (.a(L), .b({4'b0, W}), .cin(1'b0), .s(L_sum));\n"
    "    assign L_next = first ? {4'b0, W} : L_sum;\n")
SEN = (SUPD, "        if (load || score_en) S <= load ? (subtract ? M : 22'sd0) : $signed(sum);\n")
# c06: gate the 9-bit multiplicand with bit_on before the shift (9 ANDs instead of 22).
GATEPRE = (TERM, "    wire [8:0] xg = bit_on ? x : 9'd0;\n"
    "    wire [21:0] term = {{13{xg[8]}}, xg} << bit_sel;\n")
# c07: gate and invert before the shift; the right-shift form fills the low bits with neg.
GATEXOR_SR = (TERM, "    wire [8:0] xn = (bit_on ? x : 9'd0) ^ {9{neg}};\n"
    "    wire [28:0] t29 = {{13{xn[8]}}, xn, {7{neg}}};\n"
    "    wire [28:0] tsh = t29 >> (3'd7 - bit_sel);\n"
    "    wire [21:0] term = tsh[21:0];\n"
    "    wire _unused_t = &{tsh[28:22], 1'b0};\n")
# c14: c09 with the inverted multiplicand built per mode (score: sext(qi), accumulate: {0, W}).
XN_MODE = (PREXOR_SR[1].split("\n")[0] + "\n", "    wire [8:0] xn = accum_mode ? ((accum_en && v[bit_sel]) ? {neg, W ^ {8{neg}}} : {9{neg}})\n"
    "                              : (ki[bit_sel] ? {qi[7], qi} ^ {9{neg}} : {9{neg}});\n")
CANDS = {
    "c01_prexor_or": [PREXOR_OR, PREXOR_ADD],
    "c01b_prexor_sr": [PREXOR_SR, PREXOR_ADD],
    "c02_preneg": [PRENEG, PRENEG_ADD],
    "c03a_plus_main": [PLUS_ADD],
    "c03b_plus_l": [PLUS_L],
    "c03c_plus_both": [PLUS_ADD, PLUS_L],
    "c04_lmux": [LMUX],
    "c05_s_en": [SEN],
    "c06_gatepre": [GATEPRE],
    "c07_gatexor_sr": [GATEXOR_SR, PREXOR_ADD],
    "c08_gatepre_lmux": [GATEPRE, LMUX],
    "c09_prexor_sr_lmux": [PREXOR_SR, PREXOR_ADD, LMUX],
    "c10_gatexor_sr_lmux": [GATEXOR_SR, PREXOR_ADD, LMUX],
    "c11_prexor_or_lmux": [PREXOR_OR, PREXOR_ADD, LMUX],
    "c12_preneg_lmux": [PRENEG, PRENEG_ADD, LMUX],
    "c13_prexor_sr_plusl": [PREXOR_SR, PREXOR_ADD, PLUS_L],
    "c14_xn_mode_lmux": [PREXOR_SR, XN_MODE, PREXOR_ADD, LMUX, (X, ""),
                         ("    wire bit_on = accum_mode ? (accum_en && v[bit_sel]) : ki[bit_sel];\n", "")],
}
VARS = {
    "v1_xorneg": [(ADD, ADD.replace("neg ? ~term : term", "term ^ {22{neg}}"))],
    "v2_top_and": [("wire top = bit_sel == 3'd7;", "wire top = &bit_sel;")],
    "v3_lcond": [(LUPD, "        if (accum_en && !sel && !bit_sel) L <= L_next;\n")],
    "v4_xmux_inv": [(X, "    wire [8:0] x = !accum_mode ? {qi[7], qi} : {1'b0, W};\n")],
    "v5_amux_inv": [(A, "    wire [21:0] a = !accum_mode ? S : load_o ? 22'd0 : {{2{O0[19]}}, O0};\n")],
    "v6_ring_inv": [(RING, "        ring <= {!accum_mode ? O0 : sum[19:0], ring[20*OUTPUTS-1:20]};\n")],
    # structural rewrites (the v1..v6 texts above give the golden netlist bit for bit)
    "n1_amux_andor": [(A, "    wire [21:0] a = ({22{accum_mode & ~load_o}} & {{2{O0[19]}}, O0}) | ({22{~accum_mode}} & S);\n")],
    "n2_ring_xor": [(RING, "        ring <= {O0 ^ ({20{accum_mode}} & (sum[19:0] ^ O0)), ring[20*OUTPUTS-1:20]};\n")],
    "n3_l_and": [(LADD, LADD.replace("first ? 12'd0 : L", "L & {12{~first}}"))],
    "n4_biton_mask": [("(accum_en && v[bit_sel]) : ki[bit_sel]", "(accum_en && |(v & (8'd1 << bit_sel))) : |(ki & (8'd1 << bit_sel))")],
    "n5_term_mul": [(TERM, "    wire [21:0] term = {{13{x[8]}}, x} * {14'd0, bit_on, 7'd0} >> (3'd7 - bit_sel);\n")],
    "n6_neg_sop": [("    wire neg = accum_mode ? (accum_en && top) : (top ^ subtract);\n",
                    "    wire neg = (top & (accum_mode ? accum_en : ~subtract)) | (~top & ~accum_mode & subtract);\n")],
    "n7_xmux_andor": [(X, "    wire [8:0] x = ({9{accum_mode}} & {1'b0, W}) | ({9{~accum_mode}} & {qi[7], qi});\n")],
    "n8_amux_mask": [(A, "    wire [21:0] a = accum_mode ? ({22{~load_o}} & {{2{O0[19]}}, O0}) : S;\n")],
    "n9_s_and": [(SUPD, "        if (load) S <= {22{subtract}} & M;\n        else if (score_en) S <= $signed(sum);\n")],
    "n10_neg_xor": [("    wire neg = accum_mode ? (accum_en && top) : (top ^ subtract);\n",
                     "    wire neg = ((accum_mode ? accum_en : 1'b1) & top) ^ (~accum_mode & subtract);\n")],
    "n11_ring_andor": [(RING, "        ring <= {({20{accum_mode}} & sum[19:0]) | ({20{~accum_mode}} & O0), ring[20*OUTPUTS-1:20]};\n")],
    "n12_biton_shr": [("(accum_en && v[bit_sel]) : ki[bit_sel]", "(accum_en && (v >> bit_sel) & 8'd1) : |((ki >> bit_sel) & 8'd1)")],
}
def apply(subs, base=G):
    t = base
    for o, n in subs:
        assert t.count(o) == 1, o
        t = t.replace(o, n)
    return t
if __name__ == "__main__":
    import sys
    for d, tab in (("candidates", CANDS), ("variants", VARS)):
        os.makedirs(os.path.join(H, d), exist_ok=True)
        for k, s in tab.items():
            open(os.path.join(H, d, k + ".v"), "w").write(apply(s))
            print(d, k)
