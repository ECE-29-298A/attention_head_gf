// ripple_add N=22 behavioural view of the hardened block (same ports as the gate view and LEF).
// s = (a + b + cin) mod 2^22; the carry out is not a port (as in src/ripple_add.v).
// Pure combinational: no timing; use the Liberty view (views/lib) for delays.
module ripple_add (
    input  wire [21:0] a,
    input  wire [21:0] b,
    input  wire        cin,
    output wire [21:0] s
);
    assign s = a + b + {{21{1'b0}}, cin};
endmodule
