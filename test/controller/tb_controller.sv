`timescale 1ns/1ps
module tb_controller;
    logic clk = 0;
    always #5 clk = ~clk;
    logic rst_n = 0, start = 0;
    logic [4:0] token_count = 0;
    logic [15:0] query_packed = 0;
    wire start_ready, busy, done;
    wire mem_req_valid, mem_write;
    logic mem_req_ready = 0, mem_rsp_valid = 0;
    wire [15:0] mem_addr;
    wire [7:0] mem_wdata;
    logic [7:0] mem_rdata = 0;
    wire exp_start, div_start, out_valid;
    wire signed [9:0] exp_max, exp_score;
    logic exp_done = 0, div_done = 0, out_ready = 0;
    logic [7:0] exp_weight = 0;
    wire signed [15:0] div_sum;
    wire [11:0] div_denominator;
    logic signed [7:0] div_result = 0;
    wire signed [7:0] out_data;
    attention_controller dut (.*);

    logic [7:0] memory [0:255];
    int reads [0:255], writes [0:255];
    int expected [0:3], scores [0:15], weights [0:15];
    int received = 0, exp_calls = 0, div_calls = 0;
    int mem_delay = -1, exp_delay = -1, div_delay = -1;
    logic pending_write;
    logic [15:0] pending_addr;
    logic [7:0] pending_data;
    int exp_answer, div_answer;
    logic signed [9:0] held_max, held_score;
    logic signed [15:0] held_sum;
    logic [11:0] held_denominator;
    bit request_stalled = 0, output_stalled = 0;
    logic [24:0] held_request;
    logic [7:0] held_output;

    // Behavioral exponent/divider stand-ins, NOT synthesizable implementations.
    function automatic int exponent(input int m, s);
        int lut [0:15] = '{255,244,234,224,214,205,197,188,180,173,165,158,152,145,139,133};
        int a, shift, value;
        a = 23 * (m-s);
        shift = a >> 5;
        value = lut[(a >> 1) & 15];
        if (shift == 0) return value;
        if (shift > 8) return 0;
        return (value + (1 << (shift-1))) >> shift;
    endfunction
    function automatic int divide(input int s, d);
        int magnitude, quotient, remainder_value;
        assert (d > 0) else $fatal(1, "Zero denominator");
        magnitude = 16 * (s < 0 ? -s : s);
        quotient = magnitude / d;
        remainder_value = magnitude % d;
        if (2 * remainder_value >= d) quotient++;
        return s < 0 ? -quotient : quotient;
    endfunction

    // Randomized request backpressure, memory latency, arithmetic latency and output stalls.
    always @(negedge clk) begin
        mem_req_ready = rst_n && mem_delay < 0 && $urandom_range(0,3) != 0;
        out_ready = rst_n && $urandom_range(0,3) == 0;
    end
    always @(posedge clk) begin
        if (!rst_n) begin
            mem_rsp_valid <= 0; exp_done <= 0; div_done <= 0;
            mem_delay = -1; exp_delay = -1; div_delay = -1;
            received = 0; exp_calls = 0; div_calls = 0;
            request_stalled = 0; output_stalled = 0;
        end else begin
            if (request_stalled) begin
                assert (mem_req_valid && {mem_write,mem_addr,mem_wdata} == held_request)
                    else $fatal(1, "Memory request changed under backpressure");
            end
            request_stalled = mem_req_valid && !mem_req_ready;
            held_request = {mem_write,mem_addr,mem_wdata};
            if (output_stalled) begin
                assert (out_valid && out_data == held_output)
                    else $fatal(1, "Output changed under backpressure");
            end
            output_stalled = out_valid && !out_ready;
            held_output = out_data;
            mem_rsp_valid <= 0;
            if (mem_delay == 0) begin
                if (pending_write) begin
                    memory[pending_addr[7:0]] = pending_data;
                    writes[pending_addr[7:0]]++;
                end else begin
                    mem_rdata <= memory[pending_addr[7:0]];
                    reads[pending_addr[7:0]]++;
                end
                mem_rsp_valid <= 1;
                mem_delay = -1;
            end else if (mem_delay > 0) mem_delay--;
            if (mem_req_valid && mem_req_ready) begin
                assert (mem_delay < 0 && mem_addr < 112) else $fatal(1, "Bad memory request");
                pending_write = mem_write;
                pending_addr = mem_addr;
                pending_data = mem_wdata;
                mem_delay = int'($urandom_range(1,7));
            end
            exp_done <= 0;
            if (exp_delay >= 0) begin
                assert (exp_max == held_max && exp_score == held_score)
                    else $fatal(1, "Exponent operands changed while waiting");
                if (exp_delay == 0) begin exp_weight <= 8'(exp_answer); exp_done <= 1; end
                exp_delay--;
            end
            if (exp_start) begin
                assert (exp_delay < 0 && exp_max >= exp_score) else $fatal(1, "Bad exponent start");
                exp_answer = exponent(int'(exp_max), int'(exp_score));
                held_max = exp_max; held_score = exp_score;
                exp_delay = int'($urandom_range(1,5)); exp_calls++;
            end
            div_done <= 0;
            if (div_delay >= 0) begin
                assert (div_sum == held_sum && div_denominator == held_denominator)
                    else $fatal(1, "Divider operands changed while waiting");
                if (div_delay == 0) begin div_result <= 8'(div_answer); div_done <= 1; end
                div_delay--;
            end
            if (div_start) begin
                assert (div_delay < 0) else $fatal(1, "Repeated divider start");
                div_answer = divide(int'(div_sum), int'(div_denominator));
                held_sum = div_sum; held_denominator = div_denominator;
                div_delay = int'($urandom_range(1,23)); div_calls++;
            end
            if (out_valid && out_ready) begin
                assert (received < 4 && out_data == 8'(expected[received]))
                    else $fatal(1, "Output %0d got %0d expected code %0d", received, out_data, expected[received]);
                received++;
            end
        end
    end

    task automatic reset_core;
        @(negedge clk); rst_n = 0; start = 0;
        repeat (3) @(negedge clk);
        rst_n = 1;
    endtask
    task automatic launch;
        @(negedge clk);
        assert (start_ready) else $fatal(1, "Not ready to start");
        start = 1;
        @(negedge clk); start = 0;
    endtask
    task automatic scan(input int fd, output int value);
        assert ($fscanf(fd, "%d", value) == 1) else $fatal(1, "Truncated vectors");
    endtask

    string vector_path;
    int fd, count, qword, value, cases = 0, ticks;
    initial begin
        assert ($value$plusargs("VECTORS=%s", vector_path)) else $fatal(1, "Missing vectors");
        fd = $fopen(vector_path, "r");
        assert (fd != 0) else $fatal(1, "Cannot open vectors");
        reset_core();
        // Invalid N must not start a transaction.
        foreach (memory[i]) memory[i] = 0;
        token_count = 0; start = 1;
        repeat (3) @(negedge clk);
        assert (!busy && !start_ready) else $fatal(1, "Accepted N=0");
        token_count = 17;
        repeat (3) @(negedge clk);
        assert (!busy && !start_ready) else $fatal(1, "Accepted N=17");
        start = 0;
        // Abort in memory wait, exponent wait, divider wait and output wait.
        // Reset cancels all pending model-engine activity as required by contract.
        token_count = 1; query_packed = 0;
        for (int phase = 0; phase < 4; phase++) begin
            launch();
            case (phase)
                0: wait (mem_delay > 0);
                1: wait (exp_delay > 0);
                2: wait (div_delay > 0);
                3: wait (out_valid);
            endcase
            reset_core();
            assert (!busy && !done && !out_valid) else $fatal(1, "Reset did not abort");
        end
        while ($fscanf(fd, "%d", count) == 1) begin
            scan(fd, qword);
            @(negedge clk);
            token_count = 5'(count); query_packed = 16'(qword);
            foreach (memory[i]) begin memory[i] = 8'ha5; reads[i] = 0; writes[i] = 0; end
            for (int i = 0; i < 2*count; i++) begin scan(fd, value); memory[i] = 8'(value); end
            for (int i = 0; i < 2*count; i++) begin scan(fd, value); memory[32+i] = 8'(value); end
            for (int i = 0; i < 4; i++) scan(fd, expected[i]);
            for (int i = 0; i < count; i++) scan(fd, scores[i]);
            for (int i = 0; i < count; i++) scan(fd, weights[i]);
            received = 0; exp_calls = 0; div_calls = 0;
            launch();
            // Mutating live config and pulsing start while busy must not alter the transaction.
            query_packed = ~query_packed; token_count = 0; start = 1;
            repeat (2) @(negedge clk);
            start = 0;
            ticks = 0;
            while (!done && ticks < 20000) begin @(negedge clk); ticks++; end
            assert (done && !busy && received == 4 && exp_calls == count && div_calls == 4)
                else $fatal(1, "Transaction incomplete: case %0d", cases);
            for (int i = 0; i < 256; i++) begin
                assert (reads[i] == ((i < 2*count || (i >= 32 && i < 32+2*count) ||
                        (i >= 64 && i < 64+2*count) || (i >= 96 && i < 96+count)) ? 1 : 0))
                    else $fatal(1, "Read count wrong at %0d", i);
                assert (writes[i] == (((i >= 64 && i < 64+2*count) || (i >= 96 && i < 96+count)) ? 1 : 0))
                    else $fatal(1, "Write count wrong at %0d", i);
            end
            for (int i = 0; i < count; i++) begin
                assert ({memory[65+2*i],memory[64+2*i]} == 16'(scores[i])) else $fatal(1, "Saved score mismatch");
                assert (memory[96+i] == 8'(weights[i])) else $fatal(1, "Saved weight mismatch");
            end
            repeat (3) @(negedge clk);
            assert (done && !out_valid) else $fatal(1, "Done not sticky or extra output");
            cases++;
        end
        $display("PASS: %0d Python-reference cases; saved scores/weights, one K pass, stalls, invalid N, reset and back-to-back checks", cases);
        $finish;
    end
    initial begin #100000000; $fatal(1, "Global timeout"); end
endmodule
