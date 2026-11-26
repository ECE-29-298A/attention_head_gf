// ripple_add N=12 behavioural view of the hardened block (same ports as the gate view and LEF).
// s = (a + b + cin) mod 2^12; the carry out is not a port (as in src/ripple_add.v).
// Pure combinational: no timing; use the Liberty view (views/lib) for delays.
module ripple_add (
    input  wire [11:0] a,
    input  wire [11:0] b,
    input  wire        cin,
    output wire [11:0] s
);
    assign s = a + b + {{11{1'b0}}, cin};
endmodule
