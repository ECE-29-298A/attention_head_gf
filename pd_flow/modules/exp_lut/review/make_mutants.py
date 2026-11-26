#!/usr/bin/env python3
"""Agent 2: generate the RTL mutants of exp_lut from the golden copy (one checked edit each).

Each mutant is written to mutants/<name>.v with a first line
  // mutant <name>: <description>
and MANIFEST.json records class and REGISTERED value(s) the mutation affects:
  class functional-bug         must be killed
        out-of-context-bug     wrong at block level, unobservable in the chip (must be killed)
        structural             timing/structure/interface violation (must be killed)
        equivalent             expected survivor (EQY proof required)
Every edit must match exactly once in the golden (asserted).
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
GOLD = open(os.path.join(HERE, "golden_copy", "exp_lut.v")).read()

# A full alternative formulation used by several mutants: D' at full width, then a table.
def reform(dprime_expr, extra=""):
    """Replace everything from 'wire [21:0] diff' to the end of the weight always block."""
    a = GOLD.index("wire [21:0] diff = D;")
    b = GOLD.index("if (REGISTERED) begin : g_registered")
    table = GOLD[GOLD.index("        case (index[4:0])"):GOLD.index("        endcase") + len("        endcase")]
    table = table.replace("case (index[4:0])", "case (dp[4:0])")
    body = f"""wire [21:0] diff = D;
{extra}wire [22:0] dp = {dprime_expr};
reg [7:0] weight;
always @(*) begin
    if (dp >= 23'd25) begin
        weight = 8'd0;
    end else begin
{table}
    end
end

"""
    return GOLD[:a] + body + GOLD[b:]


M = []  # (name, class, registered_scope, description, edits | full_text)


def edit(name, cls, scope, desc, *pairs):
    M.append((name, cls, scope, desc, list(pairs), None))


def full(name, cls, scope, desc, text):
    M.append((name, cls, scope, desc, None, text))


# --- LUT entries ---------------------------------------------------------------------------
edit("m01_lut8_34", "functional-bug", "both", "entry D'=8 35 -> 34 (near-tie 34.5105 truncated/rounded down)",
     ("5'd8:  weight = 8'd35;", "5'd8:  weight = 8'd34;"))
edit("m02_lut25_1", "functional-bug", "both", "D'=25 gives 1 instead of 0 (near-tie 0.4923 rounded up)",
     ("            default: weight = 8'd0;   // D' = 25 .. 31",
      "            5'd25: weight = 8'd1;\n            default: weight = 8'd0;   // D' = 25 .. 31"))
edit("m03_lut1_198", "functional-bug", "both", "entry D'=1 off by one: 199 -> 198",
     ("5'd1:  weight = 8'd199;", "5'd1:  weight = 8'd198;"))
edit("m04_lut20_1", "functional-bug", "both", "entry D'=20 off by one: 2 -> 1 (equal-neighbour region)",
     ("5'd20: weight = 8'd2;", "5'd20: weight = 8'd1;"))
edit("m05_lut24_0", "functional-bug", "both", "last nonzero entry D'=24: 1 -> 0",
     ("5'd24: weight = 8'd1;", "5'd24: weight = 8'd0;"))
edit("m06_lut0_254", "functional-bug", "both", "entry D'=0: 255 -> 254 (W[0] bit stuck 0 at the peak)",
     ("5'd0:  weight = 8'd255;", "5'd0:  weight = 8'd254;"))
# --- rounding -----------------------------------------------------------------------------
edit("m07_truncate", "functional-bug", "both", "no rounding: D' = D >> s (rounding bit ignored)",
     ("wire [5:0] index = {1'b0, aligned[5:1]} + {5'b0, aligned[0]};",
      "wire [5:0] index = {1'b0, aligned[5:1]};"),
     ("reg [7:0] weight;\nalways", "wire _unused_mut = &{aligned[0], 1'b0};\nreg [7:0] weight;\nalways"))
full("m08_tie_down", "functional-bug", "both",
     "ties round down: D' = (D + 2^(s-1) - 1) >> s (round-half-down, full-width reformulation)",
     reform("({1'b0, diff} + (shift == 4'd0 ? 23'd0 : ((23'd1 << shift) >> 1) - 23'd1)) >> shift"))
full("m09_tie_even", "functional-bug", "both",
     "ties round to even (banker's rounding of D/2^s; full-width reformulation)",
     reform("tq + ((rb && (sticky || tq[0])) ? 23'd1 : 23'd0)",
            "wire [22:0] tq = {1'b0, diff} >> shift;\n"
            "wire rb = (shift != 4'd0) && diff[{1'b0, shift} - 5'd1];\n"
            "wire [22:0] lowmask = (shift <= 4'd1) ? 23'd0 : ((23'd1 << (shift - 4'd1)) - 23'd1);\n"
            "wire sticky = |({1'b0, diff} & lowmask);\n"))
# --- shift boundaries ---------------------------------------------------------------------
edit("m10_shift8_decode", "functional-bug", "both", "shift = 8 decoded as shift = 0 (stage-8 select boundary off by one)",
     ("wire [12:0] stage8 = shift[3] ? delta_guard[20:8] : delta_guard[12:0];\n"
      "wire [8:0] stage4 = shift[2] ? stage8[12:4] : stage8[8:0];\n"
      "wire [6:0] stage2 = shift[1] ? stage4[8:2] : stage4[6:0];\n"
      "wire [5:0] aligned = shift[0] ? stage2[6:1] : stage2[5:0];",
      "wire s8 = shift[3] && (shift != 4'd8);\n"
      "wire [12:0] stage8 = s8 ? delta_guard[20:8] : delta_guard[12:0];\n"
      "wire [8:0] stage4 = shift[2] ? stage8[12:4] : stage8[8:0];\n"
      "wire [6:0] stage2 = shift[1] ? stage4[8:2] : stage4[6:0];\n"
      "wire [5:0] aligned = shift[0] ? stage2[6:1] : stage2[5:0];"),
     ("(!shift[3] && (|delta_guard[20:13]))", "(!s8 && (|delta_guard[20:13]))"))
edit("m11_shift0_oor", "functional-bug", "both", "shift = 0: D = 32..63 not flagged out of range (last stage check skipped at s=0)",
     ("(!shift[0] && stage2[6]);", "(!shift[0] && stage2[6] && (shift != 4'd0));"))
edit("m12_s15_noround", "functional-bug", "both", "shift = 15 only: rounding bit ignored",
     ("wire [5:0] index = {1'b0, aligned[5:1]} + {5'b0, aligned[0]};",
      "wire [5:0] index = {1'b0, aligned[5:1]} + {5'b0, aligned[0] && (shift != 4'd15)};"))
# --- saturation ---------------------------------------------------------------------------
edit("m13_carry_lost", "functional-bug", "both", "rounding carry to D'=32 not flagged (index[5] dropped): e.g. s=1, D=63 gives 255",
     ("wire out_of_range = (|diff[21:20]) || index[5] ||", "wire out_of_range = (|diff[21:20]) ||"),
     ("reg [7:0] weight;\nalways", "wire _unused_mut = &{index[5], 1'b0};\nreg [7:0] weight;\nalways"))
edit("m14_bit21_ignored", "out-of-context-bug", "both", "D[21] ignored (D >= 2^21 aliases to D - 2^21); unreachable with a consistent tape",
     ("wire out_of_range = (|diff[21:20]) ||", "wire out_of_range = diff[20] ||"),
     ("reg [7:0] weight;\nalways", "wire _unused_mut = &{diff[21], 1'b0};\nreg [7:0] weight;\nalways"))
edit("m15_bit20_ignored", "functional-bug", "both", "D >= 2^20 check removed: D = 2^20 gives 255",
     ("wire out_of_range = (|diff[21:20]) || index[5] ||", "wire out_of_range = index[5] ||"),
     ("reg [7:0] weight;\nalways", "wire _unused_mut = &{diff[21:20], 1'b0};\nreg [7:0] weight;\nalways"))
edit("m16_default_1", "functional-bug", "both", "table default D'=25..31 gives 1 (saturation region nonzero)",
     ("default: weight = 8'd0;   // D' = 25 .. 31", "default: weight = 8'd1;   // D' = 25 .. 31"))
edit("m17_default_x", "functional-bug", "both", "table default D'=25..31 gives X (unspecified; 2-state sims may read 0)",
     ("default: weight = 8'd0;   // D' = 25 .. 31", "default: weight = 8'bx;   // D' = 25 .. 31"))
edit("m18_stage_check", "functional-bug", "both", "stage-4 discarded-bit check dropped: shift without bit 2 and D bits lost from stage8[12:9]",
     ("    (!shift[2] && (|stage8[12:9])) ||\n", ""))
# --- rare single point --------------------------------------------------------------------
edit("m19_rare_point", "functional-bug", "both", "one rare point: D = 1337, shift = 7 (D'=10) gives 22 instead of 21 (1 of 2^26 inputs)",
     ("    if (out_of_range) begin", "    if (D == 22'd1337 && shift == 4'd7) begin\n        weight = 8'd22;\n    end else if (out_of_range) begin"))
edit("m20_rare_highD", "out-of-context-bug", "both", "one rare point above the consistent-tape range: D = 22'h3FFFFF, shift = 15 gives 255",
     ("    if (out_of_range) begin", "    if (D == 22'h3FFFFF && shift == 4'd15) begin\n        weight = 8'd255;\n    end else if (out_of_range) begin"))
# --- REGISTERED = 1 sequencing -------------------------------------------------------------
edit("m21_r1_latency2", "functional-bug", "R1", "REGISTERED=1: two-cycle latency (extra W and done stage)",
     ("    assign done = done_r;\n    assign W = W_r;",
      "    reg done_r2; reg [7:0] W_r2;\n"
      "    always @(posedge clk) begin\n"
      "        if (!rst_n) begin done_r2 <= 1'b0; W_r2 <= 8'd0; end\n"
      "        else begin done_r2 <= done_r; W_r2 <= W_r; end\n"
      "    end\n"
      "    assign done = done_r2;\n    assign W = W_r2;"))
edit("m22_r1_comb_bypass", "functional-bug", "R1", "REGISTERED=1: W shows the new weight combinationally in the start cycle (latency 0)",
     ("    assign W = W_r;", "    assign W = start ? weight : W_r;"))
edit("m23_r1_load_always", "functional-bug", "R1", "REGISTERED=1: W reloads every cycle (no hold while start = 0)",
     ("            if (start) begin\n                W_r <= weight;\n            end",
      "            W_r <= weight;"))
edit("m24_r1_W_noreset", "functional-bug", "R1", "REGISTERED=1: W not cleared by reset (done still is)",
     ("            W_r    <= 8'd0;\n", ""))
edit("m25_r1_start_over_reset", "functional-bug", "R1", "REGISTERED=1: start has priority over reset for W",
     ("        if (!rst_n) begin\n            done_r <= 1'b0;\n            W_r    <= 8'd0;\n        end else begin",
      "        if (!rst_n && !start) begin\n            done_r <= 1'b0;\n            W_r    <= 8'd0;\n        end else if (!rst_n) begin\n            done_r <= 1'b0;\n            W_r    <= weight;\n        end else begin"))
edit("m26_r1_done_stretch", "functional-bug", "R1", "REGISTERED=1: done stays high one extra cycle",
     ("    assign done = done_r;", "    reg done_d;\n    always @(posedge clk) done_d <= rst_n && done_r;\n    assign done = done_r | done_d;"))
edit("m27_r1_async_reset", "structural", "R1", "REGISTERED=1: asynchronous reset (clears W/done when rst_n falls, before the edge)",
     ("    always @(posedge clk) begin\n        if (!rst_n) begin", "    always @(posedge clk or negedge rst_n) begin\n        if (!rst_n) begin"))
edit("m28_r1_negedge", "structural", "R1", "REGISTERED=1: negedge flops",
     ("    always @(posedge clk) begin\n        if (!rst_n) begin", "    always @(negedge clk) begin\n        if (!rst_n) begin"))
edit("m29_r1_initval", "structural", "R1", "REGISTERED=1: initial values on W_r/done_r (no ASIC power-up value)",
     ("    reg done_r;\n    reg [7:0] W_r;", "    reg done_r = 1'b0;\n    reg [7:0] W_r = 8'd0;"))
# --- REGISTERED = 0 / interface -------------------------------------------------------------
edit("m30_r0_rst_gates_W", "out-of-context-bug", "R0", "REGISTERED=0: W forced to 0 while rst_n = 0 (never observed in the chip)",
     ("    assign W = weight;\n    wire _unused = &{clk, rst_n, 1'b0};", "    assign W = rst_n ? weight : 8'd0;\n    wire _unused = &{clk, 1'b0};"))
edit("m31_r0_done_zero", "out-of-context-bug", "R0", "REGISTERED=0: done tied 0 (chip ties start = 0)",
     ("    assign done = start;\n    assign W = weight;\n    wire _unused = &{clk, rst_n, 1'b0};", "    assign done = 1'b0;\n    assign W = weight;\n    wire _unused = &{clk, rst_n, start, 1'b0};"))
edit("m32_r0_registered_W", "functional-bug", "R0", "REGISTERED=0: W registered (one-cycle latency in the chip configuration)",
     ("    assign W = weight;\n    wire _unused = &{clk, rst_n, 1'b0};",
      "    reg [7:0] W_q;\n    always @(posedge clk) W_q <= weight;\n    assign W = W_q;\n    wire _unused = &{rst_n, 1'b0};"))
edit("m33_r0_latch", "structural", "R0", "REGISTERED=0: W through a transparent-high latch on clk",
     ("    assign W = weight;\n    wire _unused = &{clk, rst_n, 1'b0};",
      "    reg [7:0] W_l;\n    always @(*) if (clk) W_l = weight;\n    assign W = W_l;\n    wire _unused = &{rst_n, 1'b0};"))
edit("m34_default_param0", "structural", "both", "interface: default REGISTERED changed 1 -> 0 (test/blocks instantiates the default)",
     ("module exp_lut #(parameter REGISTERED = 1) (", "module exp_lut #(parameter REGISTERED = 0) ("))
# --- REGISTERED = 0 only (D9b: r0 is no longer proven; probes edge-case/spot coverage) --------
edit("m35_r0_rare_point", "functional-bug", "R0", "REGISTERED=0 only: one interior point D = 1337, shift = 7 (D'=10) gives 22 instead of 21; R1 correct",
     ("    assign W = weight;\n    wire _unused", "    assign W = (D == 22'd1337 && shift == 4'd7) ? 8'd22 : weight;\n    wire _unused"))
edit("m36_r0_entry_one_shift", "functional-bug", "R0", "REGISTERED=0 only: entry D'=6 wrong (57 -> 56) at shift 11 only (2,048 D values)",
     ("    assign W = weight;\n    wire _unused", "    assign W = (shift == 4'd11 && weight == 8'd57) ? 8'd56 : weight;\n    wire _unused"))
edit("m37_r0_mid_interval", "functional-bug", "R0", "REGISTERED=0 only: W off by one for D in [3000, 3010] at shift 10 (inside the D'=3 interval, away from every boundary)",
     ("    assign W = weight;\n    wire _unused", "    assign W = (shift == 4'd10 && D >= 22'd3000 && D <= 22'd3010) ? weight - 8'd1 : weight;\n    wire _unused"))
edit("m38_r0_rare_x", "functional-bug", "R0", "REGISTERED=0 only: W = X at one interior point (D = 1337, shift = 7); probes the X check off the edge set",
     ("    assign W = weight;\n    wire _unused", "    assign W = (D == 22'd1337 && shift == 4'd7) ? 8'bx : weight;\n    wire _unused"))
edit("m39_rare_x_both", "functional-bug", "both", "weight = X at one interior point (D = 1337, shift = 7), both configurations",
     ("    if (out_of_range) begin", "    if (D == 22'd1337 && shift == 4'd7) begin\n        weight = 8'bx;\n    end else if (out_of_range) begin"))
# --- equivalent rewrites (expected survivors) ------------------------------------------------
edit("e01_swap_19_20", "equivalent", "both", "entries D'=19 and D'=20 swapped (both 2)",
     ("5'd19: weight = 8'd2;\n            5'd20: weight = 8'd2;", "5'd20: weight = 8'd2;\n            5'd19: weight = 8'd2;"))
full("e02_fullwidth_round", "equivalent", "both", "full-width reformulation: D' = (D + 2^(s-1)) >> s at 23 bits, W = D' < 25 ? table : 0",
     reform("({1'b0, diff} + ((23'd1 << shift) >> 1)) >> shift"))
edit("e03_ge_2_20", "equivalent", "both", "|D[21:20] written as D >= 2^20",
     ("wire out_of_range = (|diff[21:20]) ||", "wire out_of_range = (diff >= 22'h100000) ||"))
edit("e04_r1_mux_hold", "equivalent", "both", "REGISTERED=1: if (start) W_r <= weight written as W_r <= start ? weight : W_r",
     ("            if (start) begin\n                W_r <= weight;\n            end", "            W_r <= start ? weight : W_r;"))
edit("e05_explicit_zeros", "equivalent", "both", "explicit zero entries D'=25..31 added before the default",
     ("            default: weight = 8'd0;   // D' = 25 .. 31",
      "            5'd25, 5'd26, 5'd27, 5'd28, 5'd29, 5'd30, 5'd31: weight = 8'd0;\n            default: weight = 8'd0;"))


def main():
    os.makedirs(os.path.join(HERE, "mutants"), exist_ok=True)
    man = {}
    for name, cls, scope, desc, pairs, text in M:
        if text is None:
            text = GOLD
            for old, new in pairs:
                assert text.count(old) == 1, f"{name}: edit matches {text.count(old)} times: {old[:60]!r}"
                text = text.replace(old, new)
        assert text != GOLD, name
        open(os.path.join(HERE, "mutants", name + ".v"), "w").write(f"// mutant {name}: {desc}\n" + text)
        man[name] = {"class": cls, "scope": scope, "description": desc}
    json.dump(man, open(os.path.join(HERE, "mutants", "MANIFEST.json"), "w"), indent=1)
    print(len(man), "mutants")


if __name__ == "__main__":
    main()
