/*
Jinyuan Zhao
L and O0 to O3
*/

/*
Here we add everything up for the average.
Keep 5 running totals:
- L:    sum of all weights
- O0:   sum of W x value 0
- O1:   sum of W x value 1
- O2:   sum of W x value 2
- O3:   sum of W x value 3

After this the divider will do O/L to get weighted average. 
*/

/*
==== INFO ====
NO MULTIPLIER: ONE SHARED RIPPLE ADDER, SHIFT-ADD ONE BIT OF v PER CYCLE.
W x v = W*v[0] + 2W*v[1] + 4W*v[2] - 8W*v[3]  (v is two's complement).
Caller holds en for 16 cycles: for sel = 0..3, bit_sel = 0..3. L is updated on sel = 0, bit_sel = 0.
*/

module accum (
    input  wire              clk,
    input  wire              rst_n,
    input  wire              clear,   // pass 2 starting
    input  wire              en,      // a weight and its 4 values are ready
    input  wire        [7:0] W,       // 0 to 255, UNSIGNED
    input  wire        [1:0] sel,     // which O this cycle updates
    input  wire        [1:0] bit_sel, // which bit of v this cycle adds
    input  wire signed [3:0] v,       // value component sel
    output reg        [11:0] L,
    output reg signed [15:0] O0, O1, O2, O3
);

/*
L = L + W                         (sel == 0, bit_sel == 0)
Osel = Osel +/- v[bit_sel] * (W << bit_sel)   (minus for bit 3)
*/

reg signed [15:0] O_sel;
always @(*) begin
    case (sel)
        2'd0: O_sel = O0;
        2'd1: O_sel = O1;
        2'd2: O_sel = O2;
        default: O_sel = O3;
    endcase
end
wire [15:0] term = v[bit_sel] ? ({8'b0, W} << bit_sel) : 16'd0;
wire        neg  = (bit_sel == 2'd3);  // sign bit of v has weight -8: subtract via ~term + 1
wire [15:0] O_next;
wire [11:0] L_next;
ripple_add #(.N(16)) o_adder (.a(O_sel), .b(neg ? ~term : term), .cin(neg), .s(O_next));
ripple_add #(.N(12)) l_adder (.a(L), .b({4'b0, W}), .cin(1'b0), .s(L_next));

always@(posedge clk) begin

    if (!rst_n) begin
        L <= 0;
        O0 <= 0;
        O1 <= 0;
        O2 <= 0;
        O3 <= 0;
    end else if (clear) begin
        L <= 0;
        O0 <= 0;
        O1 <= 0;
        O2 <= 0;
        O3 <= 0;
    end else if (en) begin
        if (sel == 2'd0 && bit_sel == 2'd0) L <= L_next;
        case (sel)
            2'd0: O0 <= $signed(O_next);
            2'd1: O1 <= $signed(O_next);
            2'd2: O2 <= $signed(O_next);
            default: O3 <= $signed(O_next);
        endcase
    end

end

endmodule
