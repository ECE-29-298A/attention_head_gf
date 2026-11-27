// Independent cycle reference of the controller's port timing (SPEC.md sections 2 and 3),
// written from the SPEC as segments with their own counters, not from the RTL's pos encoding.
// Outputs: idle, CS#, SCK, IO0 enable and value, out_valid (and its state, for the golden's
// relational invariants). The data path (out_bit) is not
// modelled here: it is pinned by equiv_P (eqy_rtl / seq_eq) and the end-to-end simulation.
`default_nettype none
module ctrl_ref #(parameter P = 8) (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       start,
    input  wire [3:0] last,
    input  wire       cont,
    input  wire       out_ready,
    output wire       r_idle,
    output wire       r_cs_n,
    output wire       r_sck,
    output wire       r_oe,
    output wire       r_mosi,
    output wire       r_valid,
    // reference state, read only by the golden-internal relational invariants (SPEC 5.5)
    output wire [2:0] r_seg,
    output wire [10:0] r_c,
    output wire [3:0] r_tok,
    output wire       r_pass2,
    output wire       r_rowend,
    output wire [2:0] r_comp,
    output wire [2:0] r_ring
);
    localparam W = (P == 8) ? 3 : (P == 4) ? 2 : 1;
    localparam [2:0] S_IDLE = 0, S_CSHI = 1, S_CMD = 2, S_ROW = 3, S_VBLK = 4,
                     S_DREQ = 5, S_DWAIT = 6, S_OUT = 7;
    localparam [10:0] VLEN = 8 * P;        // V block: P bytes, one bit per clock
    reg [2:0] seg;
    reg [10:0] c;          // clocks spent in the current segment (0 = first clock)
    reg [3:0] tok;         // token of the current row / V block
    reg pass2;             // rows of pass 2 (each followed by a V block)
    reg row_end;           // previous clock was the last clock of a pass-1 row
    reg cs_low;            // flash selected
    reg [W-1:0] comp;      // component of the current division / result
    reg [W-1:0] ring;      // ring phase: clocks since the first data clock, mod P

    assign r_seg = seg; assign r_c = c; assign r_tok = tok; assign r_pass2 = pass2;
    assign r_rowend = row_end; assign r_comp = comp; assign r_ring = ring;  // zero-extended
    wire [4:0] cbit = (c[6:0] + 7'd1) >> 2;   // command/address bit sent in this clock
    assign r_idle  = seg == S_IDLE;
    assign r_cs_n  = !cs_low;
    assign r_valid = seg == S_OUT;
    // SCK high for one clock: command clocks 1, 5, ...; data clocks 0, 4, ... (clk / 4)
    assign r_sck   = (seg == S_CMD && c[1:0] == 2'd1) || ((seg == S_ROW || seg == S_VBLK) && c[1:0] == 2'd0);
    // IO0 driven for the 8 command and 24 address bits (32 SCK periods, 127 clocks after CS#)
    assign r_oe    = seg == S_CMD && c < 11'd127;
`ifdef REF_WRONG_CMD
    localparam [7:0] CMD = 8'hEB;   // negative control only
`else
    localparam [7:0] CMD = 8'h6B;   // Fast Read Quad Output
`endif
    wire [7:0] cmd_sh = CMD >> (3'd7 - cbit[2:0]);
    assign r_mosi  = cbit < 5'd8 && cmd_sh[0];

    always @(posedge clk) begin
        if (!rst_n) begin
            seg <= S_IDLE; cs_low <= 1'b0; row_end <= 1'b0;
        end else begin
            c <= c + 11'd1;
            ring <= ring + 1'b1;
            row_end <= 1'b0;
            if (row_end) begin   // the pass-1 row just finished: next token, or pass 2
                tok <= tok == last ? 4'd0 : tok + 4'd1;
                pass2 <= tok == last;
            end
            case (seg)
            S_IDLE: if (start) begin
                    c <= 11'd0; tok <= 4'd0; ring <= '0; pass2 <= cont;
                    if (cont) seg <= S_ROW;                       // continue: data at once
                    else begin seg <= S_CSHI; cs_low <= 1'b0; end // fresh: CS# high one clock
                end
            S_CSHI: begin seg <= S_CMD; c <= 11'd0; cs_low <= 1'b1; end
            S_CMD: if (c == 11'd160) begin seg <= S_ROW; c <= 11'd0; ring <= '0; end
            S_ROW: if (c == 11'd1023) begin
                    c <= 11'd0;
                    if (pass2) seg <= S_VBLK; else row_end <= 1'b1;
                end
            S_VBLK: if (c == VLEN - 11'd1) begin
                    c <= 11'd0;
                    if (tok == last) begin seg <= S_DREQ; comp <= '0; end
                    else begin seg <= S_ROW; tok <= tok + 4'd1; end
                end
            S_DREQ: if (ring == comp) begin seg <= S_DWAIT; c <= 11'd0; end
            S_DWAIT: if (c == 11'd24) seg <= S_OUT;               // 25 clocks per division
            S_OUT: if (out_ready) begin
                    comp <= comp + 1'b1;
                    seg <= &comp ? S_IDLE : S_DREQ;      // P is a power of 2
                end
            default: seg <= S_IDLE;
            endcase
        end
    end
endmodule
`default_nettype wire
