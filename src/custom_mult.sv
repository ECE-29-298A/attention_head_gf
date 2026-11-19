//Truncates output to OUT_WIDTH. does NOT signal overflow. UNSIGNED only. 

module multiplier #(
    parameter integer WIDTH = 4,
    parameter integer OUT_WIDTH = 8
) (
    input wire [WIDTH-1:0] a,
    input wire [WIDTH-1:0] b,
    output wire [WIDTH*2-1:0] mult_out
);
    
endmodule