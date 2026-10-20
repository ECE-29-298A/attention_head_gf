/*
Jinyuan Zhao
dot4 function
*/

module score_mac (
    input wire clk,
    input wire rst_n,
    input wire clear, // Clear the signal
    input wire en,

    input wire signed [3:0] qi,
    input wire signed [3:0] ki,
    output reg signed [9:0] S
);

always@(posedge clk) begin

    // If both clear and enable are on at the same time, clear wins.

    if(!rst_n) begin
        S <= 0;
    end else if (clear) begin
        S <= 0;
    end else if (en) begin
        S <= S + qi * ki;
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
