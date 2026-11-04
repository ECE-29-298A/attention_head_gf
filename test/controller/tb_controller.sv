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
    int expected_max, expected_l, expected_o [0:3];
    int captures = 0, mac_cycles = 0, max_updates = 0, accum_updates = 0;
    int memory_cycles = 0;
    bit legacy = 0, check_case = 0, compare_accum = 0;
    int running_l = 0, running_o [0:3];
    int total_cycles = 0, n16_cycles = 0, n16_cases = 0, transaction_cycles = 0;
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

    // Real exponent LUT rides along with the behavioral stand-in and must agree with it
    // on every weight the controller asks for.
    wire lut_done;
    wire [7:0] lut_weight;
    int lut_checks = 0;
    exp_lut lut (.clk(clk), .rst_n(rst_n), .start(exp_start), .M(exp_max), .S(exp_score),
                 .done(lut_done), .W(lut_weight));
    always @(negedge clk) if (rst_n && lut_done) begin
        assert (lut_weight == 8'(exp_answer))
            else $fatal(1, "exp_lut gave %0d, model %0d (M=%0d S=%0d)", lut_weight, exp_answer, held_max, held_score);
        lut_checks++;
    end

    // Behavioral exponent/divider stand-ins, NOT synthesizable implementations.
    // Weight = round(255 * e^(-D/2)), D = m - s; 0 once D >= 13 (matches Python EXP_TABLE).
    function automatic int exponent(input int m, s);
        int lut [0:12] = '{255,155,94,57,35,21,13,8,5,3,2,1,1};
        int d;
        d = m - s;
        if (d >= 13) return 0;
        return lut[d];
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

    function automatic int signed_nibble(input logic [3:0] value);
        return int'($signed(value));
    endfunction

    // By default randomize all delays. Fixed mode measures the same latency for
    // both versions: MEM_CYCLES counts accepted request edge to sampled response.
    always @(negedge clk) begin
        mem_req_ready = rst_n && mem_delay < 0 && (memory_cycles > 0 || $urandom_range(0,3) != 0);
        out_ready = rst_n && (memory_cycles > 0 || $urandom_range(0,3) == 0);
    end
    always @(posedge clk) begin
        if (!rst_n) begin
            mem_rsp_valid <= 0; exp_done <= 0; div_done <= 0;
            mem_delay = -1; exp_delay = -1; div_delay = -1;
            received = 0; exp_calls = 0; div_calls = 0;
            request_stalled = 0; output_stalled = 0;
            captures = 0; mac_cycles = 0; max_updates = 0; accum_updates = 0;
            compare_accum = 0; running_l = 0;
            foreach (running_o[i]) running_o[i] = 0;
        end else begin
            if (!legacy) assert (!mem_write && mem_wdata == 0)
                else $fatal(1, "Two-pass core must never write memory");
            if (check_case) begin
                if (busy || (start && start_ready)) transaction_cycles++;
                if (dut.score_unit.en) mac_cycles++;
                if (dut.state == dut.SCORE_CAPTURE) begin
                    assert (captures < (legacy ? count : 2*count) &&
                            dut.score == 10'(scores[captures % count]))
                        else $fatal(1, "Dot-product mismatch at capture %0d", captures);
                    captures++;
                end
                if (dut.max_unit.en) begin
                    assert (max_updates < count) else $fatal(1, "Maximum updated after pass 1");
                    max_updates++;
                end
                if (compare_accum) begin
                    assert (div_denominator == 12'(running_l) && dut.o0 == 16'(running_o[0]) &&
                            dut.o1 == 16'(running_o[1]) && dut.o2 == 16'(running_o[2]) && dut.o3 == 16'(running_o[3]))
                        else $fatal(1, "Running sums changed incorrectly");
                end
                if (dut.accum_unit.en) begin
                    assert (accum_updates < count && exp_calls == (legacy ? count : accum_updates+1) &&
                            dut.weight == 8'(weights[accum_updates]))
                        else $fatal(1, "Incorrect weight or accumulation schedule");
                    running_l += weights[accum_updates];
                    for (int c = 0; c < 4; c++)
                        running_o[c] += weights[accum_updates] *
                            signed_nibble(4'(memory[32+2*accum_updates+c/2] >> (4*(c%2))));
                    compare_accum = 1;
                    accum_updates++;
                end
            end
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
                assert (mem_delay < 0 && mem_addr < (legacy ? 112 : 64)) else $fatal(1, "Bad memory request");
                if (check_case && !legacy) begin
                    // Entire first key pass precedes the first exponential; each
                    // pass-2 K row then precedes its corresponding V row.
                    if (mem_addr < 32) begin
                        assert (int'(mem_addr) < 2*count && reads[mem_addr[7:0]] < 2)
                            else $fatal(1, "Out-of-range or repeated K read");
                        if (reads[mem_addr[7:0]] == 0)
                            assert (max_updates == int'(mem_addr)/2 && accum_updates == 0 && exp_calls == 0)
                                else $fatal(1, "Incorrect pass-1 read schedule");
                        else assert (max_updates == count && accum_updates == int'(mem_addr)/2)
                            else $fatal(1, "Incorrect pass-2 read schedule");
                    end else begin
                        assert (int'(mem_addr) < 32+2*count && exp_calls == (int'(mem_addr)-32)/2+1)
                            else $fatal(1, "V read before corresponding weight");
                    end
                end
                pending_write = mem_write;
                pending_addr = mem_addr;
                pending_data = mem_wdata;
                mem_delay = memory_cycles > 0 ? memory_cycles-2 : int'($urandom_range(0,7));
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
                if (check_case) begin
                    assert (exp_calls < count && max_updates == count && exp_max == 10'(expected_max) &&
                            exp_score == 10'(scores[exp_calls]) && exp_answer == weights[exp_calls])
                        else $fatal(1, "Exponent operands or result mismatch");
                end
                held_max = exp_max; held_score = exp_score;
                exp_delay = memory_cycles > 0 ? 1 : int'($urandom_range(0,5)); exp_calls++;
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
                if (check_case) begin
                    assert (div_calls < 4 && accum_updates == count &&
                            div_sum == 16'(expected_o[div_calls]) && div_denominator == 12'(expected_l))
                        else $fatal(1, "Final numerator/denominator mismatch");
                end
                div_answer = divide(int'(div_sum), int'(div_denominator));
                held_sum = div_sum; held_denominator = div_denominator;
                div_delay = memory_cycles > 0 ? 19 : int'($urandom_range(0,23)); div_calls++;
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
        legacy = $test$plusargs("LEGACY");
        if ($value$plusargs("MEM_CYCLES=%d", memory_cycles))
            assert (memory_cycles >= 2 && memory_cycles <= 100) else $fatal(1, "MEM_CYCLES must be 2..100");
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
        // Abort in both K passes, exponent wait, V fetch, divider and output.
        // Reset cancels all pending model-engine activity as required by contract.
        token_count = 1; query_packed = 0;
        for (int phase = 0; phase < 6; phase++) begin
            foreach (reads[i]) reads[i] = 0;
            launch();
            case (phase)
                0: wait (mem_delay >= 0);
                1: if (!legacy) wait (mem_delay >= 0 && pending_addr == 0 && reads[0] == 1);
                   else wait (mem_delay >= 0 && pending_addr == 64);
                2: wait (exp_delay >= 0);
                3: wait (mem_delay >= 0 && pending_addr == 32);
                4: wait (div_delay >= 0);
                5: wait (out_valid);
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
            expected_max = -224; expected_l = 0;
            foreach (expected_o[i]) expected_o[i] = 0;
            for (int i = 0; i < count; i++) begin
                if (int'($signed(16'(scores[i]))) > expected_max) expected_max = int'($signed(16'(scores[i])));
                expected_l += weights[i];
                for (int c = 0; c < 4; c++) expected_o[c] += weights[i] *
                    signed_nibble(4'(memory[32+2*i+c/2] >> (4*(c%2))));
            end
            received = 0; exp_calls = 0; div_calls = 0;
            captures = 0; mac_cycles = 0; max_updates = 0; accum_updates = 0;
            compare_accum = 0; running_l = 0; transaction_cycles = 0;
            foreach (running_o[i]) running_o[i] = 0;
            check_case = 1;
            launch();
            // Mutating live config and pulsing start while busy must not alter the transaction.
            query_packed = ~query_packed; token_count = 0; start = 1;
            repeat (2) @(negedge clk);
            start = 0;
            ticks = 0;
            while (!done && ticks < 20000) begin @(negedge clk); ticks++; end
            assert (done && !busy && received == 4 && exp_calls == count && div_calls == 4)
                else $fatal(1, "Transaction incomplete: case %0d", cases);
            assert (captures == (legacy ? count : 2*count) && mac_cycles == (legacy ? 4*count : 8*count) &&
                    max_updates == count && accum_updates == count)
                else $fatal(1, "Arithmetic operation count mismatch");
            for (int i = 0; i < 256; i++) begin
                if (legacy) begin
                    assert (reads[i] == ((i < 2*count || (i >= 32 && i < 32+2*count) ||
                            (i >= 64 && i < 64+2*count) || (i >= 96 && i < 96+count)) ? 1 : 0))
                        else $fatal(1, "Legacy read count wrong at %0d", i);
                    assert (writes[i] == (((i >= 64 && i < 64+2*count) || (i >= 96 && i < 96+count)) ? 1 : 0))
                        else $fatal(1, "Legacy write count wrong at %0d", i);
                end else begin
                    assert (reads[i] == (i < 2*count ? 2 : ((i >= 32 && i < 32+2*count) ? 1 : 0)))
                        else $fatal(1, "Two-pass read count wrong at %0d", i);
                    assert (writes[i] == 0) else $fatal(1, "Unexpected write at %0d", i);
                end
            end
            if (legacy) for (int i = 0; i < count; i++) begin
                assert ({memory[65+2*i],memory[64+2*i]} == 16'(scores[i])) else $fatal(1, "Saved score mismatch");
                assert (memory[96+i] == 8'(weights[i])) else $fatal(1, "Saved weight mismatch");
            end
            repeat (3) @(negedge clk);
            assert (done && !out_valid) else $fatal(1, "Done not sticky or extra output");
            check_case = 0;
            total_cycles += transaction_cycles;
            if (count == 16) begin n16_cycles += transaction_cycles; n16_cases++; end
            cases++;
        end
        assert (lut_checks > 0) else $fatal(1, "exp_lut was never exercised");
        $display("exp_lut matched the model on %0d controller requests", lut_checks);
        $display("PASS: %0d Python-reference cases; legacy=%0d, memory_cycles=%0d; intermediate arithmetic, memory counts, stalls, invalid N, reset and back-to-back checks", cases, legacy, memory_cycles);
        $display("METRICS total_cycles=%0d n16_cycles=%0d n16_cases=%0d", total_cycles, n16_cycles, n16_cases);
        $finish;
    end
    initial begin #100000000; $fatal(1, "Global timeout"); end
endmodule
