`default_nettype none

// Two-pass INT4 core: first find the maximum, then recompute scores and accumulate.
// K is read twice and V once; no scores or weights are written to external memory.
// Memory, exponent and divider are external engines.
// All resets are synchronous. Reset the attached engines at the same time.
module attention_controller #(
    parameter logic [15:0] K_BASE = 16'h0000, // 2 bytes per token (4 INT4 components), max 16 tokens -> 32 bytes
    parameter logic [15:0] V_BASE = 16'h0020 // 2 bytes per token (4 INT4 components), max 16 tokens -> 32 bytes
) (
    // Clock and reset
    input wire clk,
    input wire rst_n,

    // Start and configuration
    input wire start,                 // Request a transaction; accepted when start && start_ready.
    input wire [4:0] token_count,     // Number of tokens (K/V rows): 1–16. Captured when start is accepted.
    input wire [15:0] query_packed,   // Four signed INT4 Q components: Q0=[3:0], Q1=[7:4], Q2=[11:8], Q3=[15:12]. Captured when start is accepted.
    output wire start_ready,         // High when idle, reset released, and token_count is valid.
    output wire busy,                // High when processing
    output logic done,               // Sticky flag: all four outputs accepted. Cleared on start/reset.

    // Byte-memory interface: one outstanding request at a time.
    // A request is accepted on a rising edge when mem_req_valid && mem_req_ready.
    output wire mem_req_valid,       // Controller is requesting memory.
    input wire mem_req_ready,        // Memory adapter can accept the request.
    output wire mem_write,           // Always 0: this core only reads memory. Kept for adapter compatibility.
    output logic [15:0] mem_addr,     // Byte address; held stable until request acceptance.
    output wire [7:0] mem_wdata,      // Always 0: no write data is used by this core.
    input wire mem_rsp_valid,        // Completion of the accepted read, in a later cycle.
    input wire [7:0] mem_rdata,       // Returned read byte; valid with mem_rsp_valid.

    // Exponent LUT: approximate weight = 255 * exp((score - maximum) / 2).
    output wire exp_start,           // One-cycle pulse to start calculating the current token's weight.
    output wire signed [9:0] exp_max,   // Final maximum score across all tokens.
    output wire signed [9:0] exp_score, // Current token's score; operands stay stable while waiting.
    input wire exp_done,             // Calculation complete; exp_weight is valid in this cycle.
    input wire [7:0] exp_weight,      // Unsigned LUT-generated attention weight: 0–255.

    // Divider engine: result = round(16 * weighted_sum / weight_sum).
    output wire div_start,           // One-cycle pulse to start normalizing one output component.
    output logic signed [15:0] div_sum, // Weighted sum O_i = sum(W_j * V_j,i).
    output wire [11:0] div_denominator, // Weight sum L = sum(W_j); positive for a valid transaction.
    input wire div_done,             // Division complete; div_result is valid in this cycle.
    input wire signed [7:0] div_result, // Rounded signed result code; actual value = code / 16.

    // Output interface: components are sent in order 0, 1, 2, 3.
    // A byte transfers on a rising edge when out_valid && out_ready.
    output wire out_valid,           // A completed output byte is available.
    input wire out_ready,            // Receiver can accept the current output byte.
    output logic signed [7:0] out_data // Signed result code; held stable while valid and not ready.
);
    typedef enum logic [4:0] {
        IDLE, INIT, KEY0, KEY1, KEY_READY, SCORE_CLEAR, SCORE_MAC,
        SCORE_CAPTURE, KEY_NEXT, ACCUM_CLEAR, EXP_START, EXP_WAIT,
        VALUE0, VALUE1, VALUE_READY, ACCUM_STEP, VALUE_NEXT,
        DIV_START, DIV_WAIT, OUTPUT_WAIT, COMPLETE, MEM_REQUEST, MEM_WAIT
    } state_t;
    state_t state, return_state;
    logic [4:0] n;
    logic [3:0] token;
    logic second_pass; // 0: find maximum. 1: use the frozen maximum and accumulate.
    logic [1:0] component, output_index;
    logic [15:0] query, operands;
    logic [7:0] read_byte, weight;
    logic signed [9:0] current_score; // Only the current token, held for the exponent engine.
    wire signed [9:0] score, maximum;
    wire signed [15:0] o0, o1, o2, o3;
    wire [15:0] row_offset = {11'b0, token, 1'b0};
    wire signed [3:0] qi = $signed(query[4*component +: 4]);
    wire signed [3:0] ki = $signed(operands[4*component +: 4]);

    assign start_ready = rst_n && state == IDLE && token_count >= 1 && token_count <= 16;
    assign busy = state != IDLE;
    assign mem_req_valid = rst_n && state == MEM_REQUEST;
    assign mem_write = 1'b0;
    assign mem_wdata = 8'd0;
    assign exp_start = rst_n && state == EXP_START;
    assign exp_max = maximum;
    assign exp_score = current_score;
    assign div_start = rst_n && state == DIV_START;
    assign out_valid = rst_n && state == OUTPUT_WAIT;

    score_mac score_unit (
        .clk(clk), .rst_n(rst_n), .clear(state == INIT || state == SCORE_CLEAR),
        .en(state == SCORE_MAC), .qi(qi), .ki(ki), .S(score)
    );
    max_reg max_unit (
        .clk(clk), .rst_n(rst_n), .clear(state == INIT),
        .en(state == SCORE_CAPTURE && !second_pass), .S_in(score), .M(maximum)
    );
    accum accum_unit (
        .clk(clk), .rst_n(rst_n), .clear(state == INIT || state == ACCUM_CLEAR),
        .en(state == ACCUM_STEP), .W(weight),
        .v0($signed(operands[3:0])), .v1($signed(operands[7:4])),
        .v2($signed(operands[11:8])), .v3($signed(operands[15:12])),
        .L(div_denominator), .O0(o0), .O1(o1), .O2(o2), .O3(o3)
    );
    always_comb begin
        case (output_index)
            0: div_sum = o0;
            1: div_sum = o1;
            2: div_sum = o2;
            default: div_sum = o3;
        endcase
    end

    // Launch one byte read; address remains registered until the next request.
    task automatic read_byte_request(input logic [15:0] addr, input state_t next_state);
        mem_addr <= addr;
        return_state <= next_state;
        state <= MEM_REQUEST;
    endtask

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state <= IDLE;
            return_state <= IDLE;
            n <= 0;
            token <= 0;
            second_pass <= 0;
            component <= 0;
            output_index <= 0;
            query <= 0;
            operands <= 0;
            read_byte <= 0;
            current_score <= 0;
            weight <= 0;
            done <= 0;
            out_data <= 0;
            mem_addr <= 0;
        end else begin
            case (state)
                IDLE: if (start && start_ready) begin
                    query <= query_packed;
                    n <= token_count;
                    token <= 0;
                    second_pass <= 0;
                    done <= 0;
                    state <= INIT;
                end
                INIT: state <= KEY0;
                KEY0: read_byte_request(K_BASE + row_offset, KEY1);
                KEY1: begin
                    operands[7:0] <= read_byte;
                    read_byte_request(K_BASE + row_offset + 16'd1, KEY_READY);
                end
                KEY_READY: begin operands[15:8] <= read_byte; state <= SCORE_CLEAR; end
                SCORE_CLEAR: begin component <= 0; state <= SCORE_MAC; end
                SCORE_MAC: if (component == 3) state <= SCORE_CAPTURE;
                           else component <= component + 1'b1;
                // Capture on the edge AFTER the final MAC updates S.
                SCORE_CAPTURE: begin
                    if (second_pass) begin
                        current_score <= score;
                        state <= EXP_START;
                    end else state <= KEY_NEXT;
                end
                KEY_NEXT: if ({1'b0, token} == n - 5'd1) begin
                    token <= 0;
                    second_pass <= 1;
                    state <= ACCUM_CLEAR;
                end else begin token <= token + 1'b1; state <= KEY0; end
                // Clear once at the pass boundary, never between pass-2 tokens.
                ACCUM_CLEAR: state <= KEY0;
                EXP_START: state <= EXP_WAIT;
                EXP_WAIT: if (exp_done) begin weight <= exp_weight; state <= VALUE0; end
                // Hold W locally while the shared operand buffer is refilled with V.
                VALUE0: read_byte_request(V_BASE + row_offset, VALUE1);
                VALUE1: begin
                    operands[7:0] <= read_byte;
                    read_byte_request(V_BASE + row_offset + 16'd1, VALUE_READY);
                end
                VALUE_READY: begin operands[15:8] <= read_byte; state <= ACCUM_STEP; end
                ACCUM_STEP: state <= VALUE_NEXT;
                VALUE_NEXT: if ({1'b0, token} == n - 5'd1) begin
                    output_index <= 0; state <= DIV_START;
                end else begin token <= token + 1'b1; state <= KEY0; end
                DIV_START: state <= DIV_WAIT;
                DIV_WAIT: if (div_done) begin out_data <= div_result; state <= OUTPUT_WAIT; end
                OUTPUT_WAIT: if (out_ready) begin
                    if (output_index == 3) state <= COMPLETE;
                    else begin output_index <= output_index + 1'b1; state <= DIV_START; end
                end
                COMPLETE: begin done <= 1; state <= IDLE; end
                MEM_REQUEST: if (mem_req_ready) state <= MEM_WAIT;
                MEM_WAIT: if (mem_rsp_valid) begin read_byte <= mem_rdata; state <= return_state; end
                default: state <= IDLE;
            endcase
        end
    end
endmodule

`default_nettype wire
