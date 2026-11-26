`default_nettype none

// Two-pass INT8 attention core fed by a byte tape: the host lays the flash out in
// the order the chip consumes it, so the chip issues one 0x6B (Fast Read Quad
// Output) at address 0 and then only clocks. No address is ever generated.
//
// Tape (python/src/attention_model.py: tape()), all bytes signed INT8:
//   score row t  = Q[0], K[t][0], Q[1], K[t][1], ... Q[63], K[t][63]   (128 bytes)
//   pass 1       = score rows 0..N-1                    (finds the maximum M)
//   pass 2 chunk = for each t: score row t, then that chunk's OUTPUTS values
//                  V[t][OUTPUTS*c + i] as OUTPUTS bytes by bit plane:
//                  c0 b7, c1 b7, ... c(OUTPUTS-1) b7, c0 b6, ... c(OUTPUTS-1) b0
//   whole tape   = pass 1, then one pass-2 chunk per run
// A fresh run (cont = 0) restarts the flash read and consumes pass 1 plus one
// pass-2 chunk. A continue run (cont = 1) keeps the read open and the maximum,
// and consumes the next pass-2 chunk only. The flash stays selected between
// runs; reset releases it. cont = 1 before any fresh run reads garbage.
//
// Command, address and 8 dummy clocks go out on IO0 at SCK = clk / 4. Data comes
// in on IO3..IO0 (high nibble first): each SCK rise captures a nibble, which
// shifts into the shift-add MAC one bit per clock, MSB first, with the next rise
// on its last bit. K and V are never stored; Q is held one byte at a time. The
// last nibble of a run is not followed by a rise: a continue run's start edge
// captures the next one, which the flash has held on IO3..IO0 since.
// Pass 2 preloads the score with M and subtracts, so the score register holds
// D = M - S for the exponent table while V accumulates.
// last, score_shift and cont must be held from start until idle.
module attention_controller #(parameter int OUTPUTS = 8) ( // 2, 4 or 8
    input  wire       clk,
    input  wire       rst_n,       // synchronous; aborts the run and releases the flash
    input  wire       start,       // accepted when idle
    input  wire [3:0] last,        // N - 1: the run covers tokens 0..last
    input  wire [3:0] score_shift, // exp_lut rounds M - S and shifts it right by this
    input  wire       cont,
    output wire       idle,
    output wire       spi_cs_n,
    output logic      spi_sck,     // mode 0
    output wire       spi_mosi,    // IO0 out, driven only during command and address
    output wire       spi_mosi_oe,
    input  wire [3:0] spi_io,      // IO3..IO0
    // Components 0..OUTPUTS-1 of the chunk, each a 12-bit signed result (INT8 plus 4
    // fractional bits) shifted out MSB first on out_bit. While out_valid,
    // out_shift moves the next bit up (zeros after bit 0) and out_ready ends the
    // component. Both are ignored in every other state.
    output wire       out_valid,
    input  wire       out_ready,
    input  wire       out_shift,
    output wire       out_bit
);
    localparam int P = $clog2(OUTPUTS); // ring phase bits
    localparam [2:0] IDLE = 3'd0, RESTART = 3'd1, CMD = 3'd2, SCORE = 3'd3,
                     VALUE = 3'd4, DIV_START = 3'd5, DIV_WAIT = 3'd6, OUTPUT = 3'd7;
    logic [2:0] state;
    logic flash_open;   // read transaction in progress (CS low)
    // IO3..IO0 sampled at the SCK rising edge, then shifted up one bit per clock.
    // nibble[0] samples IO0 every clock; only the value from the rise is used.
    logic [3:0] nibble;
    // Counts every clock. RESTART is 0, then CMD {bit 0..40, phase[1:0]} from 1:
    // SCK high in phase 2, IO0 changes in phase 0. Data: the tape bit is in
    // nibble[3]; SCORE {dim[5:0], is_k, bit[2:0]}, VALUE {bit[2:0], component}.
    // Ring phase: the accumulator ring turns every clock, and pos[P-1:0] is the
    // component at its head (O0). From the first V bit of a run to its last
    // division pos only counts up or wraps at a multiple of OUTPUTS (a 1024-clock
    // score row, a V block of 8 * OUTPUTS), so each V bit meets its component and
    // the tape never stalls. The clears at start and at the end of CMD come before
    // the run's first V bit, which loads the ring afresh, so they need no alignment.
    logic [9:0] pos;
    logic signed [7:0] q; // current Q byte
    logic [3:0] token;
    logic second_pass, score_done;
    logic [P-1:0] output_index;

    wire cmd = state == CMD;
    wire v_end = &pos[P+2:0]; // last bit of a V block
    wire run_end = state == VALUE && v_end && token == last;
    // CMD: SCK rises from phase 1. Data: the rise comes with the nibble's last bit,
    // except at the end of a run; a continue run starts with one instead.
    wire rise = (cmd || ((state == SCORE || state == VALUE) && !run_end)) && pos[0] && (pos[1] ^ cmd)
                || (idle && start && cont);

    wire signed [21:0] score, maximum;
    wire signed [19:0] o0;
    wire [11:0] weight_sum;
    wire [7:0] weight;
    wire exp_done, div_busy, div_done;
    wire signed [11:0] result;
    // The MAC takes one K or V bit at position bit_sel; replicate the serial bit.
    wire signed [7:0] serial = {8{nibble[3]}};

    assign idle = state == IDLE;
    assign spi_cs_n = !flash_open;
    // 0x6B = 0110_1011, then 24 zero address bits; released for the dummy clocks.
    assign spi_mosi = pos[6:5] == 2'd0 && pos[4:2] != 3'd0 && pos[4:2] != 3'd3 && pos[4:2] != 3'd5;
    assign spi_mosi_oe = cmd && !pos[7];
    assign out_valid = state == OUTPUT;
    assign out_bit = result[11];

    mac_unit #(.OUTPUTS(OUTPUTS)) mac (
        .clk(clk), .accum_mode(state != SCORE),
        .load(state == SCORE && pos[9:3] == 7'd0), .subtract(second_pass), .M(maximum),
        .score_en(state == SCORE && pos[3]), .qi(q), .ki(serial),
        .first(token == 4'd0), .accum_en(state == VALUE), .W(weight), .sel(pos[P-1:0]),
        .v(serial), .bit_sel(state == VALUE ? ~pos[P+2:P] : ~pos[2:0]),
        .S(score), .L(weight_sum), .O0(o0)
    );
    max_reg max_unit (
        .clk(clk), .first(token == 4'd0), .en(score_done && !second_pass), .S_in(score), .M(maximum)
    );
    exp_lut #(.REGISTERED(0)) exponent_unit (
        .clk(clk), .rst_n(rst_n), .start(1'b0), .D(score), .shift(score_shift),
        .done(exp_done), .W(weight)
    );
    divider #(.LATCH_DENOMINATOR(0), .CHECK_INVALID(0)) divider_unit (
        .clk(clk), .rst_n(rst_n), .start(state == DIV_START && pos[P-1:0] == output_index),
        .sum_in(o0), .denominator(weight_sum), .shift(out_shift && out_valid),
        .busy(div_busy), .done(div_done), .result(result)
    );
    wire _unused = &{div_busy, exp_done, result[10:0], 1'b0};

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state <= IDLE;
            flash_open <= 1'b0;
            spi_sck <= 1'b0;
            score_done <= 1'b0;
        end else begin
            score_done <= 1'b0;
            spi_sck <= rise; // high for one clock
            nibble <= rise ? spi_io : {nibble[2:0], spi_io[0]};
            // Pass 1: max_reg takes the finished score in this cycle.
            if (score_done && !second_pass) begin
                token <= token == last ? 4'd0 : token + 4'd1;
                second_pass <= token == last;
            end
            pos <= pos + 10'd1;
            case (state)
                IDLE: if (start) begin
                    token <= 4'd0;
                    pos <= 10'd0;
                    second_pass <= cont;
                    if (cont) state <= SCORE;
                    else begin flash_open <= 1'b0; state <= RESTART; end
                end
                RESTART: begin flash_open <= 1'b1; state <= CMD; end // CS high for this cycle
                // pos 161: the 41st rise, after 8 + 24 + 8 bits, takes the first nibble.
                CMD: if (pos[7] && pos[5] && pos[0]) begin pos <= 10'd0; state <= SCORE; end
                SCORE: begin
                    if (!pos[3]) q <= {q[6:0], nibble[3]};
                    if (&pos) begin // last K bit of the row; pos wraps to 0
                        score_done <= 1'b1;
                        if (second_pass) state <= VALUE;
                    end
                end
                VALUE: if (v_end) begin
                    pos <= 10'd0;
                    if (token == last) begin output_index <= '0; state <= DIV_START; end
                    else begin token <= token + 4'd1; state <= SCORE; end
                end
                DIV_START: if (pos[P-1:0] == output_index) state <= DIV_WAIT;
                DIV_WAIT: if (div_done) state <= OUTPUT;
                OUTPUT: if (out_ready) begin
                    output_index <= output_index + 1'b1;
                    state <= &output_index ? IDLE : DIV_START;
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule

`default_nettype wire
