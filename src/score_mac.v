/*
Jinyuan Zhao
dot64 function

NO MULTIPLIER: shift-add one bit of ki per cycle through a ripple adder.
qi x ki = qi*k[0] + 2qi*k[1] + ... + 64qi*k[6] - 128qi*k[7]  (ki is two's complement).
Caller holds en for 8 cycles per component (bit_sel = 0..7), 64 components per
score, clearing only before the first.
*/

module score_mac (
    input wire clk,
    input wire rst_n,
    input wire clear, // Clear the signal
    input wire en,

    input wire signed [7:0] qi,
    input wire signed [7:0] ki,
    input wire        [2:0] bit_sel, // which bit of ki this cycle adds
    output reg signed [21:0] S       // |S| <= 64 * 128 * 128 = 1048576
);

wire [21:0] term = ki[bit_sel] ? ({{14{qi[7]}}, qi} << bit_sel) : 22'd0;
wire        neg  = (bit_sel == 3'd7);  // sign bit of ki has weight -128: subtract via ~term + 1
wire [21:0] S_next;
ripple_add #(.N(22)) s_adder (.a(S), .b(neg ? ~term : term), .cin(neg), .s(S_next));

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
def dot(q: list[int], k: list[int]) -> int:

    # Initiate sum
    S = 0
    for x, y in zip(q, k): # Iterate through them
        S = check_width(S + x * y, 22, signed=True, name="S")
    return S

*/
