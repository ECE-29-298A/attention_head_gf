// Independent formal reference for the divider result (SPEC.md section 4), written from the
// definition result = round(16*S/L), ties away from zero, not from the RTL.
// Sequential long division with the DIVISOR shifted: a 24-bit partial remainder rs starts at
// Z = 16*|S| (24 bits, so |S| = 2^19 is representable) and, for quotient bit j = 23..0, loses
// L << j (compared on 36 bits) when it can. Bit 23 is processed at the load edge, one bit per
// step edge after that (the harness steps it in lockstep with its protocol counter, so it
// finishes bit 0 on the 23rd edge after the load). Then, combinationally:
//   up    = 2R >= L                         (round half up on the magnitude)
//   m     = q + up
//   valid = L != 0 && S != -2^19 && (S >= 0 ? m <= 2047 : m <= 2048)
//   value = valid ? sign(S) * m : 0          (12-bit two's complement)
// The RTL instead shifts the dividend through a 12-bit remainder, has no bit 23, reuses its
// subtractor for the round step and applies the sign with an XOR and one increment.
// Checked against the Python golden model by the refcheck item (sim/tb_ref.sv).
`default_nettype none
module ref_divider_seq (
    input  wire               clk,
    input  wire               load,      // latch S_in, L_in and process bit 23
    input  wire               step,      // process bit `bitpos`
    input  wire        [4:0]  bitpos,
    input  wire signed [19:0] S_in,
    input  wire        [11:0] L_in,
    output reg  signed [19:0] S,
    output reg         [11:0] L,
    output reg         [23:0] rs,        // Z - (quotient so far) * L, aligned to bit 0
    output reg         [23:0] qs,        // quotient bits so far (unprocessed bits 0)
    output wire        [23:0] Z,         // 16 * |S| of the latched S
    output wire               valid,
    output wire        [11:0] value,
    output wire               tie        // 2R == L (an exact .5)
);
    wire [19:0] A_in = S_in[19] ? (~S_in + 20'd1) : S_in;
    wire [23:0] Z_in = {A_in, 4'b0000};
    wire [35:0] d23  = {24'd0, L_in} << 23;
    wire        q23  = {12'd0, Z_in} >= d23;
    wire [35:0] dj   = {24'd0, L} << bitpos;
    wire        qj   = {12'd0, rs} >= dj;
    always @(posedge clk) begin
        if (load) begin
            S  <= S_in;
            L  <= L_in;
            rs <= q23 ? Z_in - d23[23:0] : Z_in;
            qs <= {q23, 23'd0};
        end else if (step && qj) begin
            rs <= rs - dj[23:0];
            qs <= qs | (24'd1 << bitpos);
        end
    end
    wire [19:0] A = S[19] ? (~S + 20'd1) : S;
    assign Z = {A, 4'b0000};
    wire up = {rs, 1'b0} >= {13'd0, L};
    assign tie = {rs, 1'b0} == {13'd0, L};
    wire [24:0] m = {1'b0, qs} + {24'd0, up};
    wire in_range = S[19] ? (m <= 25'd2048) : (m <= 25'd2047);
    assign valid = L != 12'd0 && S != -20'sd524288 && in_range;
    assign value = !valid ? 12'd0 : S[19] ? (~m[11:0] + 12'd1) : m[11:0];
endmodule
`default_nettype wire
