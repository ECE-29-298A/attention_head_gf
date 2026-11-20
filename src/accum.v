/*
Jinyuan Zhao
L and O0 to O3
*/

/*
Here we add everything up for the average.
Keep 5 running totals:
- L:    sum of all weights
- O:    sum of W x value, one per component (4 of them)

After this the divider will do O/L to get weighted average.
*/

/*
==== INFO ====
NO MULTIPLIER: ONE SHARED RIPPLE ADDER, SHIFT-ADD ONE BIT OF v PER CYCLE.
W x v = W*v[0] + 2W*v[1] + ... + 64W*v[6] - 128W*v[7]  (v is two's complement).

AREA: the four O registers are a ring that rotates EVERY clock (no hold muxes):
O3 <= O0 + term, O0 <= O1, O1 <= O2, O2 <= O3. When en is low term = 0, so the
ring just turns. The caller keeps a free-running 2-bit phase that starts at 0 on
reset and steps every clock; O0 always holds component `phase`, and `sel` is that phase.

No reset/clear: on the first token (first = 1) the adder sees 0 instead of the
old sum, so the bit-0 cycle of each component loads rather than adds.

Caller holds en for 32 cycles per token: bit_sel = 0..7 (outer), sel = 0..3 (inner,
the free-running phase). L is updated on sel = 0, bit_sel = 0.
*/

module accum (
    input  wire              clk,
    input  wire              first,   // first token of pass 2: load instead of add
    input  wire              en,      // a weight and its 4 values are ready
    input  wire        [7:0] W,       // 0 to 255, UNSIGNED
    input  wire        [1:0] sel,     // ring phase: component now in O0
    input  wire        [2:0] bit_sel, // which bit of v this cycle adds
    input  wire signed [7:0] v,       // value component sel
    output reg        [11:0] L,
    output reg signed [19:0] O0, O1, O2, O3 // |O| <= 16 * 255 * 128 = 522240
);

wire [19:0] term = en && v[bit_sel] ? ({12'b0, W} << bit_sel) : 20'd0;
wire        neg  = bit_sel == 3'd7;  // sign bit of v weighs -128: ~term + 1 (adds 0 when term is 0)
wire        load = en && first && bit_sel == 3'd0;
wire [19:0] O_next;
wire [11:0] L_next;
ripple_add #(.N(20)) o_adder (.a(load ? 20'd0 : O0), .b(neg ? ~term : term), .cin(neg), .s(O_next));
ripple_add #(.N(12)) l_adder (.a(first ? 12'd0 : L), .b({4'b0, W}), .cin(1'b0), .s(L_next));

always @(posedge clk) begin
    O0 <= O1;
    O1 <= O2;
    O2 <= O3;
    O3 <= $signed(O_next);
    if (en && sel == 2'd0 && bit_sel == 3'd0) L <= L_next;
end

endmodule
