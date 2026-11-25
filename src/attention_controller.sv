`default_nettype none

// Two-pass INT8 core: first find the maximum, then recompute scores and accumulate.
// Scores are 64-dim dot products (one SmolLM head); outputs are one 4-dim chunk
// of V per run, so a full 64-dim head output takes 16 runs (chunk = 0..15).
// Q and K are read one byte pair per dimension: Q twice per token (once per
// pass), K twice, V once; no scores or weights are written to external memory.
// Pass 2 preloads the score with the maximum and subtracts, so the score unit
// produces D = M - S directly for the exponent table.
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
    // Combinational LUT: weight = 255 * exp(-round((maximum - score) / 2^shift) / 4).
    wire [21:0] exp_delta;            // D = M - S >= 0 from the pass-2 score unit; stable through accumulation.
    wire exp_done;                    // Unused: the combinational LUT has no latency.
    wire [7:0] exp_weight;            // Unsigned, unnormalized attention weight: 0–255.

    // Internal divider handshake: result = round(16 * weighted_sum / weight_sum).
    wire div_start;                   // One-cycle request to normalize one output component.
    wire signed [19:0] div_sum;       // Weighted sum O_i = sum(W_j * V_j,i), read from the accum ring.
    wire [11:0] div_denominator;      // Weight sum L = sum(W_j); positive for valid input.
    wire div_busy;                    // Divider is computing; sequencing waits for div_done.
    wire div_done;                    // Completion pulse; div_result is valid.
    wire signed [11:0] div_result;    // Rounded signed output, 4 fractional bits.

    typedef enum logic [4:0] {
        IDLE, INIT, QUERY_READ, KEY_READ, KEY_READY, SCORE_MAC,
        SCORE_CAPTURE, KEY_NEXT,
        VALUE_READ, VALUE_READY, ACCUM_STEP, VALUE_NEXT,
        DIV_START, DIV_WAIT, OUTPUT_WAIT, COMPLETE, MEM_REQUEST, MEM_WAIT
    } state_t;
    state_t state, return_state;
    wire [3:0] last; // token_count - 1
    logic [3:0] token;
    logic [5:0] dim; // which of the 64 Q/K components the MAC is on
    logic second_pass; // 0: find maximum. 1: use the frozen maximum and accumulate.
    // component is a free-running phase (steps every clock). The accum ring rotates in step,
    // so accum O0 always holds component `component`. MAC loops start at phase 0.
    logic [1:0] component, output_index;
    logic high_byte; // 0: send div_result[7:0] next. 1: send its sign-extended top 4 bits.
    // bit of the multiplier operand (shift-add); bit_index[1:0] also counts the 4 bytes of a V row read.
    logic [2:0] bit_index;
    // Score: {k, q, -, -} for the current dimension. Accumulate: this token's 4 V components.
    logic [31:0] operands;
    wire [3:0] shift, chunk_sel;
    if (LATCH_CONFIG) begin : g_config
        logic [7:0] saved_config;
        logic [3:0] saved_last;
        always_ff @(posedge clk)
            if (start && start_ready) begin
                saved_config <= {chunk, score_shift};
                saved_last <= 4'(token_count - 5'd1);
            end
        assign {chunk_sel, shift} = saved_config;
        assign last = saved_last;
    end else begin : g_direct_config
        // Caller holds token_count, chunk and score_shift until done.
        assign {chunk_sel, shift} = {chunk, score_shift};
        assign last = 4'(token_count - 5'd1);
    end
    // score_mac holds D, so W is stable from SCORE_CAPTURE through VALUE_NEXT.
    wire [7:0] weight = exp_weight;
    wire signed [21:0] score, maximum;
    wire signed [19:0] o0, o1, o2, o3;
    wire signed [7:0] qi = $signed(operands[23:16]);
    wire signed [7:0] ki = $signed(operands[31:24]);
    wire signed [7:0] vi = $signed(operands[7:0]);

    assign start_ready = rst_n && state == IDLE && token_count >= 1 && token_count <= 16;
    assign busy = state != IDLE;
    assign mem_req_valid = rst_n && state == MEM_REQUEST;
    assign mem_write = 1'b0;
    assign mem_wdata = 8'd0;
    // score_mac holds D until the next token's first query read, after the exponent and accumulate steps.
    assign exp_delta = score;
    // divider holds result until its next completion, after both bytes are accepted.
    assign out_data = high_byte ? {{4{div_result[11]}}, div_result[11:8]} : div_result[7:0];
    // Address is decoded from the pending return state; stable while MEM_REQUEST waits.
    // The query read returns to KEY_READ and the key read to KEY_READY.
    wire query_read = return_state == KEY_READ;
    wire value_read = return_state == VALUE_READ || return_state == VALUE_READY;
    assign mem_addr = query_read ? Q_BASE + {10'b0, dim}
                    : value_read ? V_BASE + {6'b0, token, chunk_sel, bit_index[1:0]}
                    : K_BASE + {6'b0, token, dim};
    // Start when the ring brings component output_index into O0.
    assign div_start = rst_n && state == DIV_START && component == output_index;
    assign div_sum = o0;
    assign out_valid = rst_n && state == OUTPUT_WAIT;

    mac_unit mac (
        .clk(clk), .accum_mode(state != SCORE_MAC),
        .load(state == QUERY_READ && dim == 0), .subtract(second_pass), .M(maximum),
        .score_en(state == SCORE_MAC), .qi(qi), .ki(ki),
        .first(token == 4'd0), .accum_en(state == ACCUM_STEP), .W(weight), .sel(component),
        .v(vi), .bit_sel(bit_index),
        .S(score), .L(div_denominator), .O0(o0), .O1(o1), .O2(o2), .O3(o3)
    );
    max_reg max_unit (
        .clk(clk), .first(token == 4'd0),
        .en(state == SCORE_CAPTURE && !second_pass), .S_in(score), .M(maximum)
    );
    exp_lut #(.REGISTERED(0)) exponent_unit (
        .clk(clk), .rst_n(rst_n), .start(1'b0), .D(exp_delta),
        .shift(shift), .done(exp_done), .W(exp_weight)
    );
    divider #(.LATCH_DENOMINATOR(0), .CHECK_INVALID(0)) divider_unit (
        .clk(clk), .rst_n(rst_n), .start(div_start), .sum_in(div_sum),
        .denominator(div_denominator), .busy(div_busy), .done(div_done), .result(div_result)
    );
    // Waiting for div_done prevents another start while busy; no busy polling needed.
    wire _unused = &{div_busy, exp_done, o1, o2, o3, operands[15:8], 1'b0};

    // Launch one byte read; return_state selects the address.
    task automatic read_byte_request(input state_t next_state);
        return_state <= next_state;
        state <= MEM_REQUEST;
    endtask

    // Bytes shift in from the top. A score pair leaves q in [23:16] and k in
    // [31:24]. A V row leaves byte 0 low; it rotates during each accumulate
    // cycle so its current component is always in the low byte.
    always_ff @(posedge clk)
        if (state == MEM_WAIT && mem_rsp_valid)
            operands <= {mem_rdata, operands[31:8]};
        else if (state == ACCUM_STEP)
            operands <= {operands[7:0], operands[31:8]};

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state <= IDLE;
            return_state <= IDLE;
            token <= 0;
            dim <= 0;
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
                    token <= 0;
                    dim <= 0;
                    second_pass <= 0;
                    high_byte <= 0;
                    done <= 0;
                    state <= INIT;
                end
                INIT: state <= QUERY_READ;
                // Each dimension: one Q byte, then the token's matching K byte.
                // S is (pre)loaded during the dimension-0 query read.
                QUERY_READ: read_byte_request(KEY_READ);
                KEY_READ: read_byte_request(KEY_READY);
                KEY_READY: begin bit_index <= 0; state <= SCORE_MAC; end
                // 8 cycles per dimension: one bit of k per cycle through the ripple adder.
                // After 64 dimensions (dim wraps back to 0) the score is complete.
                SCORE_MAC: begin
                    bit_index <= bit_index + 1'b1;
                    if (bit_index == 7) begin
                        dim <= dim + 1'b1;
                        state <= state_t'(dim == 63 ? SCORE_CAPTURE : QUERY_READ);
                    end
                end
                // Capture on the edge AFTER the final MAC updates S.
                SCORE_CAPTURE: begin
                    state <= state_t'(second_pass ? VALUE_READ : KEY_NEXT);
                end
                KEY_NEXT: if (token == last) begin
                    token <= 0;
                    second_pass <= 1;
                    state <= QUERY_READ; // accum loads (not adds) on token 0: no clear needed
                end else begin token <= token + 1'b1; state <= QUERY_READ; end
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
