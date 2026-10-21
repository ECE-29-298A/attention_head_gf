`default_nettype none

// INT4 sequencing core. Memory, exponent and divider are external engines.
// All resets are synchronous. Reset the attached engines at the same time.
module attention_controller #(
    parameter logic [15:0] K_BASE = 16'h0000, // 2 bytes per token (4 INT4 components), max 16 tokens -> 32 bytes
    parameter logic [15:0] V_BASE = 16'h0020, // 2 bytes per token (4 INT4 components), max 16 tokens -> 32 bytes
    parameter logic [15:0] SCORE_BASE = 16'h0040, // S = q * k_j, 2 bytes per token (10 bit max), max 16 tokens -> 32 bytes
    parameter logic [15:0] WEIGHT_BASE = 16'h0060 // 1 byte per token (8 bit max), max 16 tokens -> 16 bytes
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
    output logic mem_write,          // Request type: 1 = write, 0 = read.
    output logic [15:0] mem_addr,     // Byte address; held stable until request acceptance.
    output logic [7:0] mem_wdata,     // Byte to write; held stable until acceptance.
    input wire mem_rsp_valid,        // Completion of the accepted read OR write, in a later cycle.
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
        SCORE_CAPTURE, SCORE_WRITE0, SCORE_WRITE1, KEY_NEXT,
        SCORE_READ0, SCORE_READ1, SCORE_READY, EXP_START, EXP_WAIT,
        WEIGHT_WRITE, WEIGHT_NEXT, ACCUM_CLEAR, WEIGHT_READ,
        VALUE0, VALUE1, VALUE_READY, ACCUM_STEP, VALUE_NEXT,
        DIV_START, DIV_WAIT, OUTPUT_WAIT, COMPLETE, MEM_REQUEST, MEM_WAIT
    } state_t;
    state_t state, return_state;
    logic [4:0] n;
    logic [3:0] token;
    logic [1:0] component, output_index;
    logic [15:0] query, operands;
    logic [7:0] read_byte, score_low, weight;
    logic signed [9:0] saved_score;
    wire signed [9:0] score, maximum;
    wire signed [15:0] o0, o1, o2, o3;
    wire [15:0] row_offset = {11'b0, token, 1'b0};
    wire [15:0] weight_offset = {12'b0, token};
    wire signed [3:0] qi = $signed(query[4*component +: 4]);
    wire signed [3:0] ki = $signed(operands[4*component +: 4]);

    assign start_ready = rst_n && state == IDLE && token_count >= 1 && token_count <= 16;
    assign busy = state != IDLE;
    assign mem_req_valid = rst_n && state == MEM_REQUEST;
    assign exp_start = rst_n && state == EXP_START;
    assign exp_max = maximum;
    assign exp_score = saved_score;
    assign div_start = rst_n && state == DIV_START;
    assign out_valid = rst_n && state == OUTPUT_WAIT;

    score_mac score_unit (
        .clk(clk), .rst_n(rst_n), .clear(state == INIT || state == SCORE_CLEAR),
        .en(state == SCORE_MAC), .qi(qi), .ki(ki), .S(score)
    );
    max_reg max_unit (
        .clk(clk), .rst_n(rst_n), .clear(state == INIT),
        .en(state == SCORE_CAPTURE), .S_in(score), .M(maximum)
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

    // Launch one byte operation; fields remain registered until the next request.
    task automatic request_byte(input logic wr, input logic [15:0] addr,
                                input logic [7:0] data, input state_t next_state);
        mem_write <= wr;
        mem_addr <= addr;
        mem_wdata <= data;
        return_state <= next_state;
        state <= MEM_REQUEST;
    endtask

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state <= IDLE;
            return_state <= IDLE;
            n <= 0;
            token <= 0;
            component <= 0;
            output_index <= 0;
            query <= 0;
            operands <= 0;
            read_byte <= 0;
            score_low <= 0;
            saved_score <= 0;
            weight <= 0;
            done <= 0;
            out_data <= 0;
            mem_write <= 0;
            mem_addr <= 0;
            mem_wdata <= 0;
        end else begin
            case (state)
                IDLE: if (start && start_ready) begin
                    query <= query_packed;
                    n <= token_count;
                    token <= 0;
                    done <= 0;
                    state <= INIT;
                end
                INIT: state <= KEY0;
                KEY0: request_byte(0, K_BASE + row_offset, 0, KEY1);
                KEY1: begin
                    operands[7:0] <= read_byte;
                    request_byte(0, K_BASE + row_offset + 16'd1, 0, KEY_READY);
                end
                KEY_READY: begin operands[15:8] <= read_byte; state <= SCORE_CLEAR; end
                SCORE_CLEAR: begin component <= 0; state <= SCORE_MAC; end
                SCORE_MAC: if (component == 3) state <= SCORE_CAPTURE;
                           else component <= component + 1'b1;
                // Capture on the edge AFTER the final MAC updates S.
                SCORE_CAPTURE: begin saved_score <= score; state <= SCORE_WRITE0; end
                SCORE_WRITE0: request_byte(1, SCORE_BASE + row_offset, saved_score[7:0], SCORE_WRITE1);
                SCORE_WRITE1: request_byte(1, SCORE_BASE + row_offset + 16'd1,
                                          {{6{saved_score[9]}}, saved_score[9:8]}, KEY_NEXT);
                KEY_NEXT: if ({1'b0, token} == n - 5'd1) begin
                    token <= 0; state <= SCORE_READ0;
                end else begin token <= token + 1'b1; state <= KEY0; end
                SCORE_READ0: request_byte(0, SCORE_BASE + row_offset, 0, SCORE_READ1);
                SCORE_READ1: begin
                    score_low <= read_byte;
                    request_byte(0, SCORE_BASE + row_offset + 16'd1, 0, SCORE_READY);
                end
                SCORE_READY: begin saved_score <= $signed({read_byte[1:0], score_low}); state <= EXP_START; end
                EXP_START: state <= EXP_WAIT;
                EXP_WAIT: if (exp_done) begin weight <= exp_weight; state <= WEIGHT_WRITE; end
                WEIGHT_WRITE: request_byte(1, WEIGHT_BASE + weight_offset, weight, WEIGHT_NEXT);
                WEIGHT_NEXT: if ({1'b0, token} == n - 5'd1) begin
                    token <= 0; state <= ACCUM_CLEAR;
                end else begin token <= token + 1'b1; state <= SCORE_READ0; end
                ACCUM_CLEAR: state <= WEIGHT_READ;
                WEIGHT_READ: request_byte(0, WEIGHT_BASE + weight_offset, 0, VALUE0);
                VALUE0: begin weight <= read_byte; request_byte(0, V_BASE + row_offset, 0, VALUE1); end
                VALUE1: begin
                    operands[7:0] <= read_byte;
                    request_byte(0, V_BASE + row_offset + 16'd1, 0, VALUE_READY);
                end
                VALUE_READY: begin operands[15:8] <= read_byte; state <= ACCUM_STEP; end
                ACCUM_STEP: state <= VALUE_NEXT;
                VALUE_NEXT: if ({1'b0, token} == n - 5'd1) begin
                    output_index <= 0; state <= DIV_START;
                end else begin token <= token + 1'b1; state <= WEIGHT_READ; end
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
