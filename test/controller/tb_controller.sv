`timescale 1ns/1ps
module tb_controller #(
    parameter logic [15:0] TEST_K_BASE = 16'h0000,
    parameter logic [15:0] TEST_V_BASE = 16'h0020
);
    logic clk = 0;
    always #5 clk = ~clk;
    logic rst_n = 0, start = 0;
    logic [4:0] token_count = 0;
    logic [15:0] query_packed = 0;
    wire start_ready, busy, done, mem_req_valid, mem_write, out_valid;
    wire [15:0] mem_addr;
    wire [7:0] mem_wdata;
    wire signed [7:0] out_data;
    logic mem_req_ready = 0, mem_rsp_valid = 0, out_ready = 0;
    logic [7:0] mem_rdata = 0;
    attention_controller #(.K_BASE(TEST_K_BASE), .V_BASE(TEST_V_BASE)) dut (.*);

    // The testbench supplies only a memory model and host signals. No arithmetic
    // result or completion signal is driven from the testbench into the controller.
    logic [7:0] memory [0:63];
    int reads [0:63];
    int mem_delay = -1, pending_slot = 0, memory_cycles = 0;
    bit force_output_stall = 0, active_case = 0;
    bit request_stalled = 0, output_stalled = 0, check_sums = 0;
    bit score_ready = 0;
    bit exp_pending = 0, div_pending = 0;
    logic signed [9:0] held_max, held_score;
    logic signed [15:0] held_sum;
    logic [11:0] held_denominator;
    logic [15:0] held_address;
    logic [7:0] held_output;
    int count, expected [0:3], scores [0:15], weights [0:15];
    int expected_max, expected_l, expected_o [0:3];
    int running_l = 0, running_o [0:3];
    int captures = 0, mac_cycles = 0, max_updates = 0, accum_updates = 0;
    int exp_calls = 0, exp_results = 0, div_calls = 0, div_results = 0, received = 0;
    int cycles = 0, total_cycles = 0, divide_start_cycle = 0;

    function automatic int memory_slot(input logic [15:0] address);
        if (int'(address) >= int'(TEST_K_BASE) && int'(address) < int'(TEST_K_BASE)+32)
            return int'(address)-int'(TEST_K_BASE);
        if (int'(address) >= int'(TEST_V_BASE) && int'(address) < int'(TEST_V_BASE)+32)
            return 32+int'(address)-int'(TEST_V_BASE);
        $fatal(1, "Out-of-map memory address %h", address);
        return 0;
    endfunction
    function automatic int value_component(input int token, component);
        return int'($signed(4'(memory[32+2*token+component/2] >> (4*(component%2)))));
    endfunction

    always @(negedge clk) begin
        mem_req_ready = rst_n && mem_delay < 0 && (memory_cycles > 0 || $urandom_range(0,3) != 0);
        out_ready = rst_n && !force_output_stall && (memory_cycles > 0 || $urandom_range(0,3) == 0);
    end
    always @(posedge clk) begin
        if (!rst_n) begin
            mem_rsp_valid <= 0; mem_delay = -1;
            request_stalled = 0; output_stalled = 0;
            exp_pending = 0; div_pending = 0;
        end else begin
            assert (!mem_write && mem_wdata == 0) else $fatal(1, "Core attempted a memory write");
            if (request_stalled)
                assert (mem_req_valid && mem_addr == held_address) else $fatal(1, "Unstable memory request");
            request_stalled = mem_req_valid && !mem_req_ready;
            held_address = mem_addr;
            if (output_stalled)
                assert (out_valid && out_data == held_output) else $fatal(1, "Unstable output");
            output_stalled = out_valid && !out_ready;
            held_output = out_data;
            mem_rsp_valid <= 0;
            if (mem_delay == 0) begin
                mem_rdata <= memory[pending_slot];
                reads[pending_slot]++;
                mem_rsp_valid <= 1;
                mem_delay = -1;
            end else if (mem_delay > 0) mem_delay--;
            if (mem_req_valid && mem_req_ready) begin
                assert (mem_delay < 0) else $fatal(1, "Overlapping requests");
                pending_slot = memory_slot(mem_addr);
                if (active_case) begin
                    if (pending_slot < 32) begin
                        assert (pending_slot < 2*count && reads[pending_slot] < 2)
                            else $fatal(1, "Invalid K access");
                        if (reads[pending_slot] == 0)
                            assert (max_updates == pending_slot/2 && exp_calls == 0 && accum_updates == 0)
                                else $fatal(1, "Pass 1 scheduled incorrectly");
                        else assert (max_updates == count && accum_updates == pending_slot/2)
                            else $fatal(1, "Pass 2 scheduled incorrectly");
                    end else
                        assert (pending_slot < 32+2*count && exp_results == (pending_slot-32)/2+1)
                            else $fatal(1, "V read before real LUT completion");
                end
                mem_delay = memory_cycles > 0 ? memory_cycles-2 : int'($urandom_range(0,7));
            end

            if (active_case) begin
                if (busy || (start && start_ready)) cycles++;
                if (max_updates == count)
                    assert (dut.exp_max == 10'(expected_max)) else $fatal(1, "Final max changed");
                if (dut.score_unit.en) mac_cycles++;
                // The completed score is consumed one edge after the fourth MAC.
                if (score_ready) begin
                    assert (captures < 2*count && dut.score == 10'(scores[captures % count]))
                        else $fatal(1, "Dot-product mismatch");
                    captures++;
                end
                score_ready = dut.score_unit.en && dut.component == 3;
                if (dut.max_unit.en) begin
                    assert (max_updates < count) else $fatal(1, "Max updated in pass 2");
                    max_updates++;
                end
                if (exp_pending)
                    assert (!dut.exp_start && dut.exp_max == held_max && dut.exp_score == held_score)
                        else $fatal(1, "Exponent operands changed or start repeated while waiting");
                if (dut.exp_start) begin
                    assert (exp_calls < count && max_updates == count && exp_calls == exp_results &&
                            dut.exp_score == 10'(scores[exp_calls])) else $fatal(1, "Bad exponent start");
                    exp_calls++;
                    held_max = dut.exp_max; held_score = dut.exp_score; exp_pending = 1;
                end
                if (dut.exp_done) begin
                    assert (exp_results < exp_calls && dut.exp_weight == 8'(weights[exp_results]))
                        else $fatal(1, "Real LUT result mismatch");
                    exp_results++;
                    exp_pending = 0;
                end
                if (check_sums)
                    assert (dut.div_denominator == 12'(running_l) &&
                            dut.o0 == 16'(running_o[0]) && dut.o1 == 16'(running_o[1]) &&
                            dut.o2 == 16'(running_o[2]) && dut.o3 == 16'(running_o[3]))
                        else $fatal(1, "Running sums mismatch");
                if (dut.accum_unit.en) begin
                    assert (accum_updates < count && exp_results == accum_updates+1 &&
                            dut.weight == 8'(weights[accum_updates])) else $fatal(1, "Bad accumulate");
                    running_l += weights[accum_updates];
                    for (int c = 0; c < 4; c++)
                        running_o[c] += weights[accum_updates] * value_component(accum_updates, c);
                    accum_updates++; check_sums = 1;
                end
                if (div_pending)
                    assert (!dut.div_start && dut.div_sum == held_sum && dut.div_denominator == held_denominator)
                        else $fatal(1, "Divider operands changed or start repeated while waiting");
                if (dut.div_start) begin
                    assert (!dut.div_busy && div_calls < 4 && accum_updates == count &&
                            dut.div_sum == 16'(expected_o[div_calls]) &&
                            dut.div_denominator == 12'(expected_l) && expected_l > 0)
                        else $fatal(1, "Bad divider request");
                    divide_start_cycle = cycles;
                    div_calls++;
                    held_sum = dut.div_sum; held_denominator = dut.div_denominator; div_pending = 1;
                end
                if (dut.div_done) begin
                    // Result registered 20 edges after start, sampled here on edge 21.
                    assert (div_results < div_calls && cycles-divide_start_cycle == 21 &&
                            dut.div_result == 8'(expected[div_results])) else $fatal(1, "Real divider mismatch");
                    div_results++;
                    div_pending = 0;
                end
                if (out_valid && out_ready) begin
                    assert (received < 4 && div_results == received+1 && out_data == 8'(expected[received]))
                        else $fatal(1, "Output %0d mismatch", received);
                    received++;
                end
            end
        end
    end

    task automatic reset_core;
        // Caller is at a falling edge (or time zero); no rising edge can sneak in.
        rst_n = 0; start = 0;
        repeat (2) @(negedge clk);
        assert (!busy && !done && !out_valid && !dut.exp_done && !dut.div_done && !dut.div_busy)
            else $fatal(1, "Reset failed");
        rst_n = 1;
    endtask
    task automatic launch;
        @(negedge clk);
        assert (start_ready) else $fatal(1, "Start not ready");
        start = 1;
        @(negedge clk); start = 0;
        assert (busy && !done) else $fatal(1, "Start did not clear done/set busy");
    endtask
    task automatic scan(input int fd, output int value);
        assert ($fscanf(fd, "%d", value) == 1) else $fatal(1, "Truncated vector file");
    endtask

    string path;
    int fd, qword, temp, checked = 0, ticks;
    bit reset_point;
    initial begin
        if ($value$plusargs("MEM_CYCLES=%d", memory_cycles))
            assert (memory_cycles >= 2 && memory_cycles <= 100) else $fatal(1, "Invalid memory latency");
        assert ($value$plusargs("VECTORS=%s", path)) else $fatal(1, "Missing vectors");
        fd = $fopen(path, "r");
        assert (fd != 0) else $fatal(1, "Cannot read vectors");
        reset_core();
        token_count = 0; start = 1;
        repeat (3) @(negedge clk);
        assert (!busy && !start_ready) else $fatal(1, "Accepted N=0");
        token_count = 17;
        repeat (3) @(negedge clk);
        assert (!busy && !start_ready) else $fatal(1, "Accepted N=17");
        start = 0;
        token_count = 1; query_packed = 0;
        foreach (memory[i]) memory[i] = 0;
        // Include reset with a real LUT result pending and every divider stage.
        for (int phase = 0; phase < 26; phase++) begin
            foreach (reads[i]) reads[i] = 0;
            force_output_stall = 1;
            launch();
            reset_point = 0; ticks = 0;
            while (!reset_point && ticks < 10000) begin
                @(negedge clk); ticks++;
                case (phase)
                    0: reset_point = mem_delay >= 0;
                    1: reset_point = mem_delay >= 0 && pending_slot == 0 && reads[0] == 1;
                    2: reset_point = dut.exp_start;
                    3: reset_point = dut.exp_done;
                    4: reset_point = mem_delay >= 0 && pending_slot == 32;
                    5: reset_point = out_valid;
                    default: reset_point = dut.div_busy &&
                        ((phase < 25 && int'(dut.divider_unit.step) == phase-6) ||
                         (phase == 25 && dut.divider_unit.state == dut.divider_unit.ROUND));
                endcase
            end
            assert (reset_point) else $fatal(1, "Missing reset point %0d", phase);
            reset_core();
            repeat (25) begin
                @(negedge clk);
                assert (!done && !out_valid && !dut.exp_done && !dut.div_done && !dut.div_busy)
                    else $fatal(1, "Stale result after reset");
            end
        end
        force_output_stall = 0;
        while ($fscanf(fd, "%d", count) == 1) begin
            scan(fd, qword);
            @(negedge clk);
            token_count = 5'(count); query_packed = 16'(qword);
            foreach (memory[i]) begin memory[i] = 8'ha5; reads[i] = 0; end
            for (int i = 0; i < 2*count; i++) begin scan(fd, temp); memory[i] = 8'(temp); end
            for (int i = 0; i < 2*count; i++) begin scan(fd, temp); memory[32+i] = 8'(temp); end
            for (int i = 0; i < 4; i++) scan(fd, expected[i]);
            for (int i = 0; i < count; i++) scan(fd, scores[i]);
            for (int i = 0; i < count; i++) scan(fd, weights[i]);
            expected_l = 0; expected_max = -224;
            foreach (expected_o[i]) begin expected_o[i] = 0; running_o[i] = 0; end
            for (int i = 0; i < count; i++) begin
                if (int'($signed(16'(scores[i]))) > expected_max) expected_max = int'($signed(16'(scores[i])));
                expected_l += weights[i];
                for (int c = 0; c < 4; c++) expected_o[c] += weights[i]*value_component(i,c);
            end
            captures = 0; mac_cycles = 0; max_updates = 0; accum_updates = 0;
            exp_calls = 0; exp_results = 0; div_calls = 0; div_results = 0; received = 0;
            running_l = 0; check_sums = 0; score_ready = 0; cycles = 0; active_case = 1;
            launch();
            query_packed = ~query_packed; token_count = 0; start = 1;
            repeat (2) @(negedge clk);
            start = 0; ticks = 0;
            while (!done && ticks < 20000) begin @(negedge clk); ticks++; end
            assert (done && !busy && received == 4 && captures == 2*count && mac_cycles == 8*count &&
                    max_updates == count && accum_updates == count && exp_calls == count &&
                    exp_results == count && div_calls == 4 && div_results == 4)
                else $fatal(1, "Incomplete transaction %0d", checked);
            for (int i = 0; i < 64; i++)
                assert (reads[i] == (i < 2*count ? 2 : ((i >= 32 && i < 32+2*count) ? 1 : 0)))
                    else $fatal(1, "Wrong read count at slot %0d", i);
            repeat (3) @(negedge clk);
            assert (done && !out_valid && !dut.div_done && !dut.exp_done) else $fatal(1, "Status did not settle");
            active_case = 0; total_cycles += cycles; checked++;
        end
        assert (checked == 138) else $fatal(1, "Missing controller cases");
        $display("PASS: integrated RTL controller, %0d Python cases; memory_cycles=%0d K=%h V=%h; reset, stalls, intermediate results and outputs", checked, memory_cycles, TEST_K_BASE, TEST_V_BASE);
        $display("METRICS total_cycles=%0d", total_cycles);
        $finish;
    end
    initial begin #100000000; $fatal(1, "Core timeout"); end
endmodule
