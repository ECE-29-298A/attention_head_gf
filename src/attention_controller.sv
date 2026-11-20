`default_nettype none

// Two-pass INT8 attention core: one 64-dim query over 1..16 tokens, one 4-wide
// V chunk per run. Pass 1 scores every token and keeps the maximum; pass 2
// rescores, weights each token through the exponent table and accumulates V.
// A score runs component by component: read Q[c], read K[t][c], 8 MAC cycles.
//
// Flash map: Q[c] at 0x000 + c, K[t][c] at 0x400 + 64t + c, V[t][c] at 0x800 + 64t + c.
// Memory: mem_req holds a stable mem_addr until mem_ack. The byte arrives on
// rx_bit, MSB first, sampled on the edges that end rx_valid cycles.
// last, score_shift and chunk must be held from start until idle again.
// Only state and phase are reset; everything else is loaded before use.
module attention_controller (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       start,       // accepted when idle
    input  wire [3:0] last,        // token count - 1
    input  wire [3:0] score_shift, // exp_lut rounds M - S and shifts it right by this
    input  wire [3:0] chunk,       // output V components 4*chunk .. 4*chunk+3
    output wire       idle,
    output wire        mem_req,
    output wire [11:0] mem_addr,
    input  wire        mem_ack,
    input  wire        rx_valid,
    input  wire        rx_bit,
    // Components 0..3, each a 12-bit signed result (INT8 plus 4 fractional bits)
    // sent low byte first, then the sign-extended high byte. A byte transfers on
    // a rising edge when out_valid && out_ready.
    output wire       out_valid,
    input  wire       out_ready,
    output wire [7:0] out_data
);
    localparam [2:0] IDLE = 3'd0, READ = 3'd1, MAC = 3'd2, ALIGN = 3'd3,
                     ACCUM = 3'd4, DIV_START = 3'd5, DIV_WAIT = 3'd6, OUTPUT = 3'd7;
    localparam [1:0] Q = 2'd0, K = 2'd1, V = 2'd2;
    logic [2:0] state;
    logic [1:0] kind;        // what READ fetches
    logic [3:0] token;
    logic [5:0] comp;        // Q/K component of the score in progress
    logic second_pass;
    logic [1:0] phase;       // free-running; the accum ring holds component `phase` in O0
    // MAC and accumulate bit; V byte counter (bits 2:1); output byte (2:1 component, 0 high byte).
    logic [2:0] bit_index;
    // Scoring: {.., Q[c], K[c]}. Accumulating: {V3, V2, V1, V0}, rotated so the
    // current component is in the low byte.
    logic [31:0] operands;

    wire last_token = token == last;
    wire score_done = state == MAC && bit_index == 3'd7 && comp == 6'd63;
    wire signed [21:0] score, score_next, maximum;
    wire signed [19:0] o0, o1, o2, o3;
    wire [11:0] weight_sum;
    wire [7:0] weight;
    wire div_done;
    wire signed [11:0] result;

    assign idle = state == IDLE;
    assign mem_req = state == READ;
    // V bytes are read 3, 2, 1, 0 so that V0 ends in the low byte.
    assign mem_addr = {kind, kind == Q ? 4'd0 : token,
                       kind == V ? {chunk, ~bit_index[2:1]} : comp};
    assign out_valid = state == OUTPUT;
    assign out_data = bit_index[0] ? {{4{result[11]}}, result[11:8]} : result[7:0];

    score_mac score_unit (
        .clk(clk), .first(state == MAC && comp == 6'd0 && bit_index == 3'd0),
        .en(state == MAC), .qi(operands[15:8]), .ki(operands[7:0]), .bit_sel(bit_index),
        .S(score), .S_next(score_next)
    );
    max_reg max_unit (
        .clk(clk), .first(token == 4'd0), .en(score_done && !second_pass),
        .S_in(score_next), .M(maximum)
    );
    // M and S hold through pass 2's V read and accumulation, so W is combinational.
    exp_lut exponent_unit (.M(maximum), .S(score), .shift(score_shift), .W(weight));
    accum accum_unit (
        .clk(clk), .first(token == 4'd0), .en(state == ACCUM), .W(weight),
        .sel(phase), .bit_sel(bit_index), .v(operands[7:0]),
        .L(weight_sum), .O0(o0), .O1(o1), .O2(o2), .O3(o3)
    );
    // Start when the ring brings the output component into O0.
    divider divider_unit (
        .clk(clk), .rst_n(rst_n), .start(state == DIV_START && phase == bit_index[2:1]),
        .sum_in(o0), .denominator(weight_sum), .done(div_done), .result(result)
    );
    wire _unused = &{o1, o2, o3, 1'b0};

    always_ff @(posedge clk)
        if (rx_valid) operands <= {operands[30:0], rx_bit};
        else if (state == ACCUM) operands <= {operands[7:0], operands[31:8]};

    always_ff @(posedge clk) begin
        phase <= rst_n ? phase + 2'd1 : 2'd0;
        if (!rst_n) state <= IDLE;
        else case (state)
            IDLE: if (start) begin
                token <= 0; comp <= 0; second_pass <= 0; bit_index <= 0;
                kind <= Q; state <= READ;
            end
            READ: if (mem_ack) case (kind)
                Q: kind <= K;
                K: state <= MAC;
                default: begin
                    bit_index[2:1] <= bit_index[2:1] + 2'd1;
                    if (bit_index[2:1] == 2'd3) state <= ALIGN;
                end
            endcase
            MAC: begin
                bit_index <= bit_index + 3'd1;
                if (bit_index == 3'd7) begin
                    comp <= comp + 6'd1;
                    kind <= comp == 6'd63 && second_pass ? V : Q;
                    state <= READ;
                    if (comp == 6'd63 && !second_pass) begin
                        token <= last_token ? 4'd0 : token + 4'd1;
                        second_pass <= last_token;
                    end
                end
            end
            ALIGN: if (phase == 2'd3) state <= ACCUM; // accumulate from component 0
            // 32 cycles: bit_index outer, phase (the component) inner.
            ACCUM: if (phase == 2'd3) begin
                bit_index <= bit_index + 3'd1;
                if (bit_index == 3'd7) begin
                    token <= token + 4'd1;
                    kind <= Q;
                    state <= last_token ? DIV_START : READ;
                end
            end
            DIV_START: if (phase == bit_index[2:1]) state <= DIV_WAIT;
            DIV_WAIT: if (div_done) state <= OUTPUT;
            OUTPUT: if (out_ready) begin
                bit_index <= bit_index + 3'd1;
                if (bit_index[0]) state <= bit_index == 3'd7 ? IDLE : DIV_START;
            end
        endcase
    end
endmodule

`default_nettype wire
