`default_nettype none

// Two-pass INT8 attention core fed by a byte tape: the host lays the flash out in
// the order the chip consumes it, so the chip issues one 0x03 read at address 0
// and then only clocks. No address is ever generated.
//
// Tape (python/src/attention_model.py: tape()), all bytes signed INT8:
//   score row t  = Q[0], K[t][0], Q[1], K[t][1], ... Q[63], K[t][63]   (128 bytes)
//   pass 1       = score rows 0..N-1                    (finds the maximum M)
//   pass 2 chunk = for each t: score row t, then that chunk's V[t] bytes (2)
//   whole tape   = pass 1, then one pass-2 chunk per run
// A fresh run (cont = 0) restarts the flash read and consumes pass 1 plus one
// pass-2 chunk. A continue run (cont = 1) keeps the read open and the maximum,
// and consumes the next pass-2 chunk only. The flash stays selected between
// runs; reset releases it. cont = 1 before any fresh run reads garbage.
//
// Bits arrive MSB first, one per two clocks (SCK = clk / 2), and feed the
// shift-add MAC directly: K and V are never stored, Q is held one byte at a time.
// Pass 2 preloads the score with M and subtracts, so the score register holds
// D = M - S for the exponent table while V accumulates.
// token_count, score_shift and cont must be held from start until idle.
module attention_controller (
    input  wire       clk,
    input  wire       rst_n,       // synchronous; aborts the run and releases the flash
    input  wire       start,       // accepted when idle
    input  wire [4:0] token_count, // 1..16
    input  wire [3:0] score_shift, // exp_lut rounds M - S and shifts it right by this
    input  wire       cont,
    output wire       idle,
    output wire       spi_cs_n,
    output logic      spi_sck,     // mode 0
    output wire       spi_mosi,
    input  wire       spi_miso,
    // Components 0, 1 of the chunk, each a 12-bit signed result (INT8 plus 4
    // fractional bits) sent low byte first, then the sign-extended high byte.
    // A byte transfers on a rising edge when out_valid && out_ready.
    output wire       out_valid,
    input  wire       out_ready,
    output wire [7:0] out_data
);
    localparam [2:0] IDLE = 3'd0, RESTART = 3'd1, CMD = 3'd2, SCORE = 3'd3,
                     VALUE = 3'd4, DIV_START = 3'd5, DIV_WAIT = 3'd6, OUTPUT = 3'd7;
    logic [2:0] state;
    logic flash_open;   // read transaction in progress (CS low)
    logic rx_bit;       // bit sampled on the last SCK rising edge
    // Index of the bit in rx_bit. CMD: 0..31. SCORE: {dim[5:0], is_k, bit[2:0]}.
    // VALUE: {v byte, bit[2:0]}.
    logic [9:0] pos;
    logic signed [7:0] q; // current Q byte
    logic [3:0] token;
    logic second_pass, score_done;
    // Free-running phase: the accumulator ring turns every clock, so O0 holds
    // component `component`.
    logic component, output_index, high_byte;

    wire [3:0] last = 4'(token_count - 5'd1);
    wire consume = spi_sck; // SCK-high cycle: rx_bit holds bit `pos`
    // V bits must meet their component at the head of the ring: SCK rises only
    // into a cycle whose phase is the V byte index (one stall between the bytes).
    wire rise = (state == CMD || state == SCORE || (state == VALUE && component != pos[3])) && !spi_sck;

    wire signed [21:0] score, maximum;
    wire signed [19:0] o0, o1;
    wire [11:0] weight_sum;
    wire [7:0] weight;
    wire exp_done, div_busy, div_done;
    wire signed [11:0] result;
    // The MAC takes one K or V bit at position bit_sel; replicate the serial bit.
    wire signed [7:0] serial = {8{rx_bit}};

    assign idle = state == IDLE;
    assign spi_cs_n = !flash_open;
    assign spi_mosi = state == CMD && pos[4:1] == 4'b0011; // 0x03, then 24 zero address bits
    assign out_valid = state == OUTPUT;
    assign out_data = high_byte ? {{4{result[11]}}, result[11:8]} : result[7:0];

    mac_unit mac (
        .clk(clk), .accum_mode(state != SCORE),
        .load(state == SCORE && consume && pos[9:3] == 7'd0), .subtract(second_pass), .M(maximum),
        .score_en(state == SCORE && consume && pos[3]), .qi(q), .ki(serial),
        .first(token == 4'd0), .accum_en(state == VALUE && consume), .W(weight), .sel(component),
        .v(serial), .bit_sel(~pos[2:0]),
        .S(score), .L(weight_sum), .O0(o0), .O1(o1)
    );
    max_reg max_unit (
        .clk(clk), .first(token == 4'd0), .en(score_done && !second_pass), .S_in(score), .M(maximum)
    );
    exp_lut #(.REGISTERED(0)) exponent_unit (
        .clk(clk), .rst_n(rst_n), .start(1'b0), .D(score), .shift(score_shift),
        .done(exp_done), .W(weight)
    );
    divider #(.LATCH_DENOMINATOR(0), .CHECK_INVALID(0)) divider_unit (
        .clk(clk), .rst_n(rst_n), .start(state == DIV_START && component == output_index),
        .sum_in(o0), .denominator(weight_sum), .busy(div_busy), .done(div_done), .result(result)
    );
    wire _unused = &{div_busy, exp_done, o1, 1'b0};

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state <= IDLE;
            flash_open <= 1'b0;
            spi_sck <= 1'b0;
            component <= 1'b0;
            score_done <= 1'b0;
        end else begin
            component <= !component;
            score_done <= 1'b0;
            if (rise) begin
                spi_sck <= 1'b1;
                rx_bit <= spi_miso;
            end
            // Pass 1: max_reg takes the finished score in this cycle.
            if (score_done && !second_pass) begin
                token <= token == last ? 4'd0 : token + 4'd1;
                second_pass <= token == last;
            end
            if (consume) begin
                spi_sck <= 1'b0;
                pos <= pos + 10'd1;
            end
            case (state)
                IDLE: if (start) begin
                    token <= 4'd0;
                    pos <= 10'd0;
                    high_byte <= 1'b0;
                    second_pass <= cont;
                    if (cont) state <= SCORE;
                    else begin flash_open <= 1'b0; state <= RESTART; end
                end
                RESTART: begin flash_open <= 1'b1; state <= CMD; end // CS high for this cycle
                CMD: if (consume && pos[4:0] == 5'd31) begin pos <= 10'd0; state <= SCORE; end
                SCORE: if (consume) begin
                    if (!pos[3]) q <= {q[6:0], rx_bit};
                    if (&pos) begin // last K bit of the row; pos wraps to 0
                        score_done <= 1'b1;
                        if (second_pass) state <= VALUE;
                    end
                end
                VALUE: if (consume && pos[3:0] == 4'd15) begin
                    pos <= 10'd0;
                    if (token == last) begin output_index <= 1'b0; state <= DIV_START; end
                    else begin token <= token + 4'd1; state <= SCORE; end
                end
                DIV_START: if (component == output_index) state <= DIV_WAIT;
                DIV_WAIT: if (div_done) state <= OUTPUT;
                OUTPUT: if (out_ready) begin
                    high_byte <= !high_byte;
                    if (high_byte) begin // second byte of this component accepted
                        output_index <= 1'b1;
                        state <= output_index ? IDLE : DIV_START;
                    end
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule

`default_nettype wire
