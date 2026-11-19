`default_nettype none

// Two-pass INT8 core: first find the maximum, then recompute scores and accumulate.
// K is read twice and V once; no scores or weights are written to external memory.
// All arithmetic blocks are instantiated below; only host and memory are external.
// All resets are synchronous. Reset must also cancel/drain pending memory reads.
module attention_controller #(
    parameter logic [15:0] K_BASE = 16'h0000, // 4 bytes per token (4 INT8 components), max 16 tokens -> 64 bytes
    parameter logic [15:0] V_BASE = 16'h0040, // 4 bytes per token (4 INT8 components), max 16 tokens -> 64 bytes
    parameter bit LATCH_QUERY = 1'b1 // latch Q unless the caller holds it through completion
) (
    // Clock and reset
    input wire clk,
    input wire rst_n,

    // Start and configuration
    input wire start,                 // Request a transaction; accepted when start && start_ready.
    input wire [4:0] token_count,     // Number of tokens (K/V rows): 1–16. Captured when start is accepted.
    input wire [31:0] query_packed,   // Four signed INT8 Q components: Q0=[7:0], Q1=[15:8], Q2=[23:16], Q3=[31:24]. Captured when start is accepted.
    output wire start_ready,         // High when idle, reset released, and token_count is valid.
    output wire busy,                // High when processing
    output logic done,               // Sticky flag: all four outputs accepted. Cleared on start/reset.

    // Byte-memory interface: one outstanding request at a time.
    // A request is accepted on a rising edge when mem_req_valid && mem_req_ready.
    output wire mem_req_valid,       // Controller is requesting memory.
    input wire mem_req_ready,        // Memory adapter can accept the request.
    output wire mem_write,           // Always 0: this core only reads memory. Kept for adapter compatibility.
    output wire [15:0] mem_addr,      // Byte address; held stable until request acceptance.
    output wire [7:0] mem_wdata,      // Always 0: no write data is used by this core.
    input wire mem_rsp_valid,        // Completion of the accepted read, in a later cycle.
    input wire [7:0] mem_rdata,       // Returned read byte; valid with mem_rsp_valid.

    // Output interface: components are sent in order 0, 1, 2, 3.
    // A byte transfers on a rising edge when out_valid && out_ready.
    output wire out_valid,           // A completed output byte is available.
    input wire out_ready,            // Receiver can accept the current output byte.
    output wire signed [7:0] out_data // INT8 result; held stable while valid and not ready.
);
    // Internal LUT handshake: approximate weight = 255 * exp((score - maximum) / 2).
    wire exp_start;                   // One-cycle request for the current token's weight.
    wire signed [17:0] exp_max;       // Final maximum across all tokens.
    wire signed [17:0] exp_score;      // Current score; stable until completion.
    wire exp_done;                    // Completion pulse; exp_weight is valid.
    wire [7:0] exp_weight;            // Unsigned, unnormalized attention weight: 0–255.

    // Internal divider handshake: result = round(weighted_sum / weight_sum).
    wire div_start;                   // One-cycle request to normalize one output component.
    wire signed [19:0] div_sum;       // Weighted sum O_i = sum(W_j * V_j,i), read from the accum ring.
    wire [11:0] div_denominator;      // Weight sum L = sum(W_j); positive for valid input.
    wire div_busy;                    // Divider is computing; sequencing waits for div_done.
    wire div_done;                    // Completion pulse; div_result is valid.
    wire signed [7:0] div_result;     // Rounded signed INT8 output.

    typedef enum logic [4:0] {
        IDLE, INIT, KEY_READ, KEY_READY, SCORE_CLEAR, SCORE_MAC,
        SCORE_CAPTURE, KEY_NEXT, EXP_START, EXP_WAIT,
        VALUE_READ, VALUE_READY, ACCUM_STEP, VALUE_NEXT,
        DIV_START, DIV_WAIT, OUTPUT_WAIT, COMPLETE, MEM_REQUEST, MEM_WAIT
    } state_t;
    state_t state, return_state;
    logic [3:0] last; // token_count - 1
    logic [3:0] token;
    logic second_pass; // 0: find maximum. 1: use the frozen maximum and accumulate.
    // component is a free-running phase (steps every clock). The accum ring rotates in step,
    // so accum O0 always holds component `component`. MAC loops start at phase 0.
    logic [1:0] component, output_index;
    // bit of the multiplier operand (shift-add); bit_index[1:0] also counts the 4 bytes of a row read.
    logic [2:0] bit_index;
    wire [31:0] query;
    logic [31:0] operands;
    if (LATCH_QUERY) begin : g_query
        logic [31:0] saved_query;
        always_ff @(posedge clk)
            if (start && start_ready) saved_query <= query_packed;
        assign query = saved_query;
    end else begin : g_direct_query
        assign query = query_packed;
    end
    // exp_lut holds W until its next start, so no local copy is needed.
    wire [7:0] weight = exp_weight;
    wire signed [17:0] score, maximum;
    wire signed [19:0] o0, o1, o2, o3;
    wire signed [7:0] qi = $signed(query[8*component +: 8]);
    wire signed [7:0] ki = $signed(operands[8*component +: 8]);

    assign start_ready = rst_n && state == IDLE && token_count >= 1 && token_count <= 16;
    assign busy = state != IDLE;
    assign mem_req_valid = rst_n && state == MEM_REQUEST;
    assign mem_write = 1'b0;
    assign mem_wdata = 8'd0;
    assign exp_start = rst_n && state == EXP_START;
    assign exp_max = maximum;
    // score_mac holds S until SCORE_CLEAR, which follows the exponent and accumulate steps.
    assign exp_score = score;
    // divider holds result until its next completion, after this byte is accepted.
    assign out_data = div_result;
    // Address is decoded from the pending return state; stable while MEM_REQUEST waits.
    assign mem_addr = (return_state == VALUE_READ || return_state == VALUE_READY ? V_BASE : K_BASE)
        + {10'b0, token, bit_index[1:0]};
    // Start when the ring brings component output_index into O0.
    assign div_start = rst_n && state == DIV_START && component == output_index;
    assign div_sum = o0;
    assign out_valid = rst_n && state == OUTPUT_WAIT;

    score_mac score_unit (
        .clk(clk), .rst_n(rst_n), .clear(state == INIT || state == SCORE_CLEAR),
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
        .done(exp_done), .W(exp_weight)
    );
    divider divider_unit (
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

    // The full row is overwritten before the first arithmetic access.
    always_ff @(posedge clk)
        if (state == MEM_WAIT && mem_rsp_valid)
            operands <= {mem_rdata, operands[31:8]};

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state <= IDLE;
            return_state <= IDLE;
            last <= 0;
            token <= 0;
            second_pass <= 0;
            component <= 0;
            bit_index <= 0;
            output_index <= 0;
            done <= 0;
        end else begin
            component <= component + 1'b1;
            case (state)
                IDLE: if (start && start_ready) begin
                    last <= 4'(token_count - 5'd1);
                    token <= 0;
                    second_pass <= 0;
                    done <= 0;
                    state <= INIT;
                end
                INIT: state <= KEY_READ;
                KEY_READ: read_byte_request(state_t'(bit_index[1:0] == 3 ? KEY_READY : KEY_READ));
                KEY_READY: begin bit_index <= 0; state <= SCORE_CLEAR; end
                // Wait so the MAC loop starts at phase 0.
                SCORE_CLEAR: if (component == 3) state <= SCORE_MAC;
                // 32 cycles: one bit of one component per cycle through the ripple adder.
                // Component (the phase) is the inner loop; bit_index steps when it wraps.
                SCORE_MAC: if (component == 3) begin
                    bit_index <= bit_index + 1'b1;
                    if (bit_index == 7) state <= SCORE_CAPTURE;
                end
                // Capture on the edge AFTER the final MAC updates S.
                SCORE_CAPTURE: begin
                    state <= state_t'(second_pass ? EXP_START : KEY_NEXT);
                end
                KEY_NEXT: if (token == last) begin
                    token <= 0;
                    second_pass <= 1;
                    state <= KEY_READ; // accum loads (not adds) on token 0: no clear needed
                end else begin token <= token + 1'b1; state <= KEY_READ; end
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
                end else begin token <= token + 1'b1; state <= KEY_READ; end
                DIV_START: if (component == output_index) state <= DIV_WAIT;
                DIV_WAIT: if (div_done) state <= OUTPUT_WAIT;
                OUTPUT_WAIT: if (out_ready) begin
                    if (output_index == 3) state <= COMPLETE;
                    else begin output_index <= output_index + 1'b1; state <= DIV_START; end
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
