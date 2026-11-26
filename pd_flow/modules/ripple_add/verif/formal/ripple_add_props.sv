// Formal property harness for ripple_add #(N). All inputs are free (no assumptions).
// Reference is the behavioural (N+1)-bit sum, not the RTL's full-adder chain.
// GATE_LEVEL: the DUT is a fixed-width netlist (no parameter); N must equal its width
// (run_all.sh --gate N runs only the tasks for that N and checks the port widths).
module ripple_add_props #(parameter N = 22) (
    input wire [N-1:0] a,
    input wire [N-1:0] b,
    input wire [N-1:0] x,
    input wire         cin
);
    localparam [N-1:0] ONES = {N{1'b1}};

    wire [N-1:0] s, s_sub;
`ifdef GATE_LEVEL
    ripple_add          dut     (.a(a), .b(b),  .cin(cin),  .s(s));
    ripple_add          dut_sub (.a(a), .b(~x), .cin(1'b1), .s(s_sub));
`else
    ripple_add #(.N(N)) dut     (.a(a), .b(b),  .cin(cin),  .s(s));
    // mac_unit subtract use: b = ~x, cin = 1  ->  s = a - x (mod 2^N)
    ripple_add #(.N(N)) dut_sub (.a(a), .b(~x), .cin(1'b1), .s(s_sub));
`endif

    wire [N:0]   full = {1'b0, a} + {1'b0, b} + {{N{1'b0}}, cin};
    wire [N-1:0] diff = a - x;

    always @* begin
`ifndef SANITY_FAIL
        // R1, R2: sum modulo 2^N, carry out dropped
        a_sum: assert (s == full[N-1:0]);
        // R4: two's-complement subtract via b = ~x, cin = 1
        a_sub: assert (s_sub == diff);
`else
        // Negative control: wrong reference (cin ignored). This MUST fail.
        a_wrong: assert (s == a + b);
`endif
`ifdef COVERS
        c_overflow_wrap:   cover (full[N]);                           // carry out dropped
        c_no_overflow:     cover (!full[N] && s == ONES);             // largest unwrapped sum
        c_full_propagate:  cover (((a ^ b) == ONES) && cin);          // cin ripples through all N bits
        c_propagate_nocin: cover (((a ^ b) == ONES) && !cin);         // all-propagate, no carry
        c_cin_a_ones:      cover (cin && a == ONES && b == 0);        // s wraps to 0
        c_max_inputs:      cover (cin && a == ONES && b == ONES);     // s = ONES, carry out
        c_all_zero:        cover (!cin && a == 0 && b == 0);
        c_cin_only:        cover (cin && a == 0 && b == 0);           // s = 1
        c_msb_generate:    cover (a[N-1] && b[N-1] && s == 0 && !cin);// generate at MSB, wraps
        c_sub_borrow:      cover (x > a);                             // subtract result wraps
        c_sub_zero:        cover (x == a);                            // a - a = 0, carry out
        // covers observing the DUT outputs
        c_s_zero_wrap:     cover (full[N] && s == 0);                 // s wraps to exactly 0
        c_s_ones_wrap:     cover (full[N] && s == ONES);              // ONES + ONES + 1
        c_s_msb_by_carry:  cover (s[N-1] && !a[N-1] && !b[N-1]);      // MSB of s set by carry only
        c_s_chain_n:       cover (cin && ((a ^ b) == ONES) && s == 0);// length-N carry chain seen in s
        c_s_sub_minus1:    cover (s_sub == ONES);                     // subtract result -1
`endif
    end
endmodule
