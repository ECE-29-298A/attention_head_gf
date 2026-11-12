/*
Jinyuan Zhao
dot4 function

NO MULTIPLIER: shift-add one bit of ki per cycle through a ripple adder.
qi x ki = qi*k[0] + 2qi*k[1] + 4qi*k[2] - 8qi*k[3]  (ki is two's complement).
Caller holds en for 16 cycles per score: for each component, bit_sel = 0..3.
*/

module score_mac (
    input wire clk,
    input wire rst_n,
    input wire clear, // Clear the signal
    input wire en,

    input wire signed [3:0] qi,
    input wire signed [3:0] ki,
    input wire        [1:0] bit_sel, // which bit of ki this cycle adds
    output reg signed [9:0] S
);

wire [9:0] term = ki[bit_sel] ? ({{6{qi[3]}}, qi} << bit_sel) : 10'd0;
wire       neg  = (bit_sel == 2'd3);  // sign bit of ki has weight -8: subtract via ~term + 1
wire [9:0] S_next;
ripple_add #(.N(10)) s_adder (.a(S), .b(neg ? ~term : term), .cin(neg), .s(S_next));

always@(posedge clk) begin

    // If both clear and enable are on at the same time, clear wins.

    if(!rst_n) begin
        S <= 0;
    end else if (clear) begin
        S <= 0;
    end else if (en) begin
        S <= $signed(S_next);
    end

    // S keeps its value, do nothing

end

endmodule


/*
def dot4(q: list[int], k: list[int]) -> int:

    # Initiate sum
    S = 0
    for x, y in zip(q, k): # Iterate through them
        S = check_width(S + x * y, 10, signed=True, name="S")
    return S

*/
