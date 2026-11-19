`default_nettype none

// Two-pass INT8 core: first find the maximum, then recompute scores and accumulate.
// Scores are 64-dim dot products (one SmolLM head); outputs are one 4-dim chunk
// of V per run, so a full 64-dim head output takes 16 runs (chunk = 0..15).
// Q and K are read in 16 groups of 4 bytes per score: Q twice per token (once per
// pass), K twice, V once; no scores or weights are written to external memory.
// All arithmetic blocks are instantiated below; only host and memory are external.
// All resets are synchronous. Reset must also cancel/drain pending memory reads.
module attention_controller #(
    parameter logic [15:0] Q_BASE = 16'h0000, // 64 INT8 Q components -> 64 bytes
    parameter logic [15:0] K_BASE = 16'h0040, // 64 bytes per token, max 16 tokens -> 1 KB
    parameter logic [15:0] V_BASE = 16'h0440, // 64 bytes per token, max 16 tokens -> 1 KB
    parameter bit LATCH_CONFIG = 1'b1 // latch shift/chunk unless the caller holds them through completion
) (
    // Clock and reset
    input wire clk,
    input wire rst_n,

    // Start and configuration
    input wire start,                 // Request a transaction; accepted when start && start_ready.
    input wire [4:0] token_count,     // Number of tokens (K/V rows): 1–16. Captured when start is accepted.
    input wire [3:0] score_shift,     // exp_lut rounds M - S and shifts it right by this (0..15). Captured when start is accepted.
    input wire [3:0] chunk,           // Which 4 of V's 64 components to output: 4*chunk .. 4*chunk+3. Captured when start is accepted.
    output wire start_ready,         // High when idle, reset released, and token_count is valid.
    output wire busy,                // High when processing
    output logic done,               // Sticky flag: all eight output bytes accepted. Cleared on start/reset.

    // Byte-memory interface: one outstanding request at a time.
    // A request is accepted on a rising edge when mem_req_valid && mem_req_ready.
    output wire mem_req_valid,       // Controller is requesting memory.
    input wire mem_req_ready,        // Memory adapter can accept the request.
    output wire mem_write,           // Always 0: this core only reads memory. Kept for adapter compatibility.
    output wire [15:0] mem_addr,      // Byte address; held stable until request acceptance.
    output wire [7:0] mem_wdata,      // Always 0: no write data is used by this core.
    input wire mem_rsp_valid,        // Completion of the accepted read, in a later cycle.
    input wire [7:0] mem_rdata,       // Returned read byte; valid with mem_rsp_valid.

    // Output interface: components are sent in order 0, 1, 2, 3. Each is a 12-bit
    // signed result (INT8 plus 4 fractional bits) sent as two bytes, low byte first;
    // the high byte is sign-extended, so each pair reads as a signed 16-bit value.
    // A byte transfers on a rising edge when out_valid && out_ready.
    output wire out_valid,           // A completed output byte is available.
    input wire out_ready,            // Receiver can accept the current output byte.
    output wire [7:0] out_data       // Result byte; held stable while valid and not ready.
);
    // Internal LUT handshake: weight = 255 * exp(-round((maximum - score) / 2^shift) / 4).
    wire exp_start;                   // One-cycle request for the current token's weight.
    wire signed [21:0] exp_max;       // Final maximum across all tokens.
    wire signed [21:0] exp_score;      // Current score; stable until completion.
    wire exp_done;                    // Completion pulse; exp_weight is valid.
    wire [7:0] exp_weight;            // Unsigned, unnormalized attention weight: 0–255.

    // Internal divider handshake: result = round(16 * weighted_sum / weight_sum).
    wire div_start;                   // One-cycle request to normalize one output component.
    wire signed [19:0] div_sum;       // Weighted sum O_i = sum(W_j * V_j,i), read from the accum ring.
    wire [11:0] div_denominator;      // Weight sum L = sum(W_j); positive for valid input.
    wire div_busy;                    // Divider is computing; sequencing waits for div_done.
    wire div_done;                    // Completion pulse; div_result is valid.
    wire signed [11:0] div_result;    // Rounded signed output, 4 fractional bits.

    typedef enum logic [4:0] {
        IDLE, INIT, QUERY_READ, QUERY_READY, KEY_READ, KEY_READY, SCORE_CLEAR, SCORE_MAC,
        SCORE_CAPTURE, KEY_NEXT, EXP_START, EXP_WAIT,
        VALUE_READ, VALUE_READY, ACCUM_STEP, VALUE_NEXT,
        DIV_START, DIV_WAIT, OUTPUT_WAIT, COMPLETE, MEM_REQUEST, MEM_WAIT
    } state_t;
    state_t state, return_state;
    logic [3:0] last; // token_count - 1
    logic [3:0] token;
    logic [3:0] group; // which 4 of the 64 Q/K components the MAC is on
    logic second_pass; // 0: find maximum. 1: use the frozen maximum and accumulate.
    // component is a free-running phase (steps every clock). The accum ring rotates in step,
    // so accum O0 always holds component `component`. MAC loops start at phase 0.
    logic [1:0] component, output_index;
    logic high_byte; // 0: send div_result[7:0] next. 1: send its sign-extended top 4 bits.
    // bit of the multiplier operand (shift-add); bit_index[1:0] also counts the 4 bytes of a row read.
    logic [2:0] bit_index;
    logic [31:0] query;    // current group of 4 Q components, read from memory
    logic [31:0] operands; // current group of 4 K components, or this token's 4 V components
    wire [3:0] shift, chunk_sel;
    if (LATCH_CONFIG) begin : g_config
        logic [7:0] saved_config;
        always_ff @(posedge clk)
            if (start && start_ready) saved_config <= {chunk, score_shift};
        assign {chunk_sel, shift} = saved_config;
    end else begin : g_direct_config
        assign {chunk_sel, shift} = {chunk, score_shift};
    end
    // exp_lut holds W until its next start, so no local copy is needed.
    wire [7:0] weight = exp_weight;
    wire signed [21:0] score, maximum;
    wire signed [19:0] o0, o1, o2, o3;
    wire signed [7:0] qi = $signed(query[8*component +: 8]);
    wire signed [7:0] ki = $signed(operands[7:0]);

    assign start_ready = rst_n && state == IDLE && token_count >= 1 && token_count <= 16;
    assign busy = state != IDLE;
    assign mem_req_valid = rst_n && state == MEM_REQUEST;
    assign mem_write = 1'b0;
    assign mem_wdata = 8'd0;
    assign exp_start = rst_n && state == EXP_START;
    assign exp_max = maximum;
    // score_mac holds S until the next token's first SCORE_CLEAR, after the exponent and accumulate steps.
    assign exp_score = score;
    // divider holds result until its next completion, after both bytes are accepted.
    assign out_data = high_byte ? {{4{div_result[11]}}, div_result[11:8]} : div_result[7:0];
    // Address is decoded from the pending return state; stable while MEM_REQUEST waits.
    wire query_read = return_state == QUERY_READ || return_state == QUERY_READY;
    wire value_read = return_state == VALUE_READ || return_state == VALUE_READY;
    assign mem_addr = query_read ? Q_BASE + {10'b0, group, bit_index[1:0]}
                    : value_read ? V_BASE + {6'b0, token, chunk_sel, bit_index[1:0]}
                    : K_BASE + {6'b0, token, group, bit_index[1:0]};
    // Start when the ring brings component output_index into O0.
    assign div_start = rst_n && state == DIV_START && component == output_index;
    assign div_sum = o0;
    assign out_valid = rst_n && state == OUTPUT_WAIT;

    score_mac score_unit (
        .clk(clk), .rst_n(rst_n), .clear(state == INIT || (state == SCORE_CLEAR && group == 0)),
        .en(state == SCORE_MAC), .qi(qi), .ki(ki), .bit_sel(bit_index), .S(score)
    );
    max_reg max_unit (
        .clk(clk), .rst_n(rst_n), .clear(state == INIT),
        .en(state == SCORE_CAPTURE && !second_pass), .S_in(score), .M(maximum)
    );
    accum accum_unit (
        .clk(clk), .first(token == 4'd0),
        .en(state == ACCUM_STEP), .W(weight), .sel(component), .bit_sel(bit_index), .v(ki),
        .L(div_denominator), .O0(o0), .O1(o1), .O2(o2), .O3(o3)
    );
    exp_lut exponent_unit (
        .clk(clk), .rst_n(rst_n), .start(exp_start), .M(exp_max), .S(exp_score),
        .shift(shift), .done(exp_done), .W(exp_weight)
    );
    divider #(.LATCH_DENOMINATOR(0)) divider_unit (
        .clk(clk), .rst_n(rst_n), .start(div_start), .sum_in(div_sum),
        .denominator(div_denominator), .busy(div_busy), .done(div_done), .result(div_result)
    );
    // Waiting for div_done prevents another start while busy; no busy polling needed.
    wire _unused = &{div_busy, o1, o2, o3, 1'b0};

    // Launch one byte read; return_state selects the address.
    task automatic read_byte_request(input state_t next_state);
        return_state <= next_state;
        state <= MEM_REQUEST;
    endtask

    // Byte 0 enters first. Rotate the loaded K/V group during each arithmetic
    // cycle so its current component is always in the low byte. Q is indexed
    // by the phase instead, so it does not rotate.
    always_ff @(posedge clk)
        if (state == MEM_WAIT && mem_rsp_valid && query_read)
            query <= {mem_rdata, query[31:8]};
        else if (state == MEM_WAIT && mem_rsp_valid)
            operands <= {mem_rdata, operands[31:8]};
        else if (state == SCORE_MAC || state == ACCUM_STEP)
            operands <= {operands[7:0], operands[31:8]};

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state <= IDLE;
            return_state <= IDLE;
            last <= 0;
            token <= 0;
            group <= 0;
            second_pass <= 0;
            component <= 0;
            bit_index <= 0;
            output_index <= 0;
            high_byte <= 0;
            done <= 0;
        end else begin
            component <= component + 1'b1;
            case (state)
                IDLE: if (start && start_ready) begin
                    last <= 4'(token_count - 5'd1);
                    token <= 0;
                    group <= 0;
                    second_pass <= 0;
                    high_byte <= 0;
                    done <= 0;
                    state <= INIT;
                end
                INIT: state <= QUERY_READ;
                // Each group: 4 Q bytes, then the token's matching 4 K bytes.
                QUERY_READ: read_byte_request(state_t'(bit_index[1:0] == 3 ? QUERY_READY : QUERY_READ));
                QUERY_READY: state <= KEY_READ;
                KEY_READ: read_byte_request(state_t'(bit_index[1:0] == 3 ? KEY_READY : KEY_READ));
                KEY_READY: begin bit_index <= 0; state <= SCORE_CLEAR; end
                // Wait so the MAC loop starts at phase 0. S is cleared here only for group 0.
                SCORE_CLEAR: if (component == 3) state <= SCORE_MAC;
                // 32 cycles per group: one bit of one component per cycle through the ripple adder.
                // Component (the phase) is the inner loop; bit_index steps when it wraps.
                // After 16 groups (group wraps back to 0) the 64-dim score is complete.
                SCORE_MAC: if (component == 3) begin
                    bit_index <= bit_index + 1'b1;
                    if (bit_index == 7) begin
                        group <= group + 1'b1;
                        state <= state_t'(group == 15 ? SCORE_CAPTURE : QUERY_READ);
                    end
                end
                // Capture on the edge AFTER the final MAC updates S.
                SCORE_CAPTURE: begin
                    state <= state_t'(second_pass ? EXP_START : KEY_NEXT);
                end
                KEY_NEXT: if (token == last) begin
                    token <= 0;
                    second_pass <= 1;
                    state <= QUERY_READ; // accum loads (not adds) on token 0: no clear needed
                end else begin token <= token + 1'b1; state <= QUERY_READ; end
                EXP_START: state <= EXP_WAIT;
                EXP_WAIT: if (exp_done) state <= VALUE_READ;
                // The shared operand buffer is refilled with V.
                VALUE_READ: read_byte_request(state_t'(bit_index[1:0] == 3 ? VALUE_READY : VALUE_READ));
                VALUE_READY: begin bit_index <= 0; if (component == 3) state <= ACCUM_STEP; end
                // 32 cycles, same order as SCORE_MAC, through the shared ripple adder.
                ACCUM_STEP: if (component == 3) begin
                    bit_index <= bit_index + 1'b1;
                    if (bit_index == 7) state <= VALUE_NEXT;
                end
                VALUE_NEXT: if (token == last) begin
                    output_index <= 0; state <= DIV_START;
                end else begin token <= token + 1'b1; state <= QUERY_READ; end
                DIV_START: if (component == output_index) state <= DIV_WAIT;
                DIV_WAIT: if (div_done) state <= OUTPUT_WAIT;
                OUTPUT_WAIT: if (out_ready) begin
                    high_byte <= !high_byte;
                    if (high_byte) begin // second byte of this component accepted
                        if (output_index == 3) state <= COMPLETE;
                        else begin output_index <= output_index + 1'b1; state <= DIV_START; end
                    end
                end
                COMPLETE: begin done <= 1; state <= IDLE; end
                MEM_REQUEST: if (mem_req_ready) state <= MEM_WAIT;
                // Byte 0 is read first, so shifting in from the top leaves {b3, b2, b1, b0}.
                MEM_WAIT: if (mem_rsp_valid) begin
                    bit_index <= bit_index + 1'b1;
                    state <= return_state;
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule

`default_nettype wire
